#!/bin/bash
# =============================================================================
# KlipperOS-AI — Ana Birlesik Installer
# =============================================================================
# Mevcut Debian/Ubuntu sistemine KlipperOS-AI kurulumu.
# Donanim algilar, profil onerir, kullanici secer, kurar.
#
# Kullanim:
#   sudo ./install-klipper-os.sh [--light|--standard|--full] [--non-interactive]
# =============================================================================

set -euo pipefail

VERSION="1.0.0"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_DIR="/opt/klipperos-ai"

# --- Renkler ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# --- Parametreler ---
PROFILE=""
NON_INTERACTIVE=false
NO_MODELS=false

# --- Banner ---
show_banner() {
    echo -e "${CYAN}"
    echo "╔═══════════════════════════════════════════════════╗"
    echo "║                                                   ║"
    echo "║    ██╗  ██╗██╗     ██╗██████╗ ██████╗ ███████╗   ║"
    echo "║    ██║ ██╔╝██║     ██║██╔══██╗██╔══██╗██╔════╝   ║"
    echo "║    █████╔╝ ██║     ██║██████╔╝██████╔╝█████╗     ║"
    echo "║    ██╔═██╗ ██║     ██║██╔═══╝ ██╔═══╝ ██╔══╝     ║"
    echo "║    ██║  ██╗███████╗██║██║     ██║     ███████╗   ║"
    echo "║    ╚═╝  ╚═╝╚══════╝╚═╝╚═╝     ╚═╝     ╚══════╝   ║"
    echo "║                OS-AI v${VERSION}                      ║"
    echo "║                                                   ║"
    echo "║    Klipper 3D Printer Linux Distribution          ║"
    echo "║    AI-Powered Print Monitoring                    ║"
    echo "║                                                   ║"
    echo "╚═══════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

# --- Arguman Parse ---
parse_args() {
    while [ $# -gt 0 ]; do
        case "$1" in
            --light)      PROFILE="LIGHT" ;;
            --standard)   PROFILE="STANDARD" ;;
            --full)       PROFILE="FULL" ;;
            --non-interactive) NON_INTERACTIVE=true ;;
            --no-models)  NO_MODELS=true ;;
            -h|--help)    show_help; exit 0 ;;
            *)            echo "Bilinmeyen parametre: $1"; exit 1 ;;
        esac
        shift
    done
}

show_help() {
    echo "KlipperOS-AI Installer v${VERSION}"
    echo ""
    echo "Kullanim: sudo $0 [SECENEKLER]"
    echo ""
    echo "Secenekler:"
    echo "  --light           LIGHT profil kur (Klipper + Moonraker + Mainsail)"
    echo "  --standard        STANDARD profil kur (+ KlipperScreen + Crowsnest + AI)"
    echo "  --full            FULL profil kur (+ Multi-printer + Timelapse)"
    echo "  --non-interactive Soru sormadan kur"
    echo "  --no-models       AI modellerini indirme"
    echo "  -h, --help        Bu yardim mesajini goster"
}

# --- Root Kontrolu ---
check_root() {
    if [ "$(id -u)" -ne 0 ]; then
        echo -e "${RED}Hata: Root yetkisi gerekli.${NC}"
        echo "  sudo $0 $*"
        exit 1
    fi
}

# --- Sistem Kontrolu ---
check_system() {
    echo -e "${CYAN}Sistem kontrol ediliyor...${NC}"

    # Debian/Ubuntu kontrolu
    if [ ! -f /etc/os-release ]; then
        echo -e "${RED}Hata: /etc/os-release bulunamadi.${NC}"
        exit 1
    fi

    local distro
    distro=$(grep ^ID= /etc/os-release | cut -d= -f2 | tr -d '"')

    if [[ "$distro" != "debian" && "$distro" != "ubuntu" && "$distro" != "raspbian" && "$distro" != "armbian" ]]; then
        echo -e "${YELLOW}Uyari: Desteklenen distro degil (${distro}).${NC}"
        echo -e "${YELLOW}Debian/Ubuntu/Raspbian/Armbian bekleniyor.${NC}"
        if [ "$NON_INTERACTIVE" = false ]; then
            read -rp "Devam etmek istiyor musunuz? [e/H] " ans
            [ "${ans,,}" != "e" ] && exit 1
        fi
    fi

    echo -e "${GREEN}Sistem: ${distro}${NC}"
}

