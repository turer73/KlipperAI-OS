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
# Constants
###############################################################################
ZRAM_DEV="/dev/zram0"
SYSCTL_CONF="/etc/sysctl.d/99-kos-zram.conf"
COMP_ALGO="zstd"
SWAP_PRIORITY=100

###############################################################################
# 1. Load zram kernel module
###############################################################################
echo "[kos-zram] Loading zram kernel module ..."
modprobe zram num_devices=1

###############################################################################
# 2. Calculate 50% of total RAM (in bytes)
###############################################################################
TOTAL_KB=$(awk '/^MemTotal:/ { print $2 }' /proc/meminfo)
ZRAM_SIZE_BYTES=$(( TOTAL_KB * 1024 / 2 ))
echo "[kos-zram] Total RAM: ${TOTAL_KB} kB  ->  zram disk size: $(( ZRAM_SIZE_BYTES / 1024 / 1024 )) MB"

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
sysctl -w vm.swappiness=150
sysctl -w vm.page-cluster=0
sysctl -w vm.dirty_expire_centisecs=1500
sysctl -w vm.dirty_writeback_centisecs=500

###############################################################################
# 6. Persist sysctl settings across reboots
###############################################################################
echo "[kos-zram] Writing persistent sysctl to ${SYSCTL_CONF} ..."
cat > "${SYSCTL_CONF}" <<'SYSCTL'
# KlipperOS-AI: zram-optimised VM tunables
vm.swappiness = 150
vm.page-cluster = 0
vm.dirty_expire_centisecs = 1500
vm.dirty_writeback_centisecs = 500
SYSCTL

###############################################################################
# 7. Install earlyoom (best-effort)
###############################################################################
if command -v apt-get &>/dev/null; then
    echo "[kos-zram] Installing earlyoom (if available) ..."
    apt-get install -y earlyoom 2>/dev/null && systemctl enable --now earlyoom || \
        echo "[kos-zram] earlyoom not available in repos -- skipping"
elif command -v pacman &>/dev/null; then
    pacman -S --noconfirm earlyoom 2>/dev/null && systemctl enable --now earlyoom || \
        echo "[kos-zram] earlyoom not available -- skipping"
else
    echo "[kos-zram] Package manager not detected -- skipping earlyoom install"
fi

echo "[kos-zram] Setup complete."
