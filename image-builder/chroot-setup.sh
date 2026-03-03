#!/bin/bash
# =============================================================================
# KlipperOS-AI — Chroot Sistem Yapilandirmasi
# =============================================================================
# debootstrap rootfs icinde calistirilir. Kullanici, servisler, ayarlar.
# Cagiran: build-minimal-image.sh (FAZ 4)
# =============================================================================

set -euo pipefail

echo "[SETUP] KlipperOS-AI sistem yapilandirmasi basliyor..."

# --- klipper kullanicisi ---
if ! id -u klipper &>/dev/null; then
    useradd -m -s /bin/bash -G sudo,tty,dialout,video,plugdev klipper
    echo "klipper:klipper" | chpasswd
    echo "[SETUP] klipper kullanicisi olusturuldu (varsayilan sifre: klipper)"
fi

# --- sudoers (sifresiz systemctl, reboot, shutdown, nmcli, apt) ---
cat > /etc/sudoers.d/klipperos << 'SUDOERS'
# KlipperAI-OS sudoers
klipper ALL=(ALL) NOPASSWD: /usr/bin/systemctl
klipper ALL=(ALL) NOPASSWD: /usr/sbin/reboot
klipper ALL=(ALL) NOPASSWD: /usr/sbin/shutdown
klipper ALL=(ALL) NOPASSWD: /usr/sbin/poweroff
klipper ALL=(ALL) NOPASSWD: /usr/bin/nmcli
klipper ALL=(ALL) NOPASSWD: /usr/bin/tailscale
klipper ALL=(ALL) NOPASSWD: /usr/bin/apt-get
klipper ALL=(ALL) NOPASSWD: /usr/bin/dpkg
SUDOERS
chmod 440 /etc/sudoers.d/klipperos

# --- Klipper dizin yapisi ---
KLIPPER_HOME="/home/klipper"
sudo -u klipper mkdir -p "${KLIPPER_HOME}/printer_data/config"
sudo -u klipper mkdir -p "${KLIPPER_HOME}/printer_data/logs"
sudo -u klipper mkdir -p "${KLIPPER_HOME}/printer_data/gcodes"
sudo -u klipper mkdir -p "${KLIPPER_HOME}/printer_data/database"

# --- Hostname ---
echo "klipperos" > /etc/hostname
sed -i 's/127.0.1.1.*/127.0.1.1\tklipperos/' /etc/hosts 2>/dev/null || \
    echo "127.0.1.1	klipperos" >> /etc/hosts

# --- Locale (Turkce + English) ---
sed -i 's/# tr_TR.UTF-8/tr_TR.UTF-8/' /etc/locale.gen 2>/dev/null || true
sed -i 's/# en_US.UTF-8/en_US.UTF-8/' /etc/locale.gen 2>/dev/null || true
locale-gen 2>/dev/null || true

# --- Timezone ---
ln -sf /usr/share/zoneinfo/Europe/Istanbul /etc/localtime
echo "Europe/Istanbul" > /etc/timezone

# --- tty1 autologin (live session icin) ---
mkdir -p /etc/systemd/system/getty@tty1.service.d
cat > /etc/systemd/system/getty@tty1.service.d/autologin.conf << 'AUTOLOGIN'
[Service]
ExecStart=
ExecStart=-/sbin/agetty --autologin klipper --noclear %I $TERM
AUTOLOGIN

# --- SSH servisini etkinlestir ---
systemctl enable ssh 2>/dev/null || true

# --- NetworkManager etkinlestir ---
systemctl enable NetworkManager 2>/dev/null || true

# --- earlyoom etkinlestir ---
systemctl enable earlyoom 2>/dev/null || true

# --- Avahi (mDNS) etkinlestir ---
systemctl enable avahi-daemon 2>/dev/null || true

# --- Gereksiz servisleri devre disi birak ---
systemctl disable apt-daily.timer 2>/dev/null || true
systemctl disable apt-daily-upgrade.timer 2>/dev/null || true

# --- /opt/klipperos-ai izinleri ---
chown -R klipper:klipper /opt/klipperos-ai 2>/dev/null || true
chmod +x /opt/klipperos-ai/scripts/*.sh 2>/dev/null || true

echo "[SETUP] KlipperOS-AI sistem yapilandirmasi tamamlandi."