# --- Donanim Algilama ---
detect_hardware() {
    echo -e "${CYAN}Donanim algilaniyor...${NC}"

    TOTAL_RAM_MB=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 ))
    CPU_CORES=$(nproc 2>/dev/null || echo 1)
    ARCH=$(uname -m)

    # Board tipi
    BOARD_TYPE="x86"
    if [ -f /proc/device-tree/model ]; then
        local model
        model=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo "")
        if echo "$model" | grep -qi "raspberry"; then
            BOARD_TYPE="rpi"
        elif echo "$model" | grep -qi "orange"; then
            BOARD_TYPE="orangepi"
        else
            BOARD_TYPE="sbc"
        fi
    fi

    echo -e "  Mimari:  ${ARCH}"
    echo -e "  Board:   ${BOARD_TYPE}"
    echo -e "  RAM:     ${TOTAL_RAM_MB} MB"
    echo -e "  CPU:     ${CPU_CORES} cekirdek"
    echo ""
}

# --- Profil Onerisi ---
recommend_profile() {
    local rec="LIGHT"

    if [ "$TOTAL_RAM_MB" -ge 4096 ] && [ "$CPU_CORES" -ge 4 ]; then
        rec="FULL"
    elif [ "$TOTAL_RAM_MB" -ge 2048 ]; then
        rec="STANDARD"
    fi

    echo "$rec"
}

# --- Profil Secimi ---
select_profile() {
    if [ -n "$PROFILE" ]; then
        echo -e "${GREEN}Secilen profil: ${BOLD}${PROFILE}${NC}"
        return
    fi

    local recommended
    recommended=$(recommend_profile)

    if [ "$NON_INTERACTIVE" = true ]; then
        PROFILE="$recommended"
        echo -e "${GREEN}Otomatik profil: ${BOLD}${PROFILE}${NC}"
        return
    fi

    echo -e "${CYAN}Profil secin:${NC}"
    echo ""
    echo -e "  ${BOLD}1) LIGHT${NC}    — Klipper + Moonraker + Mainsail"
    echo -e "               512MB-1GB RAM, temel kurulum"
    echo ""
    echo -e "  ${BOLD}2) STANDARD${NC} — + KlipperScreen + Crowsnest + AI Monitor"
    echo -e "               2GB+ RAM, kamera ve AI izleme"
    echo ""
    echo -e "  ${BOLD}3) FULL${NC}     — + Multi-printer + Timelapse + Gelismis AI"
    echo -e "               4GB+ RAM, coklu yazici desteği"
    echo ""
    echo -e "  ${YELLOW}Onerilen: ${BOLD}${recommended}${NC}"
    echo ""

    while true; do
        read -rp "Seciminiz [1/2/3]: " choice
        case "$choice" in
            1) PROFILE="LIGHT"; break ;;
            2) PROFILE="STANDARD"; break ;;
            3) PROFILE="FULL"; break ;;
            *) echo "Gecersiz secim. 1, 2 veya 3 girin." ;;
        esac
    done

    echo -e "${GREEN}Secilen profil: ${BOLD}${PROFILE}${NC}"
}

