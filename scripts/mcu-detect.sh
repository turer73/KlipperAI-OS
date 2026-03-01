#!/bin/bash
# =============================================================================
# KlipperOS-AI — MCU Auto-Detection Script
# =============================================================================
# 3D yazici MCU kartlarini USB uzerinden tespit eder.
# Bilinen kartlari tanimlar ve Klipper config onerisi yapar.
# =============================================================================

set -euo pipefail

# --- Renkler ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

MCU_REPORT="/tmp/klipperos-mcu-detect.json"

# --- Bilinen MCU kartlari (USB VID:PID -> kart adi) ---
declare -A KNOWN_BOARDS=(
    # STM32 bazli kartlar
    ["1d50:614e"]="Klipper (pre-flashed)"
    ["0483:df11"]="STM32 DFU Mode"
    # Creality
    ["1a86:7523"]="CH340 (Creality/Generic)"
    # BTT (BigTreeTech)
    ["0483:5740"]="BTT SKR / Octopus (STM32 CDC)"
    # FTDI bazli
    ["0403:6001"]="FTDI FT232R (Generic)"
    ["0403:6015"]="FTDI FT231X"
    # CP2102 bazli
    ["10c4:ea60"]="CP2102 (Generic)"
    # RP2040 bazli
    ["2e8a:0003"]="RP2040 (Pico/SKR Pico)"
    ["2e8a:000a"]="RP2040 CMSIS-DAP"
    # ATmega bazli
    ["2341:0043"]="Arduino Mega 2560"
    ["2341:0042"]="Arduino Mega 2560 (R3)"
    ["1a86:7584"]="CH341 (Nano/Clone)"
    # MKS
    ["1209:abcd"]="MKS Board"
)

# --- Kart tipi -> Klipper config onerisi ---
declare -A BOARD_CONFIGS=(
    ["Klipper (pre-flashed)"]="generic"
    ["STM32 DFU Mode"]="stm32f4"
    ["CH340 (Creality/Generic)"]="creality"
    ["BTT SKR / Octopus (STM32 CDC)"]="btt"
    ["FTDI FT232R (Generic)"]="generic"
    ["FTDI FT231X"]="generic"
    ["CP2102 (Generic)"]="generic"
    ["RP2040 (Pico/SKR Pico)"]="rp2040"
    ["RP2040 CMSIS-DAP"]="rp2040"
    ["Arduino Mega 2560"]="atmega2560"
    ["Arduino Mega 2560 (R3)"]="atmega2560"
    ["CH341 (Nano/Clone)"]="atmega328p"
    ["MKS Board"]="mks"
)

