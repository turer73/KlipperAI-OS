#!/bin/bash
# =============================================================================
# KlipperOS-AI — STANDARD Profile Installer
# =============================================================================
# LIGHT + KlipperScreen + Crowsnest + AI Print Monitor
# Hedef: 1GB+ RAM — dusuk RAM/CPU otomatik algilanir ve optimize edilir
# Dusuk RAM (<3GB) veya zayif CPU (<=2 core): AI Monitor atlanir,
# bellek limitleri sikilastirilir, zram lzo-rle kullanilir
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

# --- Donanim Algilama ---
LOW_RAM=false
WEAK_CPU=false

detect_hardware() {
    local total_mb
    total_mb=$(awk '/^MemTotal:/ { print int($2/1024) }' /proc/meminfo)
    local cpu_cores
    cpu_cores=$(nproc 2>/dev/null || echo 1)

    log "Donanim: ${total_mb} MB RAM, ${cpu_cores} cekirdek"

    if [ "$total_mb" -lt 3072 ]; then
        LOW_RAM=true
        log "Dusuk RAM tespit edildi (<3GB) — bellek optimizasyonlari aktif"
    fi

    if [ "$cpu_cores" -le 2 ]; then
        WEAK_CPU=true
        log "Dusuk cekirdek sayisi (<=2) — CPU optimizasyonlari aktif"
    fi
}

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

    local git_depth=""
    local pip_cache=""
    if [ "$LOW_RAM" = true ]; then
        git_depth="--depth 1"
        pip_cache="--no-cache-dir"
    fi

    if [ -d "${KLIPPER_HOME}/KlipperScreen" ]; then
        log "KlipperScreen zaten kurulu, guncelleniyor..."
        cd "${KLIPPER_HOME}/KlipperScreen"
        sudo -u "$KLIPPER_USER" git pull --ff-only || true
    else
        sudo -u "$KLIPPER_USER" git clone $git_depth \
            https://github.com/KlipperScreen/KlipperScreen.git \
            "${KLIPPER_HOME}/KlipperScreen"
    fi

    # Python venv
    local ks_venv="${KLIPPER_HOME}/KlipperScreen/.venv"
    if [ ! -d "$ks_venv" ]; then
        sudo -u "$KLIPPER_USER" python3 -m venv "$ks_venv"
    fi

    sudo -u "$KLIPPER_USER" "${ks_venv}/bin/pip" install --quiet $pip_cache \
        -r "${KLIPPER_HOME}/KlipperScreen/scripts/KlipperScreen-requirements.txt" \
        2>/dev/null || \
    sudo -u "$KLIPPER_USER" "${ks_venv}/bin/pip" install --quiet $pip_cache \
        netifaces requests websocket-client

    # KlipperScreen config
    local ks_conf="${KLIPPER_HOME}/printer_data/config/KlipperScreen.conf"
    if [ ! -f "$ks_conf" ]; then
        if [ "$LOW_RAM" = true ]; then
            cat > "$ks_conf" << 'KSCONF'
[main]
language: tr
screen_blanking: 300
show_cursor: True

[printer KlipperOS-AI]
moonraker_host: 127.0.0.1
moonraker_port: 7125
KSCONF
        else
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
        fi
        chown "$KLIPPER_USER:$KLIPPER_USER" "$ks_conf"
    fi

    # Systemd service — low-RAM'de Nice=10 (Klipper onceligi korur)
    local ks_nice=""
    if [ "$LOW_RAM" = true ] || [ "$WEAK_CPU" = true ]; then
        ks_nice="Nice=10"
    fi

    # Xwrapper: klipper kullanicisinin X baslatmasina izin ver
    mkdir -p /etc/X11
    cat > /etc/X11/Xwrapper.config << 'XWRAP'
allowed_users=anybody
needs_root_rights=yes
XWRAP

    cat > /etc/systemd/system/KlipperScreen.service << KSSERVICE
[Unit]
Description=KlipperScreen Touch/Mouse UI
After=network.target moonraker.service

[Service]
Type=simple
User=${KLIPPER_USER}
ExecStart=/usr/bin/xinit ${ks_venv}/bin/python ${KLIPPER_HOME}/KlipperScreen/screen.py -- :0 -nolisten tcp
Restart=always
RestartSec=10
${ks_nice}

[Install]
WantedBy=multi-user.target
KSSERVICE

    log "KlipperScreen kuruldu."
}

