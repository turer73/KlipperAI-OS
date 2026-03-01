#!/bin/bash
# =============================================================================
# KlipperOS-AI — LIGHT Profile Installer
# =============================================================================
# Minimum kurulum: Klipper + Moonraker + Mainsail
# Hedef: 512MB-1GB RAM, RPi 3, eski x86
# =============================================================================

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

KLIPPER_USER="${KLIPPER_USER:-klipper}"
KLIPPER_HOME="/home/${KLIPPER_USER}"
KLIPPER_VENV="${KLIPPER_HOME}/klippy-env"
MOONRAKER_VENV="${KLIPPER_HOME}/moonraker-env"

log() { echo -e "${GREEN}[LIGHT]${NC} $*"; }
warn() { echo -e "${YELLOW}[LIGHT]${NC} $*"; }
err() { echo -e "${RED}[LIGHT]${NC} $*" >&2; }

# --- Kullanici Olustur ---
create_klipper_user() {
    log "Klipper kullanicisi olusturuluyor..."

    if id "$KLIPPER_USER" &>/dev/null; then
        log "Kullanici '${KLIPPER_USER}' zaten var."
    else
        useradd -m -s /bin/bash -G dialout,tty,video,sudo "$KLIPPER_USER"
        log "Kullanici '${KLIPPER_USER}' olusturuldu."
    fi

    # dialout grubu (seri port erisimi)
    usermod -aG dialout "$KLIPPER_USER" 2>/dev/null || true
}

# --- Sistem Bagimliklarini Kur ---
install_dependencies() {
    log "Sistem paketleri kuruluyor..."

    apt-get update -qq
    apt-get install -y --no-install-recommends \
        git \
        python3 python3-pip python3-venv python3-dev \
        python3-serial python3-cffi python3-greenlet \
        gcc g++ make \
        libffi-dev libncurses-dev libusb-1.0-0-dev \
        avrdude stm32flash dfu-util \
        nginx \
        avahi-daemon \
        curl wget unzip \
        supervisor \
        lsof
}

# --- Klipper Kur ---
install_klipper() {
    log "Klipper kuruluyor..."

    if [ -d "${KLIPPER_HOME}/klipper" ]; then
        log "Klipper zaten kurulu, guncelleniyor..."
        cd "${KLIPPER_HOME}/klipper"
        sudo -u "$KLIPPER_USER" git pull --ff-only || true
    else
        sudo -u "$KLIPPER_USER" git clone https://github.com/Klipper3d/klipper.git "${KLIPPER_HOME}/klipper"
    fi

    # Python venv
    if [ ! -d "$KLIPPER_VENV" ]; then
        sudo -u "$KLIPPER_USER" python3 -m venv "$KLIPPER_VENV"
    fi

    sudo -u "$KLIPPER_USER" "${KLIPPER_VENV}/bin/pip" install --quiet \
        cffi greenlet pyserial jinja2 markupsafe

    # Systemd service
    cat > /etc/systemd/system/klipper.service << 'KSERVICE'
[Unit]
Description=Klipper 3D Printer Firmware Host
After=network.target

[Service]
Type=simple
User=klipper
ExecStart=/home/klipper/klippy-env/bin/python /home/klipper/klipper/klippy/klippy.py /home/klipper/printer_data/config/printer.cfg -l /home/klipper/printer_data/logs/klippy.log -a /tmp/klippy_uds
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
KSERVICE

    log "Klipper kuruldu."
}

# --- Moonraker Kur ---
install_moonraker() {
    log "Moonraker kuruluyor..."

    if [ -d "${KLIPPER_HOME}/moonraker" ]; then
        log "Moonraker zaten kurulu, guncelleniyor..."
        cd "${KLIPPER_HOME}/moonraker"
        sudo -u "$KLIPPER_USER" git pull --ff-only || true
    else
        sudo -u "$KLIPPER_USER" git clone https://github.com/Arksine/moonraker.git "${KLIPPER_HOME}/moonraker"
    fi

    # Python venv
    if [ ! -d "$MOONRAKER_VENV" ]; then
        sudo -u "$KLIPPER_USER" python3 -m venv "$MOONRAKER_VENV"
    fi

    sudo -u "$KLIPPER_USER" "${MOONRAKER_VENV}/bin/pip" install --quiet \
        tornado lmdb streaming-form-data inotify-simple distro \
        pillow pycurl zeroconf preprocess-cancellation apprise

    # Systemd service
    cat > /etc/systemd/system/moonraker.service << 'MSERVICE'
[Unit]
Description=Moonraker API Server for Klipper
After=network.target klipper.service

[Service]
Type=simple
User=klipper
ExecStart=/home/klipper/moonraker-env/bin/python /home/klipper/moonraker/moonraker/moonraker.py -d /home/klipper/printer_data
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
MSERVICE

    log "Moonraker kuruldu."
}

