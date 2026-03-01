#!/bin/bash
# =============================================================================
# KlipperOS-AI — STANDARD Profile Installer
# =============================================================================
# LIGHT + KlipperScreen + Crowsnest + AI Print Monitor
# Hedef: 2GB+ RAM, RPi 4 2GB, Orange Pi
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

log() { echo -e "${GREEN}[STANDARD]${NC} $*"; }
warn() { echo -e "${YELLOW}[STANDARD]${NC} $*"; }
err() { echo -e "${RED}[STANDARD]${NC} $*" >&2; }

# --- Once LIGHT profili kur ---
install_light_base() {
    log "LIGHT profil bilesenleri kuruluyor..."

    if [ -x "${SCRIPT_DIR}/install-light.sh" ]; then
        bash "${SCRIPT_DIR}/install-light.sh"
    else
        err "install-light.sh bulunamadi: ${SCRIPT_DIR}/install-light.sh"
        exit 1
    fi
}

# --- KlipperScreen Kur ---
install_klipperscreen() {
    log "KlipperScreen kuruluyor..."

    # X11 ve pygame bagimliliklari
    apt-get install -y --no-install-recommends \
        xserver-xorg xinit x11-xserver-utils \
        python3-gi python3-gi-cairo gir1.2-gtk-3.0 \
        libopenjp2-7 libcairo2-dev \
        fonts-freefont-ttf \
        xinput

    if [ -d "${KLIPPER_HOME}/KlipperScreen" ]; then
        log "KlipperScreen zaten kurulu, guncelleniyor..."
        cd "${KLIPPER_HOME}/KlipperScreen"
        sudo -u "$KLIPPER_USER" git pull --ff-only || true
    else
        sudo -u "$KLIPPER_USER" git clone https://github.com/KlipperScreen/KlipperScreen.git \
            "${KLIPPER_HOME}/KlipperScreen"
    fi

    # Python venv
    local ks_venv="${KLIPPER_HOME}/KlipperScreen/.venv"
    if [ ! -d "$ks_venv" ]; then
        sudo -u "$KLIPPER_USER" python3 -m venv "$ks_venv"
    fi

    sudo -u "$KLIPPER_USER" "${ks_venv}/bin/pip" install --quiet \
        -r "${KLIPPER_HOME}/KlipperScreen/scripts/KlipperScreen-requirements.txt" \
        2>/dev/null || \
    sudo -u "$KLIPPER_USER" "${ks_venv}/bin/pip" install --quiet \
        netifaces requests websocket-client

    # KlipperScreen config
    local ks_conf="${KLIPPER_HOME}/printer_data/config/KlipperScreen.conf"
    if [ ! -f "$ks_conf" ]; then
        cat > "$ks_conf" << 'KSCONF'
[main]
language: tr
theme: colorized
show_heater_power: True
move_speed_xy: 80
move_speed_z: 10

[printer KlipperOS-AI]
moonraker_host: 127.0.0.1
moonraker_port: 7125
KSCONF
        chown "$KLIPPER_USER:$KLIPPER_USER" "$ks_conf"
    fi

    # Systemd service
    cat > /etc/systemd/system/KlipperScreen.service << KSSERVICE
[Unit]
Description=KlipperScreen Touch/Mouse UI
After=network.target moonraker.service

[Service]
Type=simple
User=${KLIPPER_USER}
Environment=DISPLAY=:0
ExecStartPre=/usr/bin/xinit -- :0 -nolisten tcp &
ExecStart=${ks_venv}/bin/python ${KLIPPER_HOME}/KlipperScreen/screen.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
KSSERVICE

    log "KlipperScreen kuruldu."
}