# --- Crowsnest Kur ---
install_crowsnest() {
    log "Crowsnest (kamera) kuruluyor..."

    # Kamera bagimliliklari — low-RAM'de ffmpeg atla (agir)
    if [ "$LOW_RAM" = true ]; then
        apt-get install -y --no-install-recommends v4l-utils
    else
        apt-get install -y --no-install-recommends \
            v4l-utils \
            libjpeg62-turbo-dev \
            ffmpeg
    fi

    local git_depth=""
    if [ "$LOW_RAM" = true ]; then
        git_depth="--depth 1"
    fi

    if [ -d "${KLIPPER_HOME}/crowsnest" ]; then
        log "Crowsnest zaten kurulu, guncelleniyor..."
        cd "${KLIPPER_HOME}/crowsnest"
        sudo -u "$KLIPPER_USER" git pull --ff-only || true
    else
        sudo -u "$KLIPPER_USER" git clone $git_depth \
            https://github.com/mainsail-crew/crowsnest.git \
            "${KLIPPER_HOME}/crowsnest"
    fi

    # Crowsnest config
    local cs_conf="${KLIPPER_HOME}/printer_data/config/crowsnest.conf"
    if [ ! -f "$cs_conf" ]; then
        local cs_log_level="verbose"
        local cs_fps=15
        if [ "$LOW_RAM" = true ]; then
            cs_log_level="quiet"
            cs_fps=10
        fi
        cat > "$cs_conf" << CSCONF
#### crowsnest.conf — KlipperOS-AI

[crowsnest]
log_path: ~/printer_data/logs/crowsnest.log
log_level: ${cs_log_level}
delete_log: true

[cam 1]
mode: ustreamer
enable_rtsp: false
port: 8080
device: /dev/video0
resolution: 640x480
max_fps: ${cs_fps}
CSCONF
        chown "$KLIPPER_USER:$KLIPPER_USER" "$cs_conf"
    fi

    # Crowsnest'in kendi installer'ini calistir
    if [ -f "${KLIPPER_HOME}/crowsnest/tools/install.sh" ]; then
        cd "${KLIPPER_HOME}/crowsnest"
        sudo -u "$KLIPPER_USER" bash tools/install.sh || true
    fi

    # Systemd service (crowsnest kendi kurmadiysa)
    local cn_extra=""
    if [ "$LOW_RAM" = true ] || [ "$WEAK_CPU" = true ]; then
        cn_extra="Nice=15
CPUQuota=30%"
    fi

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
${cn_extra}

[Install]
WantedBy=multi-user.target
CSSERVICE
    fi

    log "Crowsnest kuruldu."
}

# --- AI Print Monitor Kur (dusuk RAM/CPU'da atlanir) ---
install_ai_monitor() {
    if [ "$LOW_RAM" = true ] || [ "$WEAK_CPU" = true ]; then
        warn "AI Monitor ATLANIYOR — dusuk RAM/CPU tespit edildi"
        warn "Sonra etkinlestirmek icin: sudo /opt/klipperos-ai/scripts/install-standard.sh"
        return 0
    fi

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
        requests \
        psutil

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
Environment=ADAPTIVE_PRINT=0
Environment=PREDICTIVE_MAINT=1
Environment=AUTORECOVERY_ENABLED=0

[Install]
WantedBy=multi-user.target
AISERVICE

    # OS Tuning servisi
    if [ -f "${SCRIPT_DIR}/setup-os-tuning.sh" ]; then
        cat > /etc/systemd/system/kos-os-tuning.service << OSTUNING
[Unit]
Description=KlipperOS-AI OS Tuning
After=local-fs.target
Before=klipper.service

[Service]
Type=oneshot
ExecStart=/opt/klipperos-ai/scripts/setup-os-tuning.sh
RemainAfterExit=yes

[Install]
WantedBy=multi-user.target
OSTUNING
        systemctl enable kos-os-tuning.service 2>/dev/null || true
    fi

    # Resource Manager servisi
    cat > /etc/systemd/system/kos-resource-manager.service << RESMGR
[Unit]
Description=KlipperOS-AI Resource Manager
After=network.target klipperos-ai-monitor.service
Requires=klipperos-ai-monitor.service

[Service]
Type=simple
User=${KLIPPER_USER}
ExecStart=${ai_venv}/bin/python ${ai_dir}/resource_manager.py
Restart=always
RestartSec=30
MemoryMax=64M
CPUQuota=10%
Environment=MOONRAKER_URL=http://127.0.0.1:7125

[Install]
WantedBy=multi-user.target
RESMGR
    systemctl enable kos-resource-manager.service 2>/dev/null || true

    log "AI Print Monitor kuruldu."
}

