#!/bin/bash
# =============================================================================
# KlipperOS-AI — Hardware Detection Script
# =============================================================================
# SBC ve x86 donanim tespiti. Profil onerisi icin kullanilir.
# Cikti: JSON formatinda donanim bilgileri
# =============================================================================

set -euo pipefail

# --- Renkler ---
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# --- Cikti dizini ---
HW_REPORT="/tmp/klipperos-hw-detect.json"

# --- CPU Detection ---
detect_cpu() {
    local arch
    arch=$(uname -m)

    local cpu_model
    cpu_model=$(grep -m1 "model name" /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo "Unknown")

    local cpu_cores
    cpu_cores=$(nproc 2>/dev/null || echo 1)

    local cpu_freq_mhz="0"
    if [ -f /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq ]; then
        cpu_freq_mhz=$(( $(cat /sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq) / 1000 ))
    elif grep -q "cpu MHz" /proc/cpuinfo 2>/dev/null; then
        cpu_freq_mhz=$(grep -m1 "cpu MHz" /proc/cpuinfo | cut -d: -f2 | xargs | cut -d. -f1)
    fi

    echo "  \"cpu\": {"
    echo "    \"arch\": \"${arch}\","
    echo "    \"model\": \"${cpu_model}\","
    echo "    \"cores\": ${cpu_cores},"
    echo "    \"freq_mhz\": ${cpu_freq_mhz}"
    echo "  },"
}

# --- RAM Detection ---
detect_ram() {
    local total_kb
    total_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local total_mb=$(( total_kb / 1024 ))

    local available_kb
    available_kb=$(grep MemAvailable /proc/meminfo | awk '{print $2}')
    local available_mb=$(( available_kb / 1024 ))

    echo "  \"ram\": {"
    echo "    \"total_mb\": ${total_mb},"
    echo "    \"available_mb\": ${available_mb}"
    echo "  },"
}

# --- Board Detection (SBC) ---
detect_board() {
    local board_type="unknown"
    local board_model="Unknown"

    # Raspberry Pi
    if [ -f /proc/device-tree/model ]; then
        board_model=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo "Unknown")
        if echo "$board_model" | grep -qi "raspberry"; then
            board_type="rpi"
        elif echo "$board_model" | grep -qi "orange"; then
            board_type="orangepi"
        elif echo "$board_model" | grep -qi "banana"; then
            board_type="bananapi"
        elif echo "$board_model" | grep -qi "rock"; then
            board_type="rockpi"
        else
            board_type="sbc"
        fi
    # x86 sistemi
    elif [ "$(uname -m)" = "x86_64" ] || [ "$(uname -m)" = "i686" ]; then
        board_type="x86"
        board_model=$(cat /sys/devices/virtual/dmi/id/product_name 2>/dev/null || echo "Generic x86")
    fi

    echo "  \"board\": {"
    echo "    \"type\": \"${board_type}\","
    echo "    \"model\": \"${board_model}\""
    echo "  },"
}

# --- GPU Detection ---
detect_gpu() {
    local gpu_name="none"
    local gpu_type="none"

    # VideoCore (RPi)
    if [ -e /dev/vchiq ]; then
        gpu_type="videocore"
        gpu_name="Broadcom VideoCore"
    # Mali (Orange Pi vb.)
    elif [ -e /dev/mali0 ] || [ -e /dev/mali ]; then
        gpu_type="mali"
        gpu_name="ARM Mali"
    # x86 GPU
    elif command -v lspci &>/dev/null; then
        local pci_gpu
        pci_gpu=$(lspci 2>/dev/null | grep -i "vga\|3d\|display" | head -1 | cut -d: -f3 | xargs || echo "")
        if [ -n "$pci_gpu" ]; then
            gpu_name="$pci_gpu"
            if echo "$pci_gpu" | grep -qi "nvidia"; then
                gpu_type="nvidia"
            elif echo "$pci_gpu" | grep -qi "amd\|radeon"; then
                gpu_type="amd"
            elif echo "$pci_gpu" | grep -qi "intel"; then
                gpu_type="intel"
            else
                gpu_type="other"
            fi
        fi
    fi

    echo "  \"gpu\": {"
    echo "    \"type\": \"${gpu_type}\","
    echo "    \"name\": \"${gpu_name}\""
    echo "  },"
}

# --- Camera Detection ---
detect_cameras() {
    local cameras=()

    # V4L2 kameralar
    if [ -d /sys/class/video4linux ]; then
        for dev in /sys/class/video4linux/video*; do
            if [ -f "$dev/name" ]; then
                local cam_name
                cam_name=$(cat "$dev/name" 2>/dev/null || echo "Unknown")
                local cam_dev
                cam_dev=$(basename "$dev")
                cameras+=("\"${cam_dev}: ${cam_name}\"")
            fi
        done
    fi

    # CSI kamera (RPi)
    local csi_detected="false"
    if [ -e /dev/vchiq ] && command -v vcgencmd &>/dev/null; then
        if vcgencmd get_camera 2>/dev/null | grep -q "detected=1"; then
            csi_detected="true"
        fi
    fi

    echo "  \"cameras\": {"
    echo "    \"v4l2_devices\": [$(IFS=,; echo "${cameras[*]:-}")],"
    echo "    \"csi_detected\": ${csi_detected}"
    echo "  },"
}

