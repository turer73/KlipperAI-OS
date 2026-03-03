#!/usr/bin/env bash
# =============================================================================
# KlipperOS-AI — OS Tuning & Hardening
# =============================================================================
# Kernel parametreleri, dosya sistemi, journald, ag ve CPU affinity ayarları.
# Oneshot olarak calisir (boot'ta veya install sonrasi).
#
# Cagiran: kos-os-tuning.service  /  install-klipper-os.sh
# Referans: setup-zram.sh (ayni pattern)
# =============================================================================

set -euo pipefail

###############################################################################
# Guard: root gerekli
###############################################################################
if [[ $EUID -ne 0 ]]; then
    echo "ERROR: setup-os-tuning.sh root olarak calistirilmali" >&2
    exit 1
fi

###############################################################################
# Marker: tekrar calistirma korumasi
###############################################################################
MARKER="/etc/klipperos-ai/os-tuning-applied"
FORCE="${FORCE_REAPPLY:-0}"

if [ -f "$MARKER" ] && [ "$FORCE" != "1" ]; then
    echo "[kos-tuning] OS tuning zaten uygulanmis. Atlanıyor."
    echo "[kos-tuning] Tekrar uygulamak icin: FORCE_REAPPLY=1 $0"
    exit 0
fi

###############################################################################
# Donanim algilama
###############################################################################
CPU_CORES=$(nproc 2>/dev/null || echo 1)
TOTAL_KB=$(awk '/^MemTotal:/ { print $2 }' /proc/meminfo)
TOTAL_MB=$(( TOTAL_KB / 1024 ))
KERNEL_VER=$(uname -r | cut -d. -f1-2)

# Board tipi: rpi, sbc, x86
BOARD_TYPE="x86"
if [ -f /proc/device-tree/model ]; then
    DT_MODEL=$(tr -d '\0' < /proc/device-tree/model 2>/dev/null || echo "")
    if echo "$DT_MODEL" | grep -qi "raspberry"; then
        BOARD_TYPE="rpi"
    else
        BOARD_TYPE="sbc"
    fi
fi

# Dusuk RAM tespiti
LOW_RAM=false
if [ "$TOTAL_MB" -lt 2048 ]; then
    LOW_RAM=true
fi

echo "[kos-tuning] Donanim: ${BOARD_TYPE}, ${CPU_CORES} cekirdek, ${TOTAL_MB}MB RAM (kernel ${KERNEL_VER})"
echo "[kos-tuning] Dusuk RAM modu: ${LOW_RAM}"

###############################################################################
# 1. Kernel Boot Parametreleri
###############################################################################
apply_kernel_boot_params() {
    echo "[kos-tuning] Kernel boot parametreleri ayarlaniyor..."

    # Hedef parametreler
    local PARAMS="threadirqs consoleblank=0"

    # Kernel 6.x: PREEMPT_DYNAMIC destekli, 5.x: preempt=full
    local major minor
    major=$(echo "$KERNEL_VER" | cut -d. -f1)
    minor=$(echo "$KERNEL_VER" | cut -d. -f2)
    if [ "$major" -ge 6 ]; then
        PARAMS="$PARAMS preempt=full"
    fi

    if [ "$BOARD_TYPE" = "rpi" ]; then
        # RPi: /boot/firmware/cmdline.txt
        local CMDLINE="/boot/firmware/cmdline.txt"
        [ ! -f "$CMDLINE" ] && CMDLINE="/boot/cmdline.txt"

        if [ -f "$CMDLINE" ]; then
            local current
            current=$(cat "$CMDLINE")
            local changed=false
            for param in $PARAMS; do
                if ! echo "$current" | grep -q "$param"; then
                    current="$current $param"
                    changed=true
                fi
            done
            if [ "$changed" = true ]; then
                echo "$current" > "$CMDLINE"
                echo "[kos-tuning] RPi cmdline.txt guncellendi"
            fi
        fi
    else
        # x86/generic: /etc/default/grub
        local GRUB_CFG="/etc/default/grub"
        if [ -f "$GRUB_CFG" ]; then
            local current
            current=$(grep "^GRUB_CMDLINE_LINUX_DEFAULT=" "$GRUB_CFG" | sed 's/^GRUB_CMDLINE_LINUX_DEFAULT="//' | sed 's/"$//')
            local changed=false
            for param in $PARAMS; do
                if ! echo "$current" | grep -q "$param"; then
                    current="$current $param"
                    changed=true
                fi
            done
            if [ "$changed" = true ]; then
                sed -i "s|^GRUB_CMDLINE_LINUX_DEFAULT=.*|GRUB_CMDLINE_LINUX_DEFAULT=\"${current}\"|" "$GRUB_CFG"
                update-grub 2>/dev/null || true
                echo "[kos-tuning] GRUB cmdline guncellendi"
            fi
        fi
    fi

    # IO scheduler: NVMe/eMMC icin none, SD kart icin mq-deadline
    for disk in /sys/block/sd* /sys/block/mmcblk* /sys/block/nvme*; do
        [ ! -d "$disk" ] && continue
        local sched_file="$disk/queue/scheduler"
        [ ! -f "$sched_file" ] && continue

        local dev_name
        dev_name=$(basename "$disk")
        if echo "$dev_name" | grep -q "^nvme\|^mmcblk"; then
            echo "none" > "$sched_file" 2>/dev/null || true
        else
            echo "mq-deadline" > "$sched_file" 2>/dev/null || true
        fi
    done
    echo "[kos-tuning] IO scheduler ayarlandi"
}