# --- Klipper Input Shaping Assistant Kur ---
install_input_shaping_assistant() {
    log "Klipper Input Shaping Assistant kuruluyor..."

    local isa_dir="${KLIPPER_HOME}/input-shaping-assistant"

    if [ -d "$isa_dir" ]; then
        log "Input Shaping Assistant zaten kurulu, guncelleniyor..."
        cd "$isa_dir"
        sudo -u "$KLIPPER_USER" git pull --ff-only || true
    else
        sudo -u "$KLIPPER_USER" git clone \
            https://github.com/theycallmek/Klipper-Input-Shaping-Assistant.git \
            "$isa_dir"
    fi

    # Python venv
    local isa_venv="${isa_dir}/.venv"
    if [ ! -d "$isa_venv" ]; then
        sudo -u "$KLIPPER_USER" python3 -m venv "$isa_venv"
    fi

    # Bagimliliklari kur
    if [ -f "${isa_dir}/requirements.txt" ]; then
        sudo -u "$KLIPPER_USER" "${isa_venv}/bin/pip" install --quiet \
            -r "${isa_dir}/requirements.txt" 2>/dev/null || \
        sudo -u "$KLIPPER_USER" "${isa_venv}/bin/pip" install --quiet \
            matplotlib numpy
    fi

    # CLI wrapper
    cat > /usr/local/bin/kos-input-shaper << ISAWRAP
#!/bin/bash
# KlipperOS-AI — Input Shaping Assistant launcher
cd ${isa_dir}
${isa_venv}/bin/python main.py "\$@"
ISAWRAP
    chmod +x /usr/local/bin/kos-input-shaper

    log "Input Shaping Assistant kuruldu. Calistirmak icin: kos-input-shaper"
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

[update_manager input_shaping_assistant]
type: git_repo
path: ~/input-shaping-assistant
origin: https://github.com/theycallmek/Klipper-Input-Shaping-Assistant.git
virtualenv: ~/input-shaping-assistant/.venv
requirements: requirements.txt
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

    # zram yapilandirmasi (hata toleransli — boot servisinde duzgun calisacak)
    if [ -x "${SCRIPT_DIR}/setup-zram.sh" ]; then
        bash "${SCRIPT_DIR}/setup-zram.sh" || warn "zram kurulumu sirasinda hata — reboot sonrasi aktif olacak."
    fi

    # zram systemd service
    if [ -f "${SCRIPT_DIR}/../config/systemd/kos-zram.service" ]; then
        cp "${SCRIPT_DIR}/../config/systemd/kos-zram.service" /etc/systemd/system/
        systemctl daemon-reload
        systemctl enable kos-zram.service
        log "kos-zram servisi etkinlestirildi."
    fi

    # cgroup bellek limitleri — dusuk RAM'de sikistirilmis limitler kullan
    local mem_limits
    if [ "$LOW_RAM" = true ]; then
        mem_limits="${SCRIPT_DIR}/../config/systemd/memory-limits-lowram"
        log "Dusuk RAM bellek limitleri kullaniliyor"
    else
        mem_limits="${SCRIPT_DIR}/../config/systemd/memory-limits"
    fi
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

    # Dusuk RAM: Klipper ve Moonraker oncelik ayarlari (install-light sonrasi override)
    if [ "$LOW_RAM" = true ] || [ "$WEAK_CPU" = true ]; then
        # Klipper: en yuksek oncelik (Nice=-5)
        mkdir -p /etc/systemd/system/klipper.service.d
        cat > /etc/systemd/system/klipper.service.d/priority.conf << 'KPRI'
[Service]
Nice=-5
KPRI
        # Moonraker: orta oncelik (Nice=5)
        mkdir -p /etc/systemd/system/moonraker.service.d
        cat > /etc/systemd/system/moonraker.service.d/priority.conf << 'MPRI'
[Service]
Nice=5
MPRI
        systemctl daemon-reload
        log "Servis oncelikleri ayarlandi (Klipper=-5, Moonraker=5)"
    fi

    # Dusuk RAM: gereksiz kernel modullerini kara listeye al
    if [ "$LOW_RAM" = true ]; then
        cat > /etc/modprobe.d/klipperos-lowram.conf << 'MODBL'
# KlipperOS-AI: dusuk RAM optimizasyonu — gereksiz moduller devre disi
blacklist bluetooth
blacklist btusb
blacklist snd_pcm
blacklist snd_hda_intel
blacklist pcspkr
MODBL
        log "Gereksiz kernel modulleri kara listeye alindi"
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
    systemctl enable KlipperScreen 2>/dev/null || true

    # AI Monitor — sadece yeterli donanim varsa
    if [ "$LOW_RAM" = false ] && [ "$WEAK_CPU" = false ]; then
        systemctl enable klipperos-ai-monitor 2>/dev/null || true
    fi

    # Crowsnest — kamera algilama
    if ls /dev/video* 1>/dev/null 2>&1; then
        log "Kamera tespit edildi — crowsnest etkinlestiriliyor"
        systemctl enable crowsnest 2>/dev/null || true
        systemctl start crowsnest 2>/dev/null || true
    else
        warn "Kamera bulunamadi — crowsnest devre disi (sonra takinca otomatik baslar)"
        systemctl disable crowsnest 2>/dev/null || true
    fi

    log "Servisler hazir."
}