# --- USB Devices ---
detect_usb() {
    local serial_ports=()

    # Seri portlar (MCU icin)
    for port in /dev/ttyUSB* /dev/ttyACM* /dev/serial/by-id/*; do
        if [ -e "$port" ]; then
            serial_ports+=("\"${port}\"")
        fi
    done

    echo "  \"usb\": {"
    echo "    \"serial_ports\": [$(IFS=,; echo "${serial_ports[*]:-}")]"
    echo "  },"
}

# --- Disk Detection ---
detect_storage() {
    local root_total_mb
    root_total_mb=$(df -BM / | awk 'NR==2{print $2}' | tr -d 'M')
    local root_avail_mb
    root_avail_mb=$(df -BM / | awk 'NR==2{print $4}' | tr -d 'M')

    echo "  \"storage\": {"
    echo "    \"root_total_mb\": ${root_total_mb},"
    echo "    \"root_available_mb\": ${root_avail_mb}"
    echo "  },"
}

# --- Network Detection ---
detect_network() {
    local has_wifi="false"
    local has_ethernet="false"

    if [ -d /sys/class/net ]; then
        for iface in /sys/class/net/*; do
            local name
            name=$(basename "$iface")
            [ "$name" = "lo" ] && continue

            if [ -d "$iface/wireless" ]; then
                has_wifi="true"
            elif [ -f "$iface/type" ]; then
                local itype
                itype=$(cat "$iface/type" 2>/dev/null || echo "0")
                [ "$itype" = "1" ] && has_ethernet="true"
            fi
        done
    fi

    echo "  \"network\": {"
    echo "    \"wifi\": ${has_wifi},"
    echo "    \"ethernet\": ${has_ethernet}"
    echo "  },"
}

# --- Profile Recommendation ---
recommend_profile() {
    local total_ram_mb=$1
    local cpu_cores=$2
    local board_type=$3

    local profile="LIGHT"

    if [ "$total_ram_mb" -ge 4096 ] && [ "$cpu_cores" -ge 4 ]; then
        profile="FULL"
    elif [ "$total_ram_mb" -ge 2048 ]; then
        profile="STANDARD"
    fi

    echo "  \"recommended_profile\": \"${profile}\""
}

# --- Ana Fonksiyon ---
main() {
    echo -e "${CYAN}╔══════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║     KlipperOS-AI — Hardware Detection        ║${NC}"
    echo -e "${CYAN}╚══════════════════════════════════════════════╝${NC}"

    # RAM ve CPU icin degerleri yakala
    local total_kb
    total_kb=$(grep MemTotal /proc/meminfo | awk '{print $2}')
    local total_mb=$(( total_kb / 1024 ))
    local cpu_cores
    cpu_cores=$(nproc 2>/dev/null || echo 1)

    # Board type
    local board_type="x86"
    if [ -f /proc/device-tree/model ]; then
        if grep -qi "raspberry" /proc/device-tree/model 2>/dev/null; then
            board_type="rpi"
        elif grep -qi "orange" /proc/device-tree/model 2>/dev/null; then
            board_type="orangepi"
        else
            board_type="sbc"
        fi
    fi

    echo -e "${GREEN}Donanim taraniyor...${NC}"

    # JSON raporu olustur
    {
        echo "{"
        detect_cpu
        detect_ram
        detect_board
        detect_gpu
        detect_cameras
        detect_usb
        detect_storage
        detect_network
        recommend_profile "$total_mb" "$cpu_cores" "$board_type"
        echo "}"
    } > "$HW_REPORT"

    echo -e "${GREEN}Rapor: ${HW_REPORT}${NC}"

    # Ozet
    echo ""
    echo -e "${YELLOW}=== Donanim Ozeti ===${NC}"
    echo -e "  Board:    ${board_type}"
    echo -e "  RAM:      ${total_mb} MB"
    echo -e "  CPU:      ${cpu_cores} cekirdek"

    local rec_profile="LIGHT"
    if [ "$total_mb" -ge 4096 ] && [ "$cpu_cores" -ge 4 ]; then
        rec_profile="FULL"
    elif [ "$total_mb" -ge 2048 ]; then
        rec_profile="STANDARD"
    fi
    echo -e "  Profil:   ${CYAN}${rec_profile}${NC}"
    echo ""

    # JSON ciktisi (--json parametresi ile)
    if [ "${1:-}" = "--json" ]; then
        cat "$HW_REPORT"
    fi
}

main "$@"