###############################################################################
# 2. Dosya Sistemi Tuning
###############################################################################
apply_filesystem_tuning() {
    echo "[kos-tuning] Dosya sistemi ayarlari uygulanıyor..."

    # /etc/fstab: root mount'a noatime,commit=60 ekle
    if [ -f /etc/fstab ]; then
        # Sadece root (/) mount noktasini guncelle — ext4 veya btrfs
        if grep -qE '^\S+\s+/\s+(ext4|btrfs)' /etc/fstab; then
            if ! grep -qE '^\S+\s+/\s+\S+\s+\S*noatime' /etc/fstab; then
                sed -i -E 's|^(\S+\s+/\s+(ext4\|btrfs)\s+)(\S+)|\1\3,noatime,commit=60|' /etc/fstab
                echo "[kos-tuning] fstab: noatime,commit=60 eklendi"
            fi
        fi
    fi

    # AI loglari icin tmpfs (RAM'de, shutdown'da persist)
    local AI_LOG_DIR="/var/log/klipperos-ai"
    mkdir -p "$AI_LOG_DIR"

    if ! grep -q "klipperos-ai" /etc/fstab 2>/dev/null; then
        echo "# KlipperOS-AI: AI loglari RAM'de" >> /etc/fstab
        echo "tmpfs ${AI_LOG_DIR} tmpfs defaults,noatime,nosuid,nodev,noexec,size=32M,mode=0755 0 0" >> /etc/fstab
        mount -a 2>/dev/null || true
        echo "[kos-tuning] tmpfs: ${AI_LOG_DIR} (32MB) eklendi"
    fi

    # Log persist servisi (shutdown'da /var/log/klipperos-ai -> disk)
    cat > /etc/systemd/system/kos-log-persist.service << 'SERVICE'
[Unit]
Description=KlipperOS-AI Log Persist (shutdown)
DefaultDependencies=no
Before=shutdown.target reboot.target halt.target

[Service]
Type=oneshot
ExecStart=/bin/bash -c 'cp -a /var/log/klipperos-ai/* /opt/klipperos-ai/logs/ 2>/dev/null || true'

[Install]
WantedBy=halt.target reboot.target shutdown.target
SERVICE
    mkdir -p /opt/klipperos-ai/logs
    systemctl daemon-reload
    systemctl enable kos-log-persist.service 2>/dev/null || true
}

###############################################################################
# 3. Journald Limitleri
###############################################################################
apply_journald_limits() {
    echo "[kos-tuning] Journald limitleri ayarlaniyor..."

    mkdir -p /etc/systemd/journald.conf.d
    cat > /etc/systemd/journald.conf.d/kos.conf << 'JOURNALD'
# KlipperOS-AI: journal boyut siniri
[Journal]
SystemMaxUse=50M
RuntimeMaxUse=30M
MaxFileSec=1day
ForwardToSyslog=no
JOURNALD

    # Dusuk RAM'de daha agresif
    if [ "$LOW_RAM" = true ]; then
        cat > /etc/systemd/journald.conf.d/kos.conf << 'JOURNALD'
# KlipperOS-AI: journal boyut siniri (dusuk RAM)
[Journal]
SystemMaxUse=20M
RuntimeMaxUse=10M
MaxFileSec=6h
ForwardToSyslog=no
Storage=volatile
JOURNALD
    fi

    systemctl restart systemd-journald 2>/dev/null || true
    echo "[kos-tuning] Journald limitleri uygulandı"
}

