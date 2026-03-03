#!/usr/bin/env bash
# =============================================================================
# KlipperOS-AI — CPU Affinity Drop-in Generator
# =============================================================================
# CPU cekirdek sayisina gore systemd drop-in dosyalari uretir.
# Klipper real-time thread'leri izole cekirdeklerde, AI ayri cekirdeklerde.
#
# | Core | Klipper | AI Monitor | Kamera/UI | Diger |
# |------|---------|-----------|-----------|-------|
# | 1    | (paylaşımlı — affinity yok)                      |
# | 2    | 0       | 1         | 1         | —     |
# | 4    | 0-1     | 2         | 3         | 3     |
# | 8+   | 0-1     | 2-3       | 4         | 5-7   |
#
# Cagiran: setup-os-tuning.sh (apply_cpu_affinity)
# =============================================================================

set -euo pipefail

CPU_CORES=$(nproc 2>/dev/null || echo 1)
DROP_DIR="/etc/systemd/system"

echo "[cpu-affinity] ${CPU_CORES} cekirdek tespit edildi"

# 1 veya 2 cekirdek icin affinity ayarlamak ters etki yapar
if [ "$CPU_CORES" -lt 4 ]; then
    echo "[cpu-affinity] ${CPU_CORES} cekirdek — affinity gereksiz, atlaniyor"
    exit 0
fi

###############################################################################
# Affinity hesapla
###############################################################################
if [ "$CPU_CORES" -ge 8 ]; then
    KLIPPER_CPUS="0-1"
    AI_CPUS="2-3"
    CAMERA_CPUS="4"
elif [ "$CPU_CORES" -ge 4 ]; then
    KLIPPER_CPUS="0-1"
    AI_CPUS="2"
    CAMERA_CPUS="3"
fi

echo "[cpu-affinity] Klipper=${KLIPPER_CPUS}, AI=${AI_CPUS}, Kamera=${CAMERA_CPUS}"

###############################################################################
# systemd drop-in: Klipper
###############################################################################
KLIPPER_DROP="${DROP_DIR}/klipper.service.d"
mkdir -p "$KLIPPER_DROP"
cat > "${KLIPPER_DROP}/cpu-affinity.conf" << EOF
# KlipperOS-AI: CPU affinity — Klipper real-time
[Service]
CPUAffinity=${KLIPPER_CPUS}
Nice=-5
EOF
echo "[cpu-affinity] Klipper drop-in: CPUAffinity=${KLIPPER_CPUS}"

###############################################################################
# systemd drop-in: AI Monitor
###############################################################################
AI_DROP="${DROP_DIR}/klipperos-ai-monitor.service.d"
mkdir -p "$AI_DROP"
cat > "${AI_DROP}/cpu-affinity.conf" << EOF
# KlipperOS-AI: CPU affinity — AI Monitor
[Service]
CPUAffinity=${AI_CPUS}
Nice=5
EOF
echo "[cpu-affinity] AI Monitor drop-in: CPUAffinity=${AI_CPUS}"

###############################################################################
# systemd drop-in: Crowsnest (kamera)
###############################################################################
CAMERA_DROP="${DROP_DIR}/crowsnest.service.d"
mkdir -p "$CAMERA_DROP"
cat > "${CAMERA_DROP}/cpu-affinity.conf" << EOF
# KlipperOS-AI: CPU affinity — Crowsnest (kamera)
[Service]
CPUAffinity=${CAMERA_CPUS}
Nice=10
EOF
echo "[cpu-affinity] Crowsnest drop-in: CPUAffinity=${CAMERA_CPUS}"

###############################################################################
# systemd reload
###############################################################################
systemctl daemon-reload 2>/dev/null || true
echo "[cpu-affinity] CPU affinity drop-in dosyalari olusturuldu ve daemon reload yapildi"
