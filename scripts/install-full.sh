#!/bin/bash
# =============================================================================
# KlipperOS-AI — FULL Profile Installer
# =============================================================================
# STANDARD + Multi-printer + Advanced AI + Timelapse
# Hedef: 4GB+ RAM, RPi 4/5 4GB+, x86
# =============================================================================

set -euo pipefail

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
KLIPPER_USER="${KLIPPER_USER:-klipper}"
KLIPPER_HOME="/home/${KLIPPER_USER}"

log() { echo -e "${GREEN}[FULL]${NC} $*"; }
warn() { echo -e "${YELLOW}[FULL]${NC} $*"; }
err() { echo -e "${RED}[FULL]${NC} $*" >&2; }

# --- Once STANDARD profili kur ---
install_standard_base() {
    log "STANDARD profil bilesenleri kuruluyor..."

    if [ -x "${SCRIPT_DIR}/install-standard.sh" ]; then
        bash "${SCRIPT_DIR}/install-standard.sh"
    else
        err "install-standard.sh bulunamadi: ${SCRIPT_DIR}/install-standard.sh"
        exit 1
    fi
}

# --- Multi-Printer Desteği ---
setup_multi_printer() {
    log "Multi-printer desteği kuruluyor..."

    # 2. ve 3. yazici icin veri dizinleri
    for i in 2 3; do
        local data_dir="${KLIPPER_HOME}/printer_${i}_data"

        if [ ! -d "$data_dir" ]; then
            sudo -u "$KLIPPER_USER" mkdir -p "${data_dir}/config"
            sudo -u "$KLIPPER_USER" mkdir -p "${data_dir}/logs"
            sudo -u "$KLIPPER_USER" mkdir -p "${data_dir}/gcodes"
            sudo -u "$KLIPPER_USER" mkdir -p "${data_dir}/database"
        fi

        # Klipper instance service
        cat > "/etc/systemd/system/klipper-${i}.service" << KLIPSERVICE
[Unit]
Description=Klipper 3D Printer ${i}
After=network.target

[Service]
Type=simple
User=${KLIPPER_USER}
ExecStart=${KLIPPER_HOME}/klippy-env/bin/python ${KLIPPER_HOME}/klipper/klippy/klippy.py ${data_dir}/config/printer.cfg -l ${data_dir}/logs/klippy.log -a /tmp/klippy_uds_${i}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
KLIPSERVICE

        # Moonraker instance service
        local moon_port=$((7125 + i - 1))
        cat > "/etc/systemd/system/moonraker-${i}.service" << MOONSERVICE
[Unit]
Description=Moonraker API Server - Printer ${i}
After=network.target klipper-${i}.service

[Service]
Type=simple
User=${KLIPPER_USER}
ExecStart=${KLIPPER_HOME}/moonraker-env/bin/python ${KLIPPER_HOME}/moonraker/moonraker/moonraker.py -d ${data_dir}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
MOONSERVICE

        # Moonraker config (farkli port)
        if [ ! -f "${data_dir}/config/moonraker.conf" ]; then
            cat > "${data_dir}/config/moonraker.conf" << MOONCONF2
[server]
host: 0.0.0.0
port: ${moon_port}
klippy_uds_address: /tmp/klippy_uds_${i}

[authorization]
trusted_clients:
    10.0.0.0/8
    127.0.0.0/8
    169.254.0.0/16
    172.16.0.0/12
    192.168.0.0/16
cors_domains:
    *.lan
    *.local
    *://localhost
    *://localhost:*

[octoprint_compat]
[history]
[file_manager]
enable_root_delete: True
MOONCONF2
            chown "$KLIPPER_USER:$KLIPPER_USER" "${data_dir}/config/moonraker.conf"
        fi

        # Varsayilan printer.cfg
        if [ ! -f "${data_dir}/config/printer.cfg" ]; then
            cat > "${data_dir}/config/printer.cfg" << PCONF2
# KlipperOS-AI — Printer ${i} Config
# Bu dosyayi ${i}. yazici kartiniza gore duzenleyin.

[mcu]
serial: /dev/ttyACM${i}

[printer]
kinematics: cartesian
max_velocity: 300
max_accel: 3000
max_z_velocity: 5
max_z_accel: 100

[virtual_sdcard]
path: ~/printer_${i}_data/gcodes

[display_status]
[pause_resume]
PCONF2
            chown "$KLIPPER_USER:$KLIPPER_USER" "${data_dir}/config/printer.cfg"
        fi
    done

    # Nginx multi-printer proxy
    cat > /etc/nginx/sites-available/mainsail-multi << NGINXMULTI
# Printer 2 — port 7126
server {
    listen 81;
    server_name _;
    root /home/${KLIPPER_USER}/mainsail;
    index index.html;
    client_max_body_size 0;

    location / { try_files \$uri \$uri/ /index.html; }
    location /websocket {
        proxy_pass http://127.0.0.1:7126/websocket;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
    location ~ ^/(printer|api|access|machine|server)/ {
        proxy_pass http://127.0.0.1:7126\$request_uri;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Host \$http_host;
    }
}

# Printer 3 — port 7127
server {
    listen 82;
    server_name _;
    root /home/${KLIPPER_USER}/mainsail;
    index index.html;
    client_max_body_size 0;

    location / { try_files \$uri \$uri/ /index.html; }
    location /websocket {
        proxy_pass http://127.0.0.1:7127/websocket;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_read_timeout 86400;
    }
    location ~ ^/(printer|api|access|machine|server)/ {
        proxy_pass http://127.0.0.1:7127\$request_uri;
        proxy_http_version 1.1;
        proxy_set_header Upgrade \$http_upgrade;
        proxy_set_header Host \$http_host;
    }
}
NGINXMULTI

    ln -sf /etc/nginx/sites-available/mainsail-multi /etc/nginx/sites-enabled/mainsail-multi

    log "Multi-printer desteği hazir (3 yazici)."
}

# --- Timelapse Kur ---
install_timelapse() {
    log "Moonraker Timelapse kuruluyor..."

    local tl_dir="${KLIPPER_HOME}/moonraker-timelapse"

    if [ -d "$tl_dir" ]; then
        cd "$tl_dir"
        sudo -u "$KLIPPER_USER" git pull --ff-only || true
    else
        sudo -u "$KLIPPER_USER" git clone https://github.com/mainsail-crew/moonraker-timelapse.git "$tl_dir"
    fi

    # Sembolik link
    ln -sf "${tl_dir}/component/timelapse.py" \
        "${KLIPPER_HOME}/moonraker/moonraker/components/timelapse.py" 2>/dev/null || true

    # Klipper macro
    ln -sf "${tl_dir}/klipper_macro/timelapse.cfg" \
        "${KLIPPER_HOME}/printer_data/config/timelapse.cfg" 2>/dev/null || true

    # printer.cfg'ye ekle
    local pcfg="${KLIPPER_HOME}/printer_data/config/printer.cfg"
    if ! grep -q "timelapse.cfg" "$pcfg" 2>/dev/null; then
        echo "" >> "$pcfg"
        echo "[include timelapse.cfg]" >> "$pcfg"
    fi

    # moonraker.conf'a ekle
    local mcfg="${KLIPPER_HOME}/printer_data/config/moonraker.conf"
    if ! grep -q "\[timelapse\]" "$mcfg" 2>/dev/null; then
        cat >> "$mcfg" << 'TLCONF'

[timelapse]
output_path: ~/printer_data/timelapse/
frame_path: /tmp/timelapse/
TLCONF
    fi

    # Timelapse cikti dizini
    sudo -u "$KLIPPER_USER" mkdir -p "${KLIPPER_HOME}/printer_data/timelapse"

    # ffmpeg gerekli
    apt-get install -y --no-install-recommends ffmpeg

    log "Timelapse kuruldu."
}

# --- Gelismis AI Ozellikleri ---
setup_advanced_ai() {
    log "Gelismis AI ozellikleri yapilandiriliyor..."

    local ai_dir="/opt/klipperos-ai/ai-monitor"

    # Gelismis AI: daha sik kontrol, ekstra tespit modelleri
    if [ -f /etc/systemd/system/klipperos-ai-monitor.service ]; then
        # Check interval'i 5 saniyeye dusur
        sed -i 's/CHECK_INTERVAL=10/CHECK_INTERVAL=5/' \
            /etc/systemd/system/klipperos-ai-monitor.service
    fi

    # FULL profil icin ekstra Python paketleri
    local ai_venv="/opt/klipperos-ai/ai-venv"
    if [ -d "$ai_venv" ]; then
        "${ai_venv}/bin/pip" install --quiet \
            scipy \
            scikit-image 2>/dev/null || true
    fi

    log "Gelismis AI hazir (5sn aralik, ekstra analiz)."
}

# --- Firewall ---
configure_firewall() {
    log "Firewall yapilandiriliyor..."

    if command -v ufw &>/dev/null; then
        ufw --force enable
        ufw allow 22/tcp    # SSH
        ufw allow 80/tcp    # Mainsail (Printer 1)
        ufw allow 81/tcp    # Mainsail (Printer 2)
        ufw allow 82/tcp    # Mainsail (Printer 3)
        ufw allow 7125/tcp  # Moonraker 1
        ufw allow 7126/tcp  # Moonraker 2
        ufw allow 7127/tcp  # Moonraker 3
        ufw allow 8080/tcp  # Kamera
        ufw allow 5353/udp  # mDNS
        ufw allow in on tailscale0  # Tailscale VPN
        log "Firewall yapilandirildi."
    else
        apt-get install -y --no-install-recommends ufw
        configure_firewall
    fi
}

# --- Servisleri Baslat ---
enable_full_services() {
    log "FULL servisler etkinlestiriliyor..."

    systemctl daemon-reload
    nginx -t && systemctl restart nginx

    log "Servisler hazir."
}

# --- Ana ---
main() {
    echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  KlipperOS-AI — FULL Profile Installer       ║${NC}"
    echo -e "${CYAN}║  STANDARD + Multi-printer + Timelapse + AI+  ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
    echo ""

    if [ "$(id -u)" -ne 0 ]; then
        err "Root yetkisi gerekli. 'sudo' ile calistirin."
        exit 1
    fi

    # RAM kontrolu
    local total_mb
    total_mb=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 ))
    if [ "$total_mb" -lt 3584 ]; then
        warn "Uyari: ${total_mb} MB RAM tespit edildi."
        warn "FULL profil icin 4GB+ onerilir."
        warn "Devam ediliyor..."
    fi

    install_standard_base
    setup_multi_printer
    install_timelapse
    setup_advanced_ai
    configure_firewall
    enable_full_services

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  FULL profil kurulumu tamamlandi!            ║${NC}"
    echo -e "${GREEN}║                                              ║${NC}"
    echo -e "${GREEN}║  Yazici 1: http://klipperos.local            ║${NC}"
    echo -e "${GREEN}║  Yazici 2: http://klipperos.local:81         ║${NC}"
    echo -e "${GREEN}║  Yazici 3: http://klipperos.local:82         ║${NC}"
    echo -e "${GREEN}║  Kamera:   http://klipperos.local:8080       ║${NC}"
    echo -e "${GREEN}║  AI:       aktif (5sn aralik, gelismis)      ║${NC}"
    echo -e "${GREEN}║  Timelapse: aktif                            ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
}

main "$@"