###############################################################################
# 4. Ag (Network) Tuning
###############################################################################
apply_network_tuning() {
    echo "[kos-tuning] Ag ayarlari uygulanıyor..."

    local SYSCTL_NET="/etc/sysctl.d/99-kos-network.conf"
    cat > "$SYSCTL_NET" << 'SYSCTL'
# KlipperOS-AI: Network tuning
net.core.somaxconn = 256
net.ipv4.tcp_fastopen = 3
net.ipv4.tcp_tw_reuse = 1
net.core.netdev_max_backlog = 1000
SYSCTL

    sysctl -p "$SYSCTL_NET" 2>/dev/null || true

    # IPv6 devre disi birak (global adres yoksa)
    local has_ipv6_global=false
    if ip -6 addr show scope global 2>/dev/null | grep -q "inet6"; then
        has_ipv6_global=true
    fi

    if [ "$has_ipv6_global" = false ]; then
        cat > /etc/sysctl.d/99-kos-disable-ipv6.conf << 'SYSCTL'
# KlipperOS-AI: IPv6 devre disi (global adres yok)
net.ipv6.conf.all.disable_ipv6 = 1
net.ipv6.conf.default.disable_ipv6 = 1
SYSCTL
        sysctl -p /etc/sysctl.d/99-kos-disable-ipv6.conf 2>/dev/null || true
        echo "[kos-tuning] IPv6 devre disi birakildi (global adres yok)"
    else
        echo "[kos-tuning] IPv6 aktif tutuldu (global adres mevcut)"
    fi
}

###############################################################################
# 5. CPU Affinity (cekirdek 4+ ise)
###############################################################################
apply_cpu_affinity() {
    if [ "$CPU_CORES" -lt 4 ]; then
        echo "[kos-tuning] CPU affinity atlanıyor (${CPU_CORES} cekirdek < 4)"
        return 0
    fi

    echo "[kos-tuning] CPU affinity ayarlaniyor (${CPU_CORES} cekirdek)..."

    local SCRIPT_DIR
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    local GEN_SCRIPT="${SCRIPT_DIR}/generate-cpu-affinity.sh"

    if [ -x "$GEN_SCRIPT" ]; then
        bash "$GEN_SCRIPT"
        echo "[kos-tuning] CPU affinity drop-in dosyalari olusturuldu"
    else
        echo "[kos-tuning] UYARI: generate-cpu-affinity.sh bulunamadi"
    fi
}

###############################################################################
# 6. Ek Kernel Runtime Parametreleri
###############################################################################
apply_runtime_kernel_params() {
    echo "[kos-tuning] Runtime kernel parametreleri uygulanıyor..."

    local SYSCTL_KERN="/etc/sysctl.d/99-kos-kernel.conf"
    cat > "$SYSCTL_KERN" << 'SYSCTL'
# KlipperOS-AI: Kernel runtime tuning
kernel.sched_rt_runtime_us = 980000
kernel.sched_autogroup_enabled = 0
SYSCTL

    # Dusuk RAM: ek ayarlar
    if [ "$LOW_RAM" = true ]; then
        cat >> "$SYSCTL_KERN" << 'SYSCTL'
# Dusuk RAM ek ayarlar
kernel.printk = 3 4 1 3
SYSCTL
    fi

    sysctl -p "$SYSCTL_KERN" 2>/dev/null || true
}

###############################################################################
# ANA FONKSIYON
###############################################################################
main() {
    echo "=============================================="
    echo "  KlipperOS-AI — OS Tuning & Hardening"
    echo "=============================================="

    apply_kernel_boot_params
    apply_filesystem_tuning
    apply_journald_limits
    apply_network_tuning
    apply_cpu_affinity
    apply_runtime_kernel_params

    # Marker olustur
    mkdir -p /etc/klipperos-ai
    date -Iseconds > "$MARKER"
    echo "[kos-tuning] Tamamlandi. Marker: $MARKER"

    # Bazi ayarlar reboot gerektiriyor
    echo "[kos-tuning] NOT: Kernel boot parametreleri sonraki reboot'ta aktif olacak."
    echo "[kos-tuning] OS tuning basariyla uygulandı."
}

main "$@"