# --- FlowGuard Config Sec ---
install_flowguard_config() {
    local klipper_cfg_dir="${KLIPPER_HOME}/printer_data/config"
    local flowguard_src

    if [ "$LOW_RAM" = true ] || [ "$WEAK_CPU" = true ]; then
        # Sensor-only: L1 (filament) + L3 (StallGuard) — daemon gerektirmez
        flowguard_src="${SCRIPT_DIR}/../config/klipper/kos_flowguard_lowram.cfg"
        log "FlowGuard: sensor-only mod (L1+L3)"
    else
        # Full: L1+L2+L3+L4 — AI Monitor daemon ile entegre
        flowguard_src="${SCRIPT_DIR}/../config/klipper/kos_flowguard.cfg"
        log "FlowGuard: tam mod (L1+L2+L3+L4)"
    fi

    if [ -f "$flowguard_src" ]; then
        cp "$flowguard_src" "${klipper_cfg_dir}/kos_flowguard.cfg"
        chown "$KLIPPER_USER:$KLIPPER_USER" "${klipper_cfg_dir}/kos_flowguard.cfg"
        log "FlowGuard config kopyalandi."
    fi
}

# --- Ana ---
main() {
    echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║  KlipperOS-AI — STANDARD Profile Installer   ║${NC}"
    echo -e "${CYAN}║  LIGHT + KlipperScreen + Crowsnest + AI      ║${NC}"
    echo -e "${CYAN}║  Donanim otomatik algilanir ve optimize edilir║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
    echo ""

    if [ "$(id -u)" -ne 0 ]; then
        err "Root yetkisi gerekli. 'sudo' ile calistirin."
        exit 1
    fi

    # Donanim algilama — tum kararlari bu belirler
    detect_hardware

    # RAM kontrolu
    local total_mb
    total_mb=$(awk '/^MemTotal:/ { print int($2/1024) }' /proc/meminfo)
    if [ "$total_mb" -lt 1024 ]; then
        err "${total_mb} MB RAM — STANDARD profil icin en az 1GB gerekli."
        err "LIGHT profili deneyin: install-light.sh"
        exit 1
    elif [ "$total_mb" -lt 2048 ]; then
        warn "${total_mb} MB RAM — dusuk RAM modu aktif, AI Monitor atlanacak"
    fi

    install_light_base
    install_klipperscreen
    install_crowsnest
    install_ai_monitor
    install_input_shaping_assistant
    install_system_panels
    install_flowguard_config
    update_moonraker_config
    enable_standard_services

    echo ""
    echo -e "${GREEN}╔══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║  STANDARD profil kurulumu tamamlandi!            ║${NC}"
    echo -e "${GREEN}║                                                  ║${NC}"
    echo -e "${GREEN}║  Web UI:    http://klipperos.local               ║${NC}"
    echo -e "${GREEN}║  API:       http://klipperos.local:7125          ║${NC}"
    echo -e "${GREEN}║  Kamera:    http://klipperos.local:8080          ║${NC}"
    if [ "$LOW_RAM" = false ] && [ "$WEAK_CPU" = false ]; then
        echo -e "${GREEN}║  AI Monitor: aktif (10sn aralik)                 ║${NC}"
        echo -e "${GREEN}║  FlowGuard:  tam mod (L1+L2+L3+L4)              ║${NC}"
    else
        echo -e "${YELLOW}║  AI Monitor: atlanmis (dusuk donanim)            ║${NC}"
        echo -e "${YELLOW}║  FlowGuard:  sensor-only (L1+L3)                ║${NC}"
    fi
    echo -e "${GREEN}╚══════════════════════════════════════════════════╝${NC}"
}

main "$@"