# --- Mainsail Kur ---
install_mainsail() {
    log "Mainsail kuruluyor..."

    local mainsail_dir="/home/${KLIPPER_USER}/mainsail"

    mkdir -p "$mainsail_dir"

    # Son release'i indir
    local release_url
    release_url=$(curl -s https://api.github.com/repos/mainsail-crew/mainsail/releases/latest \
        | grep "browser_download_url.*mainsail.zip" \
        | cut -d '"' -f 4)

    if [ -n "$release_url" ]; then
        wget -q "$release_url" -O /tmp/mainsail.zip
        unzip -qo /tmp/mainsail.zip -d "$mainsail_dir"
        rm -f /tmp/mainsail.zip
        chown -R "$KLIPPER_USER:$KLIPPER_USER" "$mainsail_dir"
        log "Mainsail indirildi ve kuruldu."
    else
        warn "Mainsail indirilemedi. Internet baglantisini kontrol edin."
    fi
}

# --- Nginx Yapilandir ---
configure_nginx() {
    log "Nginx yapilandiriliyor..."

    # Default site'i kaldir
    rm -f /etc/nginx/sites-enabled/default

    # Mainsail nginx config
    cat > /etc/nginx/sites-available/mainsail << NGINX
upstream apiserver {
    ip_hash;
    server 127.0.0.1:7125;
}

server {
    listen 80 default_server;
    listen [::]:80 default_server;

    access_log /var/log/nginx/mainsail-access.log;
    error_log /var/log/nginx/mainsail-error.log;

    root /home/${KLIPPER_USER}/mainsail;
    index index.html;
    server_name _;

    client_max_body_size 0;

    proxy_request_buffering off;

    location / {
        try_files \$uri \$uri/ /index.html;
    }

    location = /index.html {
        add_header Cache-Control "no-store, no-cache, must-revalidate";
    }

    location /websocket {
        proxy_pass http://apiserver/websocket;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_read_timeout 86400;
    }

    location ~ ^/(printer|api|access|machine|server)/ {
        proxy_pass http://apiserver\$request_uri;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Host \$http_host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Scheme \$scheme;
    }
}
NGINX

    ln -sf /etc/nginx/sites-available/mainsail /etc/nginx/sites-enabled/mainsail
    nginx -t && systemctl restart nginx

    log "Nginx yapilandirildi."
}

# --- Printer Data Dizinleri ---
setup_printer_data() {
    log "Printer data dizinleri olusturuluyor..."

    local data_dir="${KLIPPER_HOME}/printer_data"
    mkdir -p "${data_dir}/config"
    mkdir -p "${data_dir}/logs"
    mkdir -p "${data_dir}/gcodes"
    mkdir -p "${data_dir}/database"

    # Varsayilan printer.cfg
    if [ ! -f "${data_dir}/config/printer.cfg" ]; then
        cat > "${data_dir}/config/printer.cfg" << 'PRINTERCFG'
# KlipperOS-AI — Varsayilan Printer Config
# Bu dosyayi yazici kartiniza gore duzenleyin.
#
# MCU tespiti icin: sudo /opt/klipperos-ai/scripts/mcu-detect.sh
# Ornek config dosyalari: /opt/klipperos-ai/config/klipper/

[mcu]
# serial: /dev/serial/by-id/usb-xxxx
# Yukaridaki satiri MCU'nuzun seri portuyla degistirin
serial: /dev/ttyACM0

[printer]
kinematics: cartesian
max_velocity: 300
max_accel: 3000
max_z_velocity: 5
max_z_accel: 100

[virtual_sdcard]
path: ~/printer_data/gcodes

[display_status]

[pause_resume]

[gcode_macro PAUSE]
rename_existing: BASE_PAUSE
gcode:
    SAVE_GCODE_STATE NAME=PAUSE_state
    BASE_PAUSE
    G91
    G1 Z10 F600
    G90

[gcode_macro RESUME]
rename_existing: BASE_RESUME
gcode:
    RESTORE_GCODE_STATE NAME=PAUSE_state MOVE=1
    BASE_RESUME

[gcode_macro CANCEL_PRINT]
rename_existing: BASE_CANCEL
gcode:
    TURN_OFF_HEATERS
    G91
    G1 Z5 F600
    G90
    G1 X0 Y200 F6000
    M84
    BASE_CANCEL
PRINTERCFG
    fi

    # Moonraker config
    if [ ! -f "${data_dir}/config/moonraker.conf" ]; then
        cat > "${data_dir}/config/moonraker.conf" << 'MOONCONF'
[server]
host: 0.0.0.0
port: 7125
klippy_uds_address: /tmp/klippy_uds

[authorization]
trusted_clients:
    10.0.0.0/8
    127.0.0.0/8
    169.254.0.0/16
    172.16.0.0/12
    192.168.0.0/16
    100.64.0.0/10
cors_domains:
    *.lan
    *.local
    *://localhost
    *://localhost:*

[octoprint_compat]

[history]

[file_manager]
enable_root_delete: True

[update_manager]

[update_manager mainsail]
type: web
channel: stable
repo: mainsail-crew/mainsail
path: ~/mainsail
MOONCONF
    fi

    chown -R "$KLIPPER_USER:$KLIPPER_USER" "$data_dir"
    log "Printer data dizinleri hazir."
}

