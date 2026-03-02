#!/usr/bin/env bash
# KlipperOS-AI  --  zram + zstd swap & memory-tuning bootstrap
# Called once at boot by kos-zram.service (oneshot)
set -euo pipefail

###############################################################################
# Guard: must be root
###############################################################################
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: setup-zram.sh must be run as root" >&2
    exit 1
fi

###############################################################################
# Hardware detection — auto-select optimal settings
###############################################################################
ZRAM_DEV="/dev/zram0"
SYSCTL_CONF="/etc/sysctl.d/99-kos-zram.conf"
SWAP_PRIORITY=100

TOTAL_KB=$(awk '/^MemTotal:/ { print $2 }' /proc/meminfo)
TOTAL_MB=$(( TOTAL_KB / 1024 ))
CPU_CORES=$(nproc 2>/dev/null || echo 1)

# Dusuk RAM (<3GB) veya tek cekirdek: lzo-rle (4x daha az CPU)
# Normal donanim: zstd (daha iyi sikistirma)
if [ "$TOTAL_MB" -lt 3072 ] || [ "$CPU_CORES" -le 2 ]; then
    COMP_ALGO="lzo-rle"
    SWAPPINESS=100
    ZRAM_PCT=50
    LOW_RAM=true
    echo "[kos-zram] Dusuk RAM/CPU tespit edildi (${TOTAL_MB}MB, ${CPU_CORES} cekirdek) — lzo-rle modu"
else
    COMP_ALGO="zstd"
    SWAPPINESS=150
    ZRAM_PCT=50
    LOW_RAM=false
    echo "[kos-zram] Normal donanim (${TOTAL_MB}MB, ${CPU_CORES} cekirdek) — zstd modu"
fi

###############################################################################
# 1. Load zram kernel module
###############################################################################
echo "[kos-zram] Loading zram kernel module ..."
modprobe zram num_devices=1

###############################################################################
# 2. Calculate zram size (ZRAM_PCT% of total RAM, in bytes)
###############################################################################
ZRAM_SIZE_BYTES=$(( TOTAL_KB * 1024 * ZRAM_PCT / 100 ))
echo "[kos-zram] Total RAM: ${TOTAL_MB} MB  ->  zram disk size: $(( ZRAM_SIZE_BYTES / 1024 / 1024 )) MB (${ZRAM_PCT}%)"

###############################################################################
# 3. Configure zram0 device
###############################################################################
echo "[kos-zram] Setting compression algorithm to ${COMP_ALGO} ..."
echo "${COMP_ALGO}" > /sys/block/zram0/comp_algorithm

echo "[kos-zram] Setting disk size to ${ZRAM_SIZE_BYTES} bytes ..."
echo "${ZRAM_SIZE_BYTES}" > /sys/block/zram0/disksize

###############################################################################
# 4. Create and activate swap
###############################################################################
echo "[kos-zram] Creating swap on ${ZRAM_DEV} ..."
mkswap "${ZRAM_DEV}"

echo "[kos-zram] Activating swap with priority ${SWAP_PRIORITY} ..."
swapon -p "${SWAP_PRIORITY}" "${ZRAM_DEV}"

###############################################################################
# 5. Apply runtime kernel parameters
###############################################################################
echo "[kos-zram] Applying kernel memory tuning parameters ..."
sysctl -w vm.swappiness=${SWAPPINESS}
sysctl -w vm.page-cluster=0

if [ "$LOW_RAM" = true ]; then
    # Dusuk RAM: daha yavas dirty writeback (I/O azaltir)
    sysctl -w vm.dirty_expire_centisecs=3000
    sysctl -w vm.dirty_writeback_centisecs=1000
    sysctl -w vm.dirty_ratio=40
    sysctl -w vm.vfs_cache_pressure=200
    sysctl -w vm.min_free_kbytes=16384

    # THP devre disi (tek cekirdekte defrag CPU yer)
    echo never > /sys/kernel/mm/transparent_hugepage/enabled 2>/dev/null || true
    echo "[kos-zram] THP devre disi birakildi (dusuk RAM modu)"
else
    sysctl -w vm.dirty_expire_centisecs=1500
    sysctl -w vm.dirty_writeback_centisecs=500
fi

###############################################################################
# 6. Persist sysctl settings across reboots
###############################################################################
echo "[kos-zram] Writing persistent sysctl to ${SYSCTL_CONF} ..."
if [ "$LOW_RAM" = true ]; then
    cat > "${SYSCTL_CONF}" <<SYSCTL
# KlipperOS-AI: zram-optimised VM tunables (low-ram mode)
vm.swappiness = ${SWAPPINESS}
vm.page-cluster = 0
vm.dirty_expire_centisecs = 3000
vm.dirty_writeback_centisecs = 1000
vm.dirty_ratio = 40
vm.vfs_cache_pressure = 200
vm.min_free_kbytes = 16384
SYSCTL
else
    cat > "${SYSCTL_CONF}" <<SYSCTL
# KlipperOS-AI: zram-optimised VM tunables
vm.swappiness = ${SWAPPINESS}
vm.page-cluster = 0
vm.dirty_expire_centisecs = 1500
vm.dirty_writeback_centisecs = 500
SYSCTL
fi

###############################################################################
# 7. Install earlyoom (best-effort)
###############################################################################
if command -v apt-get &>/dev/null; then
    echo "[kos-zram] Installing earlyoom (if available) ..."
    apt-get install -y earlyoom 2>/dev/null || true
elif command -v pacman &>/dev/null; then
    pacman -S --noconfirm earlyoom 2>/dev/null || true
fi

if command -v earlyoom &>/dev/null; then
    if [ "$LOW_RAM" = true ]; then
        # Dusuk RAM: agresif earlyoom — Klipper'i koru, UI/kamera feda et
        mkdir -p /etc/default
        cat > /etc/default/earlyoom << 'EOOM'
EARLYOOM_ARGS="-m 5 -s 5 --prefer '(crowsnest|KlipperScreen)' --avoid '(klipper|moonraker|nginx)' -r 60 -n
EOOM
        echo "[kos-zram] earlyoom: agresif mod (dusuk RAM)"
    fi
    systemctl enable --now earlyoom 2>/dev/null || true
else
    echo "[kos-zram] earlyoom not available -- skipping"
fi

echo "[kos-zram] Setup complete."