# --- Proje Dosyalarini Kopyala ---
install_project_files() {
    echo -e "${CYAN}KlipperOS-AI dosyalari kuruluyor...${NC}"

    mkdir -p "$INSTALL_DIR"

    # Eger git repodan calisiyorsak
    local project_root
    project_root="$(dirname "$SCRIPT_DIR")"

    if [ -d "$project_root/scripts" ] && [ -d "$project_root/ai-monitor" ]; then
        cp -r "$project_root/scripts" "$INSTALL_DIR/"
        cp -r "$project_root/ai-monitor" "$INSTALL_DIR/"
        cp -r "$project_root/config" "$INSTALL_DIR/" 2>/dev/null || true
        cp -r "$project_root/tools" "$INSTALL_DIR/" 2>/dev/null || true
        chmod +x "$INSTALL_DIR/scripts/"*.sh 2>/dev/null || true
    else
        echo -e "${YELLOW}Proje dizini bulunamadi. Git'ten indiriliyor...${NC}"
        git clone https://github.com/klipperos-ai/klipperos-ai.git /tmp/klipperos-ai-src
        cp -r /tmp/klipperos-ai-src/* "$INSTALL_DIR/"
        rm -rf /tmp/klipperos-ai-src
    fi

    echo -e "${GREEN}Proje dosyalari: ${INSTALL_DIR}${NC}"
}

# --- MCU Tarama ---
scan_mcu() {
    echo -e "${CYAN}MCU kartlari taraniyor...${NC}"

    if [ -x "${INSTALL_DIR}/scripts/mcu-detect.sh" ]; then
        bash "${INSTALL_DIR}/scripts/mcu-detect.sh" || true
    else
        echo -e "${YELLOW}mcu-detect.sh bulunamadi, atlaniyor.${NC}"
    fi
}

# --- Profil Installer Calistir ---
run_profile_installer() {
    echo -e "${CYAN}${PROFILE} profil installer calistiriliyor...${NC}"
    echo ""

    local installer=""
    case "$PROFILE" in
        LIGHT)    installer="${INSTALL_DIR}/scripts/install-light.sh" ;;
        STANDARD) installer="${INSTALL_DIR}/scripts/install-standard.sh" ;;
        FULL)     installer="${INSTALL_DIR}/scripts/install-full.sh" ;;
    esac

    if [ -x "$installer" ]; then
        bash "$installer"
    else
        echo -e "${RED}Hata: Installer bulunamadi: ${installer}${NC}"
        exit 1
    fi
}

# --- Python Tools Kur ---
install_python_tools() {
    echo -e "${CYAN}Python yonetim araclari kuruluyor...${NC}"

    if [ -f "${INSTALL_DIR}/pyproject.toml" ]; then
        cd "$INSTALL_DIR"
        pip3 install -e . 2>/dev/null || pip3 install . 2>/dev/null || true
    fi

    # CLI sembolik linkleri
    for tool in kos_profile kos_update kos_backup kos_mcu; do
        if [ -f "${INSTALL_DIR}/tools/${tool}.py" ]; then
            cat > "/usr/local/bin/${tool}" << TOOLWRAP
#!/bin/bash
python3 ${INSTALL_DIR}/tools/${tool}.py "\$@"
TOOLWRAP
            chmod +x "/usr/local/bin/${tool}"
        fi
    done

    echo -e "${GREEN}Yonetim araclari kuruldu.${NC}"
}

# --- AI Model Indirme ---
download_ai_models() {
    if [ "$NO_MODELS" = true ]; then
        echo -e "${YELLOW}AI model indirmesi atlandi (--no-models).${NC}"
        return
    fi

    if [ "$PROFILE" = "LIGHT" ]; then
        return
    fi

    echo -e "${CYAN}AI modeli indiriliyor...${NC}"

    local model_dir="${INSTALL_DIR}/ai-monitor/models"
    mkdir -p "$model_dir"

    # Spaghetti detection model (placeholder URL)
    if [ ! -f "$model_dir/spaghetti_detect.tflite" ]; then
        echo -e "${YELLOW}Not: AI modeli ilk baslangicta indirilecek.${NC}"
        echo -e "${YELLOW}Model dizini: ${model_dir}${NC}"
    fi
}

# --- Ozet ---
show_summary() {
    echo ""
    echo -e "${GREEN}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${GREEN}║                                                   ║${NC}"
    echo -e "${GREEN}║     KlipperOS-AI Kurulumu Tamamlandi!             ║${NC}"
    echo -e "${GREEN}║                                                   ║${NC}"
    echo -e "${GREEN}╠═══════════════════════════════════════════════════╣${NC}"
    echo -e "${GREEN}║                                                   ║${NC}"
    echo -e "${GREEN}║  Profil:    ${BOLD}${PROFILE}${NC}${GREEN}                                ║${NC}"
    echo -e "${GREEN}║  Dizin:     ${INSTALL_DIR}                        ║${NC}"
    echo -e "${GREEN}║                                                   ║${NC}"
    echo -e "${GREEN}║  Web UI:    http://klipperos.local                ║${NC}"
    echo -e "${GREEN}║  API:       http://klipperos.local:7125           ║${NC}"

    if [ "$PROFILE" != "LIGHT" ]; then
        echo -e "${GREEN}║  Kamera:    http://klipperos.local:8080           ║${NC}"
        echo -e "${GREEN}║  AI Mon:    aktif                                 ║${NC}"
    fi

    if [ "$PROFILE" = "FULL" ]; then
        echo -e "${GREEN}║  Yazici 2:  http://klipperos.local:81             ║${NC}"
        echo -e "${GREEN}║  Yazici 3:  http://klipperos.local:82             ║${NC}"
    fi

    echo -e "${GREEN}║                                                   ║${NC}"
    echo -e "${GREEN}║  Sonraki adimlar:                                 ║${NC}"
    echo -e "${GREEN}║  1. printer.cfg'yi yaziciya gore duzenleyin       ║${NC}"
    echo -e "${GREEN}║  2. MCU firmware flash: kos_mcu flash             ║${NC}"
    echo -e "${GREEN}║  3. Servisleri yeniden baslatin:                   ║${NC}"
    echo -e "${GREEN}║     sudo systemctl restart klipper moonraker      ║${NC}"
    echo -e "${GREEN}║                                                   ║${NC}"
    echo -e "${GREEN}╚═══════════════════════════════════════════════════╝${NC}"
}

# --- Ana ---
main() {
    parse_args "$@"
    show_banner
    check_root
    check_system
    detect_hardware
    select_profile
    install_project_files
    scan_mcu
    run_profile_installer
    install_python_tools
    download_ai_models
    show_summary
}

main "$@"