# --- USB Cihaz Tarama ---
scan_usb_devices() {
    local found=0

    echo -e "${CYAN}USB seri cihazlar taraniyor...${NC}"
    echo ""

    # /dev/serial/by-id varsa tercih et
    if [ -d /dev/serial/by-id ]; then
        echo -e "${GREEN}Bulunan seri cihazlar (/dev/serial/by-id):${NC}"
        for dev in /dev/serial/by-id/*; do
            if [ -L "$dev" ]; then
                local real_dev
                real_dev=$(readlink -f "$dev")
                local dev_name
                dev_name=$(basename "$dev")
                echo -e "  ${YELLOW}${dev_name}${NC} -> ${real_dev}"
                found=$((found + 1))
            fi
        done
        echo ""
    fi

    # ttyUSB ve ttyACM tara
    echo -e "${GREEN}Seri portlar:${NC}"
    for port in /dev/ttyUSB* /dev/ttyACM*; do
        if [ -c "$port" ]; then
            echo -e "  ${YELLOW}${port}${NC}"
            found=$((found + 1))
        fi
    done

    if [ "$found" -eq 0 ]; then
        echo -e "  ${RED}Seri cihaz bulunamadi${NC}"
    fi

    echo ""
    return $found
}

# --- USB VID:PID ile Kart Tanima ---
identify_boards() {
    local detected_boards=()

    if ! command -v lsusb &>/dev/null; then
        echo -e "${RED}lsusb bulunamadi. 'usbutils' paketini kurun.${NC}"
        return 1
    fi

    echo -e "${CYAN}USB cihazlar analiz ediliyor...${NC}"
    echo ""

    while IFS= read -r line; do
        local vid_pid
        vid_pid=$(echo "$line" | grep -oP 'ID \K[0-9a-f]{4}:[0-9a-f]{4}' || continue)

        if [ -n "${KNOWN_BOARDS[$vid_pid]:-}" ]; then
            local board_name="${KNOWN_BOARDS[$vid_pid]}"
            local config_type="${BOARD_CONFIGS[$board_name]:-generic}"
            echo -e "  ${GREEN}✓${NC} ${board_name} (${vid_pid}) — Config: ${CYAN}${config_type}${NC}"
            detected_boards+=("{\"vid_pid\":\"${vid_pid}\",\"name\":\"${board_name}\",\"config\":\"${config_type}\"}")
        fi
    done < <(lsusb 2>/dev/null)

    if [ ${#detected_boards[@]} -eq 0 ]; then
        echo -e "  ${YELLOW}Bilinen MCU karti bulunamadi${NC}"
        echo -e "  ${YELLOW}Manuel konfigürasyon gerekebilir${NC}"
    fi

    echo ""

    # JSON ciktisi
    echo "[" > "$MCU_REPORT"
    local first=true
    for board in "${detected_boards[@]}"; do
        if [ "$first" = true ]; then
            first=false
        else
            echo "," >> "$MCU_REPORT"
        fi
        echo "  $board" >> "$MCU_REPORT"
    done
    echo "]" >> "$MCU_REPORT"
}

# --- Klipper Serial Config Onerisi ---
suggest_serial_config() {
    echo -e "${CYAN}Klipper serial konfigürasyon onerisi:${NC}"
    echo ""

    # /dev/serial/by-id tercih edilir (kararsiz olmaz)
    if [ -d /dev/serial/by-id ]; then
        for dev in /dev/serial/by-id/*; do
            if [ -L "$dev" ]; then
                echo -e "  [mcu]"
                echo -e "  serial: ${dev}"
                echo ""
                echo -e "  ${GREEN}Bu yol en kararsiz baglanti icin onerilir.${NC}"
                return 0
            fi
        done
    fi

    # Fallback: ttyUSB0 veya ttyACM0
    for port in /dev/ttyACM0 /dev/ttyUSB0; do
        if [ -c "$port" ]; then
            echo -e "  [mcu]"
            echo -e "  serial: ${port}"
            echo ""
            echo -e "  ${YELLOW}Not: /dev/serial/by-id kullanmaniz onerilir${NC}"
            echo -e "  ${YELLOW}(cihaz yeniden baglandiginda port degisebilir)${NC}"
            return 0
        fi
    done

    echo -e "  ${RED}Bagli MCU bulunamadi. Yaziciyi USB ile baglayin.${NC}"
}

# --- Canbus Tarama ---
detect_canbus() {
    echo -e "${CYAN}CANbus arayuzleri:${NC}"
    echo ""

    local found_can=false
    if [ -d /sys/class/net ]; then
        for iface in /sys/class/net/*; do
            local name
            name=$(basename "$iface")
            if echo "$name" | grep -q "^can"; then
                echo -e "  ${GREEN}✓${NC} ${name}"
                found_can=true
            fi
        done
    fi

    if [ "$found_can" = false ]; then
        echo -e "  ${YELLOW}CANbus arayuzu bulunamadi${NC}"
    fi
    echo ""
}

# --- Klipper Firmware Flash Onerisi ---
suggest_firmware_flash() {
    echo -e "${CYAN}Klipper firmware flash bilgisi:${NC}"
    echo ""
    echo -e "  Klipper firmware'i MCU'ya yuklemek icin:"
    echo -e "  ${YELLOW}cd ~/klipper${NC}"
    echo -e "  ${YELLOW}make menuconfig${NC}  (kart tipi secin)"
    echo -e "  ${YELLOW}make${NC}"
    echo -e "  ${YELLOW}make flash FLASH_DEVICE=/dev/ttyACM0${NC}"
    echo ""
    echo -e "  STM32 DFU mode icin:"
    echo -e "  ${YELLOW}make flash FLASH_DEVICE=0483:df11${NC}"
    echo ""
    echo -e "  RP2040 icin:"
    echo -e "  ${YELLOW}# BOOTSEL dugmesine basili tutarak USB'ye takın${NC}"
    echo -e "  ${YELLOW}make flash FLASH_DEVICE=first${NC}"
    echo ""
}

# --- Ana Fonksiyon ---
main() {
    echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║     KlipperOS-AI — MCU Detection             ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"
    echo ""

    scan_usb_devices
    identify_boards
    detect_canbus
    suggest_serial_config
    echo ""
    suggest_firmware_flash

    echo -e "${GREEN}MCU raporu: ${MCU_REPORT}${NC}"

    # JSON ciktisi (--json parametresi ile)
    if [ "${1:-}" = "--json" ]; then
        cat "$MCU_REPORT"
    fi
}

main "$@"