# --- Crowsnest Kur ---
install_crowsnest() {
    log "Crowsnest (kamera) kuruluyor..."

    # Kamera bagimliliklari
    apt-get install -y --no-install-recommends \
        v4l-utils \
        libjpeg62-turbo-dev \
        ffmpeg

    if [ -d "${KLIPPER_HOME}/crowsnest" ]; then
        log "Crowsnest zaten kurulu, guncelleniyor..."
        cd "${KLIPPER_HOME}/crowsnest"
        sudo -u "$KLIPPER_USER" git pull --ff-only || true
    else
        sudo -u "$KLIPPER_USER" git clone https://github.com/mainsail-crew/crowsnest.git \
            "${KLIPPER_HOME}/crowsnest"
    fi

    # Crowsnest config
    local cs_conf="${KLIPPER_HOME}/printer_data/config/crowsnest.conf"
    if [ ! -f "$cs_conf" ]; then
        cat > "$cs_conf" << 'CSCONF'
#### crowsnest.conf — KlipperOS-AI

[crowsnest]
log_path: ~/printer_data/logs/crowsnest.log
log_level: verbose
delete_log: true
no_resolve: false

[cam 1]
mode: ustreamer
enable_rtsp: false
port: 8080
device: /dev/video0
resolution: 640x480
max_fps: 15
v4l2ctl:
CSCONF
        chown "$KLIPPER_USER:$KLIPPER_USER" "$cs_conf"
    fi

    # Crowsnest'in kendi installer'ini calistir
    if [ -f "${KLIPPER_HOME}/crowsnest/tools/install.sh" ]; then
        cd "${KLIPPER_HOME}/crowsnest"
        sudo -u "$KLIPPER_USER" bash tools/install.sh || true
    fi

    # Systemd service (crowsnest kendi kurmadiysa)
    if [ ! -f /etc/systemd/system/crowsnest.service ]; then
        cat > /etc/systemd/system/crowsnest.service << CSSERVICE
[Unit]
Description=Crowsnest Camera Streamer
After=network.target

[Service]
Type=simple
User=${KLIPPER_USER}
ExecStart=${KLIPPER_HOME}/crowsnest/crowsnest -c ${cs_conf}
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
CSSERVICE
    fi

    log "Crowsnest kuruldu."
}

# --- AI Print Monitor Kur ---
install_ai_monitor() {
    log "AI Print Monitor kuruluyor..."

    local ai_dir="/opt/klipperos-ai/ai-monitor"
    local ai_venv="/opt/klipperos-ai/ai-venv"

    mkdir -p "$ai_dir/models"

    # AI monitor dosyalarini kopyala
    if [ -d "${SCRIPT_DIR}/../ai-monitor" ]; then
        cp -r "${SCRIPT_DIR}/../ai-monitor/"* "$ai_dir/" 2>/dev/null || true
    fi

    # Python venv
    if [ ! -d "$ai_venv" ]; then
        python3 -m venv "$ai_venv"
    fi

    "${ai_venv}/bin/pip" install --quiet \
        tflite-runtime \
        numpy \
        pillow \
        opencv-python-headless \
        requests

    # Systemd service
    cat > /etc/systemd/system/klipperos-ai-monitor.service << AISERVICE
[Unit]
Description=KlipperOS-AI Print Monitor
After=network.target moonraker.service crowsnest.service

[Service]
Type=simple
User=${KLIPPER_USER}
ExecStart=${ai_venv}/bin/python ${ai_dir}/print_monitor.py
Restart=always
RestartSec=30
Environment=MOONRAKER_URL=http://127.0.0.1:7125
Environment=CAMERA_URL=http://127.0.0.1:8080/?action=snapshot
Environment=CHECK_INTERVAL=10
Environment=FLOWGUARD_ENABLED=1

[Install]
WantedBy=multi-user.target
AISERVICE

    log "AI Print Monitor kuruldu."
}

# --- Moonraker'a kamera ve AI entegrasyonu ---
update_moonraker_config() {
    log "Moonraker config guncelleniyor (kamera + AI)..."

    local moon_conf="${KLIPPER_HOME}/printer_data/config/moonraker.conf"

    # Crowsnest update manager ekle
    if ! grep -q "crowsnest" "$moon_conf" 2>/dev/null; then
        cat >> "$moon_conf" << 'MOONEXT'

[update_manager crowsnest]
type: git_repo
path: ~/crowsnest
origin: https://github.com/mainsail-crew/crowsnest.git
managed_services: crowsnest
install_script: tools/install.sh

[update_manager KlipperScreen]
type: git_repo
path: ~/KlipperScreen
origin: https://github.com/KlipperScreen/KlipperScreen.git
virtualenv: ~/KlipperScreen/.venv
requirements: scripts/KlipperScreen-requirements.txt
managed_services: KlipperScreen
MOONEXT
    fi
}