# --- Tailscale Kur ---
install_tailscale() {
    log "Tailscale kuruluyor..."

    # Tailscale repo ekle ve kur
    if ! command -v tailscale &>/dev/null; then
        curl -fsSL https://tailscale.com/install.sh | sh
    else
        log "Tailscale zaten kurulu."
    fi

    # Servisi etkinlestir
    systemctl enable --now tailscaled 2>/dev/null || true

    log "Tailscale kuruldu."
    log "Baglanti icin: sudo tailscale up --ssh"
    log "Durum:         tailscale status"
}

# --- SSH Guclendir ---
configure_ssh() {
    log "SSH yapilandiriliyor..."

    local sshd_config="/etc/ssh/sshd_config"

    if [ ! -f "$sshd_config" ]; then
        apt-get install -y --no-install-recommends openssh-server
    fi

    # SSH hardening
    # Root login kapat
    sed -i 's/^#*PermitRootLogin.*/PermitRootLogin no/' "$sshd_config"
    # Sifre auth kapat (sadece key)
    sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' "$sshd_config"
    # Bos sifre reddet
    sed -i 's/^#*PermitEmptyPasswords.*/PermitEmptyPasswords no/' "$sshd_config"
    # X11 forwarding kapat
    sed -i 's/^#*X11Forwarding.*/X11Forwarding no/' "$sshd_config"
    # MaxAuthTries sinirla
    sed -i 's/^#*MaxAuthTries.*/MaxAuthTries 3/' "$sshd_config"
    # ClientAlive (baglanti kopma tespiti)
    sed -i 's/^#*ClientAliveInterval.*/ClientAliveInterval 300/' "$sshd_config"
    sed -i 's/^#*ClientAliveCountMax.*/ClientAliveCountMax 2/' "$sshd_config"

    # klipper kullanicisi icin SSH dizini olustur
    local ssh_dir="${KLIPPER_HOME}/.ssh"
    if [ ! -d "$ssh_dir" ]; then
        sudo -u "$KLIPPER_USER" mkdir -p "$ssh_dir"
        chmod 700 "$ssh_dir"
        touch "$ssh_dir/authorized_keys"
        chmod 600 "$ssh_dir/authorized_keys"
        chown -R "$KLIPPER_USER:$KLIPPER_USER" "$ssh_dir"
    fi

    # SSH servisi yeniden baslat
    systemctl restart sshd 2>/dev/null || systemctl restart ssh 2>/dev/null || true

    log "SSH guclendirildi (root kapal, sadece key auth)."
    log "SSH key eklemek icin:"
    log "  ssh-copy-id ${KLIPPER_USER}@klipperos.local"
    log "Veya Tailscale SSH: sudo tailscale up --ssh"
}

# --- mDNS Yapilandir ---
configure_mdns() {
    log "mDNS yapilandiriliyor (klipperos.local)..."

    if ! systemctl is-active --quiet avahi-daemon; then
        systemctl enable --now avahi-daemon
    fi

    # Hostname ayarla
    hostnamectl set-hostname klipperos 2>/dev/null || \
        echo "klipperos" > /etc/hostname

    log "mDNS hazir: klipperos.local"
}

# --- Servisleri Baslat ---
enable_services() {
    log "Servisler etkinlestiriliyor..."

    systemctl daemon-reload
    systemctl enable klipper moonraker nginx avahi-daemon
    systemctl start klipper moonraker nginx

    log "Servisler baslatildi."
}

# --- Ana ---
main() {
    echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  KlipperOS-AI — LIGHT Profile Installer      ║${NC}"
    echo -e "${CYAN}║  Klipper + Moonraker + Mainsail              ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
    echo ""

    if [ "$(id -u)" -ne 0 ]; then
        err "Root yetkisi gerekli. 'sudo' ile calistirin."
        exit 1
    fi

    create_klipper_user
    install_dependencies
    install_klipper
    install_moonraker
    install_mainsail
    setup_printer_data
    configure_nginx
    configure_ssh
    configure_mdns
    install_tailscale
    enable_services

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  LIGHT profil kurulumu tamamlandi!           ║${NC}"
    echo -e "${GREEN}║                                              ║${NC}"
    echo -e "${GREEN}║  Web UI:     http://klipperos.local           ║${NC}"
    echo -e "${GREEN}║  API:        http://klipperos.local:7125     ║${NC}"
    echo -e "${GREEN}║  Tailscale:  sudo tailscale up               ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
}

main "$@"