# --- Sistem Panelleri ve Optimizasyonlar Kur ---
install_system_panels() {
    log "Sistem panelleri ve optimizasyonlar kuruluyor..."

    # VTE3 ve psutil paketleri
    apt-get install -y --no-install-recommends \
        gir1.2-vte-2.91 \
        matchbox-keyboard \
        python3-psutil

    # KlipperScreen venv'e psutil kur
    local ks_venv="${KLIPPER_HOME}/KlipperScreen/.venv"
    if [ -d "$ks_venv" ]; then
        sudo -u "$KLIPPER_USER" "${ks_venv}/bin/pip" install --quiet psutil requests
    fi

    # Panel dosyalarini kopyala
    local panel_dir="${KLIPPER_HOME}/KlipperScreen/ks_includes/panels"
    if [ -d "${SCRIPT_DIR}/../ks-panels" ]; then
        cp "${SCRIPT_DIR}/../ks-panels/"*.py "${panel_dir}/" 2>/dev/null || true
        chown -R "$KLIPPER_USER:$KLIPPER_USER" "${panel_dir}/"
        log "Sistem panelleri kopyalandi."
    fi

    # KlipperScreen config'e sistem menusu ekle
    local ks_conf="${KLIPPER_HOME}/printer_data/config/KlipperScreen.conf"
    if [ -f "$ks_conf" ] && ! grep -q "menu __main system" "$ks_conf" 2>/dev/null; then
        cat "${SCRIPT_DIR}/../config/klipperscreen/KlipperScreen.conf" > "$ks_conf"
        chown "$KLIPPER_USER:$KLIPPER_USER" "$ks_conf"
        log "KlipperScreen sistem menusu eklendi."
    fi

    # zram yapilandirmasi
    if [ -x "${SCRIPT_DIR}/setup-zram.sh" ]; then
        bash "${SCRIPT_DIR}/setup-zram.sh"
        log "zram yapilandirildi."
    fi

    # zram systemd service
    if [ -f "${SCRIPT_DIR}/../config/systemd/kos-zram.service" ]; then
        cp "${SCRIPT_DIR}/../config/systemd/kos-zram.service" /etc/systemd/system/
        systemctl daemon-reload
        systemctl enable kos-zram.service
        log "kos-zram servisi etkinlestirildi."
    fi

    # cgroup bellek limitleri
    local mem_limits="${SCRIPT_DIR}/../config/systemd/memory-limits"
    if [ -d "$mem_limits" ]; then
        for conf in "$mem_limits"/*.conf; do
            local svc_name
            svc_name=$(basename "$conf" .conf)
            mkdir -p "/etc/systemd/system/${svc_name}.service.d"
            cp "$conf" "/etc/systemd/system/${svc_name}.service.d/memory.conf"
        done
        systemctl daemon-reload
        log "Bellek limitleri yapilandirildi."
    fi

    # Logrotate config
    if [ -f "${SCRIPT_DIR}/../config/logrotate/klipperos" ]; then
        cp "${SCRIPT_DIR}/../config/logrotate/klipperos" /etc/logrotate.d/klipperos
        log "Log rotation yapilandirildi."
    fi

    # earlyoom kur
    apt-get install -y --no-install-recommends earlyoom 2>/dev/null || true
    systemctl enable earlyoom 2>/dev/null || true

    log "Sistem panelleri ve optimizasyonlar kuruldu."
}

# --- Servisleri Baslat ---
enable_standard_services() {
    log "STANDARD servisler etkinlestiriliyor..."

    systemctl daemon-reload
    systemctl enable crowsnest KlipperScreen klipperos-ai-monitor 2>/dev/null || true
    systemctl start crowsnest 2>/dev/null || true

    log "Servisler hazir."
}

# --- Ana ---
main() {
    echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  KlipperOS-AI — STANDARD Profile Installer   ║${NC}"
    echo -e "${CYAN}║  LIGHT + KlipperScreen + Crowsnest + AI      ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
    echo ""

    if [ "$(id -u)" -ne 0 ]; then
        err "Root yetkisi gerekli. 'sudo' ile calistirin."
        exit 1
    fi

    # RAM kontrolu
    local total_mb
    total_mb=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 ))
    if [ "$total_mb" -lt 1536 ]; then
        warn "Uyari: ${total_mb} MB RAM tespit edildi."
        warn "STANDARD profil icin 2GB+ onerilir."
        warn "Devam ediliyor..."
    fi

    install_light_base
    install_klipperscreen
    install_crowsnest
    install_ai_monitor
    install_system_panels
    update_moonraker_config
    enable_standard_services

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  STANDARD profil kurulumu tamamlandi!        ║${NC}"
    echo -e "${GREEN}║                                              ║${NC}"
    echo -e "${GREEN}║  Web UI:    http://klipperos.local           ║${NC}"
    echo -e "${GREEN}║  API:       http://klipperos.local:7125      ║${NC}"
    echo -e "${GREEN}║  Kamera:    http://klipperos.local:8080      ║${NC}"
    echo -e "${GREEN}║  AI Monitor: aktif (10sn aralik)             ║${NC}"
    echo -e "${GREEN}╚══════════════════════════════════════════════╝${NC}"
}

main "$@"
