# KlipperAI-OS Image Builder Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Debian Live Build ile x86/PC icin bootable USB imaji ureten build sistemi ve ilk boot wizard'i olusturmak.

**Architecture:** `image-builder/` dizininde Debian Live Build config dosyalari + `build-image.sh` ana script. `first-boot-wizard.sh` whiptail TUI ile donanim algilama, profil secimi, ag ayarlari ve kurulum. Build sirasinda proje dosyalari imaja kopyalanir, ilk boot'ta internet uzerinden Klipper/Moonraker kurulur.

**Tech Stack:** Debian Live Build (lb), bash, whiptail, systemd, GRUB

---

### Task 1: Dizin Yapisi ve Build Script Iskeleti

**Files:**
- Create: `image-builder/build-image.sh`
- Create: `image-builder/config/package-lists/klipperos.list.chroot`

**Amac:** `lb config` + `lb build` cagiran ana build scripti ve paket listesi.

**build-image.sh icerigi:**

```bash
#!/bin/bash
# =============================================================================
# KlipperAI-OS — Image Builder
# =============================================================================
# Debian Live Build ile x86/PC bootable USB imaji uretir.
#
# Gereksinimler:
#   sudo apt-get install live-build
#
# Kullanim:
#   sudo ./build-image.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${SCRIPT_DIR}/build"
VERSION="2.1.0"
IMAGE_NAME="klipperai-os-x86-v${VERSION}"

CYAN='\033[0;36m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[BUILD]${NC} $*"; }
warn() { echo -e "${YELLOW}[BUILD]${NC} $*"; }
err() { echo -e "${RED}[BUILD]${NC} $*" >&2; }

# --- Root kontrolu ---
if [ "$(id -u)" -ne 0 ]; then
    err "Root yetkisi gerekli: sudo $0"
    exit 1
fi

# --- live-build kontrolu ---
if ! command -v lb &>/dev/null; then
    err "live-build kurulu degil. Kuruluyor..."
    apt-get update && apt-get install -y live-build
fi

# --- Temiz baslangic ---
log "Build dizini hazirlaniyor: ${BUILD_DIR}"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# Onceki build varsa temizle
if [ -d ".build" ] || [ -f "live-image-amd64.hybrid.iso" ]; then
    log "Onceki build temizleniyor..."
    lb clean --purge 2>/dev/null || true
fi

# --- lb config ---
log "Debian Live Build yapilandiriliyor..."
lb config \
    --distribution bookworm \
    --architectures amd64 \
    --binary-images iso-hybrid \
    --bootloaders "grub-efi,syslinux" \
    --debian-installer none \
    --memtest none \
    --iso-application "KlipperAI-OS" \
    --iso-volume "KlipperAI-OS v${VERSION}" \
    --apt-recommends false \
    --security true \
    --updates true \
    --cache true

# --- Paket listesi kopyala ---
log "Paket listesi kopyalaniyor..."
cp "${SCRIPT_DIR}/config/package-lists/klipperos.list.chroot" \
    "${BUILD_DIR}/config/package-lists/"

# --- includes.chroot: proje dosyalarini kopyala ---
log "Proje dosyalari kopyalaniyor..."
local CHROOT="${BUILD_DIR}/config/includes.chroot"
mkdir -p "${CHROOT}/opt/klipperos-ai"

# Proje dosyalari
for dir in scripts ai-monitor config tools ks-panels data; do
    if [ -d "${PROJECT_ROOT}/${dir}" ]; then
        cp -r "${PROJECT_ROOT}/${dir}" "${CHROOT}/opt/klipperos-ai/"
    fi
done

# pyproject.toml ve README
cp "${PROJECT_ROOT}/pyproject.toml" "${CHROOT}/opt/klipperos-ai/" 2>/dev/null || true
cp "${PROJECT_ROOT}/README.md" "${CHROOT}/opt/klipperos-ai/" 2>/dev/null || true

# Calistirilabilir izinler
chmod +x "${CHROOT}/opt/klipperos-ai/scripts/"*.sh 2>/dev/null || true

# --- First boot wizard ---
log "First boot wizard kopyalaniyor..."
mkdir -p "${CHROOT}/usr/local/bin"
cp "${SCRIPT_DIR}/first-boot-wizard.sh" "${CHROOT}/usr/local/bin/klipperai-wizard"
chmod +x "${CHROOT}/usr/local/bin/klipperai-wizard"

# Sentinel dosyasi (wizard sadece ilk boot'ta calisir)
touch "${CHROOT}/opt/klipperos-ai/.first-boot"

# --- Systemd service ---
mkdir -p "${CHROOT}/etc/systemd/system"
cp "${SCRIPT_DIR}/config/includes.chroot/etc/systemd/system/klipperai-first-boot.service" \
    "${CHROOT}/etc/systemd/system/"

# --- Hook: build icinde kullanici olusturma ---
log "Build hook kopyalaniyor..."
mkdir -p "${BUILD_DIR}/config/hooks/live"
cp "${SCRIPT_DIR}/config/hooks/live/0100-setup.hook.chroot" \
    "${BUILD_DIR}/config/hooks/live/"
chmod +x "${BUILD_DIR}/config/hooks/live/0100-setup.hook.chroot"

# --- GRUB config ---
log "GRUB yapilandirmasi kopyalaniyor..."
mkdir -p "${BUILD_DIR}/config/bootloaders/grub-pc"
cp "${SCRIPT_DIR}/config/bootloaders/grub/grub.cfg" \
    "${BUILD_DIR}/config/bootloaders/grub-pc/grub.cfg" 2>/dev/null || true

# --- BUILD ---
log "Imaj olusturuluyor... (bu islem 15-30 dakika surebilir)"
lb build 2>&1 | tee "${BUILD_DIR}/build.log"

# --- Cikti ---
if [ -f "${BUILD_DIR}/live-image-amd64.hybrid.iso" ]; then
    mv "${BUILD_DIR}/live-image-amd64.hybrid.iso" "${SCRIPT_DIR}/${IMAGE_NAME}.img"
    local size
    size=$(du -h "${SCRIPT_DIR}/${IMAGE_NAME}.img" | cut -f1)
    echo ""
    log "Imaj olusturuldu!"
    log "Dosya: ${SCRIPT_DIR}/${IMAGE_NAME}.img"
    log "Boyut: ${size}"
    echo ""
    echo -e "${GREEN}USB'ye yazmak icin:${NC}"
    echo "  sudo dd if=${IMAGE_NAME}.img of=/dev/sdX bs=4M status=progress"
    echo "  veya Balena Etcher / Rufus kullanin."
else
    err "Imaj olusturulamadi! build.log dosyasini kontrol edin."
    exit 1
fi
```

**klipperos.list.chroot icerigi:**

```
# =============================================================================
# KlipperAI-OS — Paket Listesi (Debian Bookworm amd64)
# =============================================================================

# --- Temel Sistem ---
sudo
openssh-server
curl
wget
ca-certificates
gnupg
lsb-release
apt-transport-https
software-properties-common

# --- Network ---
network-manager
wpasupplicant
avahi-daemon
avahi-utils

# --- Python ---
python3
python3-venv
python3-pip
python3-dev
python3-setuptools
python3-wheel

# --- Build Tools (Klipper firmware derleme) ---
git
build-essential
cmake
gcc-arm-none-eabi
binutils-arm-none-eabi
libnewlib-arm-none-eabi
stm32flash
dfu-util
avrdude
pkg-config

# --- Display / GTK (KlipperScreen) ---
xserver-xorg
xinit
x11-xserver-utils
python3-gi
python3-gi-cairo
gir1.2-gtk-3.0
gir1.2-vte-2.91
libopenjp2-7
libcairo2-dev
fonts-freefont-ttf
xinput
matchbox-keyboard

# --- Web Server ---
nginx

# --- Sistem Araclari ---
python3-psutil
whiptail
htop
nano
less
zstd
earlyoom
usbutils
pciutils
v4l-utils
ffmpeg

# --- Klipper CANBUS ---
can-utils

# --- Wizard bagimliliklari ---
parted
dosfstools
rsync
```

**Test:**

```bash
# Syntax kontrolu
bash -n image-builder/build-image.sh && echo "OK"
# Paket listesi format kontrolu (bos satir ve yorum satiri disinda hepsi paket adi)
grep -v '^#\|^$' image-builder/config/package-lists/klipperos.list.chroot | head -5
```

**Commit:**

```bash
git add image-builder/build-image.sh image-builder/config/package-lists/klipperos.list.chroot
git commit -m "feat: add image builder skeleton with lb config and package list"
```

---

### Task 2: Build Hook (Chroot icinde sistem kurulumu)

**Files:**
- Create: `image-builder/config/hooks/live/0100-setup.hook.chroot`

**Amac:** Build sirasinda chroot icinde calisir: `klipper` kullanici olusturma, dizin yapisi, sudoers, locale, hostname.

**0100-setup.hook.chroot icerigi:**

```bash
#!/bin/bash
# =============================================================================
# KlipperAI-OS — Build Hook (chroot icinde calisir)
# =============================================================================
# lb build sirasinda calistirilir. Kullanici, dizin, ayar yapilandirmasi.
# =============================================================================

set -euo pipefail

echo "[HOOK] KlipperAI-OS sistem yapilandirmasi basliyor..."

# --- klipper kullanicisi ---
if ! id -u klipper &>/dev/null; then
    useradd -m -s /bin/bash -G sudo,tty,dialout,video,plugdev klipper
    echo "klipper:klipper" | chpasswd
    echo "[HOOK] klipper kullanicisi olusturuldu (varsayilan sifre: klipper)"
fi

# --- sudoers (sifresiz systemctl, reboot, shutdown) ---
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

# --- First boot wizard servisini etkinlestir ---
systemctl enable klipperai-first-boot.service 2>/dev/null || true

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

echo "[HOOK] KlipperAI-OS sistem yapilandirmasi tamamlandi."
```

**Test:**

```bash
bash -n image-builder/config/hooks/live/0100-setup.hook.chroot && echo "OK"
```

**Commit:**

```bash
git add image-builder/config/hooks/live/0100-setup.hook.chroot
git commit -m "feat: add build hook for user creation, sudoers, locale setup"
```

---

### Task 3: First Boot Systemd Service

**Files:**
- Create: `image-builder/config/includes.chroot/etc/systemd/system/klipperai-first-boot.service`

**Amac:** Wizard'i sadece ilk boot'ta calistiran oneshot systemd servisi.

**klipperai-first-boot.service icerigi:**

```ini
[Unit]
Description=KlipperAI-OS First Boot Setup Wizard
After=network-online.target
Wants=network-online.target
ConditionPathExists=/opt/klipperos-ai/.first-boot

[Service]
Type=oneshot
ExecStart=/usr/local/bin/klipperai-wizard
ExecStartPost=/bin/rm -f /opt/klipperos-ai/.first-boot
StandardInput=tty
StandardOutput=tty
TTYPath=/dev/tty1
RemainAfterExit=no
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

**Test:**

```bash
# systemd unit syntax kontrolu (basit grep)
grep -c "^\[" image-builder/config/includes.chroot/etc/systemd/system/klipperai-first-boot.service
# Beklenen: 3 ([Unit], [Service], [Install])
```

**Commit:**

```bash
git add image-builder/config/includes.chroot/etc/systemd/system/klipperai-first-boot.service
git commit -m "feat: add first-boot wizard systemd service"
```

---

### Task 4: First Boot Wizard — Ana Script

**Files:**
- Create: `image-builder/first-boot-wizard.sh`

**Amac:** whiptail TUI ile tam ilk boot deneyimi. Bu en buyuk task — 6 asamali wizard.

**first-boot-wizard.sh icerigi:**

```bash
#!/bin/bash
# =============================================================================
# KlipperAI-OS — First Boot Wizard
# =============================================================================
# Ilk boot'ta calisir. Donanim algilar, profil onerir, ag ayarlarini yapar,
# istege bagli diske kurar, profil installer'i calistirir.
# =============================================================================

set -euo pipefail

export TERM=linux
export NEWT_COLORS='
root=,blue
window=,black
border=white,black
textbox=white,black
button=black,cyan
actbutton=black,cyan
compactbutton=white,black
title=cyan,black
roottext=cyan,blue
emptyscale=,black
fullscale=,cyan
entry=white,black
checkbox=white,black
actcheckbox=black,cyan
listbox=white,black
actlistbox=black,cyan
actsellistbox=black,cyan
'

VERSION="2.1.0"
BACKTITLE="KlipperAI-OS v${VERSION} Kurulum Sihirbazi"
LOG_FILE="/var/log/klipperai-wizard.log"
KLIPPER_HOME="/home/klipper"
INSTALL_DIR="/opt/klipperos-ai"

log() { echo "[$(date '+%H:%M:%S')] $*" >> "$LOG_FILE"; }

# ===================================================================
# Adim 1: Hosgeldin
# ===================================================================
step_welcome() {
    whiptail --backtitle "$BACKTITLE" \
        --title "KlipperAI-OS'e Hosgeldiniz!" \
        --msgbox "\
  _  _  _ _                      _    ___
 | |/ /| (_)_ __  _ __   ___ _ _/_\  |_ _|
 | ' / | | | '_ \| '_ \ / _ \ '_/ _ \ | |
 | . \ | | | |_) | |_) |  __/ |/ ___ \| |
 |_|\_\|_|_| .__/| .__/ \___|_/_/   \_\___|
            |_|   |_|     OS v${VERSION}

  AI-Powered 3D Printer Operating System

  Bu sihirbaz sisteminizi yapilandiracak:
  1. Donanim algilama
  2. Kurulum profili secimi
  3. Ag ayarlari
  4. Diske kurulum (istege bagli)
  5. Yazilim kurulumu

  Devam etmek icin OK'a basin." \
        20 60
    log "Wizard basladi"
}

# ===================================================================
# Adim 2: Donanim Algilama
# ===================================================================
step_detect_hardware() {
    log "Donanim algilaniyor..."

    # RAM
    TOTAL_RAM_MB=$(( $(grep MemTotal /proc/meminfo | awk '{print $2}') / 1024 ))

    # CPU
    CPU_CORES=$(nproc 2>/dev/null || echo 1)
    CPU_MODEL=$(grep -m1 "model name" /proc/cpuinfo 2>/dev/null | cut -d: -f2 | xargs || echo "Bilinmiyor")

    # Disk
    ROOT_DISK_MB=$(df -BM / | awk 'NR==2{print $2}' | tr -d 'M')

    # Ag
    HAS_WIFI="Hayir"
    [ -d /sys/class/net/wlan0/wireless ] 2>/dev/null && HAS_WIFI="Evet"
    for iface in /sys/class/net/*/wireless; do
        [ -d "$iface" ] && HAS_WIFI="Evet" && break
    done

    HAS_ETHERNET="Hayir"
    for iface in /sys/class/net/eth* /sys/class/net/en*; do
        [ -e "$iface" ] && HAS_ETHERNET="Evet" && break
    done

    # Profil onerisi
    RECOMMENDED_PROFILE="LIGHT"
    if [ "$TOTAL_RAM_MB" -ge 4096 ] && [ "$CPU_CORES" -ge 4 ]; then
        RECOMMENDED_PROFILE="FULL"
    elif [ "$TOTAL_RAM_MB" -ge 1536 ]; then
        RECOMMENDED_PROFILE="STANDARD"
    fi

    # RAM < 1.5GB ise sadece LIGHT
    FORCE_LIGHT=false
    if [ "$TOTAL_RAM_MB" -lt 1536 ]; then
        FORCE_LIGHT=true
    fi

    log "RAM=${TOTAL_RAM_MB}MB CPU=${CPU_CORES} Disk=${ROOT_DISK_MB}MB Oneri=${RECOMMENDED_PROFILE}"

    whiptail --backtitle "$BACKTITLE" \
        --title "Donanim Algilama Sonuclari" \
        --msgbox "\
  CPU:       ${CPU_MODEL}
  Cekirdek:  ${CPU_CORES}
  RAM:       ${TOTAL_RAM_MB} MB
  Disk:      ${ROOT_DISK_MB} MB
  WiFi:      ${HAS_WIFI}
  Ethernet:  ${HAS_ETHERNET}

  Onerilen Profil: ${RECOMMENDED_PROFILE}" \
        16 60
}

# ===================================================================
# Adim 3: Profil Secimi
# ===================================================================
step_select_profile() {
    if [ "$FORCE_LIGHT" = true ]; then
        SELECTED_PROFILE="LIGHT"
        whiptail --backtitle "$BACKTITLE" \
            --title "Profil Secimi" \
            --msgbox "\
  RAM: ${TOTAL_RAM_MB} MB (< 1.5 GB)

  Yetersiz RAM nedeniyle sadece LIGHT profil
  kurulabilir.

  LIGHT: Klipper + Moonraker + Mainsail" \
            12 55
        log "Profil: LIGHT (zorunlu — dusuk RAM)"
        return
    fi

    local default_item="2"
    case "$RECOMMENDED_PROFILE" in
        LIGHT)    default_item="1" ;;
        STANDARD) default_item="2" ;;
        FULL)     default_item="3" ;;
    esac

    SELECTED_PROFILE=$(whiptail --backtitle "$BACKTITLE" \
        --title "Kurulum Profili Secin" \
        --default-item "$default_item" \
        --menu "\
  Donanim: ${TOTAL_RAM_MB}MB RAM, ${CPU_CORES} cekirdek
  Onerilen: ${RECOMMENDED_PROFILE}\n" \
        18 65 3 \
        "1" "LIGHT    — Klipper + Moonraker + Mainsail (512MB+)" \
        "2" "STANDARD — + KlipperScreen + Kamera + AI (2GB+)" \
        "3" "FULL     — + Multi-printer + Timelapse (4GB+)" \
        3>&1 1>&2 2>&3) || SELECTED_PROFILE="$default_item"

    case "$SELECTED_PROFILE" in
        1) SELECTED_PROFILE="LIGHT" ;;
        2) SELECTED_PROFILE="STANDARD" ;;
        3) SELECTED_PROFILE="FULL" ;;
    esac

    log "Profil: ${SELECTED_PROFILE}"
}

# ===================================================================
# Adim 4: Ag Ayarlari
# ===================================================================
step_network() {
    # Ethernet varsa ve bagliysa atla
    if ip route get 1.1.1.1 &>/dev/null; then
        whiptail --backtitle "$BACKTITLE" \
            --title "Ag Baglantisi" \
            --msgbox "Internet baglantisi mevcut. Devam ediliyor." \
            8 50
        log "Ag: zaten bagli"
        return
    fi

    # WiFi varsa SSID sor
    if [ "$HAS_WIFI" = "Evet" ]; then
        # nmcli ile tarama
        local wifi_list
        wifi_list=$(nmcli -t -f SSID,SIGNAL dev wifi list 2>/dev/null | head -10 | sort -t: -k2 -rn)

        if [ -z "$wifi_list" ]; then
            whiptail --backtitle "$BACKTITLE" \
                --title "WiFi" \
                --msgbox "WiFi agi bulunamadi. Ethernet kablo baglayin veya WiFi'yi sonra yapilandirin." \
                8 60
            return
        fi

        # Menu icin SSID listesi
        local menu_items=()
        local idx=1
        while IFS=: read -r ssid signal; do
            [ -z "$ssid" ] && continue
            menu_items+=("$idx" "${ssid} (${signal}%)")
            idx=$((idx + 1))
        done <<< "$wifi_list"

        local choice
        choice=$(whiptail --backtitle "$BACKTITLE" \
            --title "WiFi Agi Secin" \
            --menu "Baglanilacak agi secin:" \
            18 60 8 \
            "${menu_items[@]}" \
            3>&1 1>&2 2>&3) || return

        # Secilen SSID
        local selected_ssid
        selected_ssid=$(echo "$wifi_list" | sed -n "${choice}p" | cut -d: -f1)

        # Sifre
        local wifi_pass
        wifi_pass=$(whiptail --backtitle "$BACKTITLE" \
            --title "WiFi Sifresi" \
            --passwordbox "${selected_ssid} icin sifre:" \
            10 50 \
            3>&1 1>&2 2>&3) || return

        # Baglan
        log "WiFi baglaniyor: ${selected_ssid}"
        if nmcli dev wifi connect "$selected_ssid" password "$wifi_pass" 2>/dev/null; then
            whiptail --backtitle "$BACKTITLE" \
                --title "WiFi" \
                --msgbox "Baglanti basarili: ${selected_ssid}" \
                8 50
            log "WiFi baglandi: ${selected_ssid}"
        else
            whiptail --backtitle "$BACKTITLE" \
                --title "WiFi Hatasi" \
                --msgbox "Baglanti basarisiz. Sifre yanlis olabilir.\nKurulum sonrasi tekrar deneyebilirsiniz." \
                10 55
            log "WiFi basarisiz: ${selected_ssid}"
        fi
    else
        whiptail --backtitle "$BACKTITLE" \
            --title "Ag Baglantisi" \
            --msgbox "WiFi algilanamiyor. Ethernet kablo baglayin.\nKurulum icin internet gerekli." \
            8 55
    fi
}

# ===================================================================
# Adim 5: Kullanici Ayarlari
# ===================================================================
step_user_settings() {
    # Hostname
    local new_hostname
    new_hostname=$(whiptail --backtitle "$BACKTITLE" \
        --title "Hostname" \
        --inputbox "Cihaz adi (hostname):" \
        10 50 "klipperos" \
        3>&1 1>&2 2>&3) || new_hostname="klipperos"

    if [ -n "$new_hostname" ] && [ "$new_hostname" != "klipperos" ]; then
        echo "$new_hostname" > /etc/hostname
        sed -i "s/klipperos/${new_hostname}/g" /etc/hosts 2>/dev/null || true
        hostnamectl set-hostname "$new_hostname" 2>/dev/null || true
        log "Hostname: ${new_hostname}"
    fi

    # klipper kullanici sifresi
    local user_pass
    user_pass=$(whiptail --backtitle "$BACKTITLE" \
        --title "Kullanici Sifresi" \
        --passwordbox "'klipper' kullanicisi icin yeni sifre\n(bos birakirsaniz varsayilan: klipper):" \
        10 55 \
        3>&1 1>&2 2>&3) || user_pass=""

    if [ -n "$user_pass" ]; then
        echo "klipper:${user_pass}" | chpasswd
        log "klipper sifresi degistirildi"
    fi
}

# ===================================================================
# Adim 6: Diske Kurulum (Istege Bagli)
# ===================================================================
step_disk_install() {
    local do_install
    do_install=$(whiptail --backtitle "$BACKTITLE" \
        --title "Diske Kurulum" \
        --menu "Kurulum tipi secin:" \
        14 60 3 \
        "1" "Diske kur (kalici kurulum)" \
        "2" "Live olarak devam et (RAM'de calis)" \
        3>&1 1>&2 2>&3) || do_install="2"

    if [ "$do_install" = "2" ]; then
        log "Live mod secildi"
        return
    fi

    # Disk listesi
    local disks
    disks=$(lsblk -dpno NAME,SIZE,TYPE | grep "disk" | grep -v "loop\|sr\|ram")

    if [ -z "$disks" ]; then
        whiptail --backtitle "$BACKTITLE" \
            --title "Hata" \
            --msgbox "Kurulum icin uygun disk bulunamadi." \
            8 50
        return
    fi

    local disk_items=()
    while read -r name size _type; do
        disk_items+=("$name" "${size}")
    done <<< "$disks"

    local target_disk
    target_disk=$(whiptail --backtitle "$BACKTITLE" \
        --title "Hedef Disk Secin" \
        --menu "UYARI: Secilen diskteki TUM VERILER SILINECEK!" \
        16 60 5 \
        "${disk_items[@]}" \
        3>&1 1>&2 2>&3) || return

    # Onay
    if ! whiptail --backtitle "$BACKTITLE" \
        --title "ONAY" \
        --yesno "UYARI!\n\n${target_disk} diskteki TUM VERILER SILINECEK.\n\nDevam etmek istiyor musunuz?" \
        12 55; then
        log "Disk kurulumu iptal edildi"
        return
    fi

    log "Diske kurulum basliyor: ${target_disk}"

    # Partitioning
    {
        echo "10"; echo "# Disk bolumlendiriliyor..."
        parted -s "$target_disk" mklabel gpt
        parted -s "$target_disk" mkpart ESP fat32 1MiB 512MiB
        parted -s "$target_disk" set 1 esp on
        parted -s "$target_disk" mkpart primary ext4 512MiB 100%

        echo "20"; echo "# Dosya sistemleri olusturuluyor..."
        mkfs.fat -F 32 "${target_disk}1" 2>/dev/null || mkfs.fat -F 32 "${target_disk}p1"
        mkfs.ext4 -F "${target_disk}2" 2>/dev/null || mkfs.ext4 -F "${target_disk}p2"

        echo "30"; echo "# Dosyalar kopyalaniyor..."
        local mount_root="/mnt/klipperai"
        mkdir -p "${mount_root}"
        mount "${target_disk}2" "${mount_root}" 2>/dev/null || mount "${target_disk}p2" "${mount_root}"
        mkdir -p "${mount_root}/boot/efi"
        mount "${target_disk}1" "${mount_root}/boot/efi" 2>/dev/null || mount "${target_disk}p1" "${mount_root}/boot/efi"

        echo "40"; echo "# Sistem kopyalaniyor (rsync)..."
        rsync -aAXv --exclude={"/dev/*","/proc/*","/sys/*","/tmp/*","/run/*","/mnt/*","/media/*","/lost+found"} \
            / "${mount_root}/" >> "$LOG_FILE" 2>&1

        echo "70"; echo "# Bootloader kuruluyor..."
        # fstab olustur
        local root_uuid
        root_uuid=$(blkid -s UUID -o value "${target_disk}2" 2>/dev/null || blkid -s UUID -o value "${target_disk}p2")
        local efi_uuid
        efi_uuid=$(blkid -s UUID -o value "${target_disk}1" 2>/dev/null || blkid -s UUID -o value "${target_disk}p1")

        cat > "${mount_root}/etc/fstab" << FSTAB
UUID=${root_uuid}  /          ext4  defaults,noatime  0  1
UUID=${efi_uuid}   /boot/efi  vfat  defaults          0  2
tmpfs              /tmp       tmpfs defaults,noatime,size=64M 0 0
FSTAB

        echo "80"; echo "# GRUB kuruluyor..."
        mount --bind /dev "${mount_root}/dev"
        mount --bind /proc "${mount_root}/proc"
        mount --bind /sys "${mount_root}/sys"
        chroot "${mount_root}" grub-install --target=x86_64-efi --efi-directory=/boot/efi --bootloader-id=KlipperAI-OS 2>>"$LOG_FILE" || true
        chroot "${mount_root}" grub-install "$target_disk" 2>>"$LOG_FILE" || true
        chroot "${mount_root}" update-grub 2>>"$LOG_FILE"

        echo "95"; echo "# Temizleniyor..."
        umount -R "${mount_root}" 2>/dev/null || true

        echo "100"; echo "# Tamamlandi!"
    } | whiptail --backtitle "$BACKTITLE" \
        --title "Diske Kurulum" \
        --gauge "Hazirlaniyor..." \
        8 60 0

    log "Disk kurulumu tamamlandi: ${target_disk}"
}

# ===================================================================
# Adim 7: Profil Kurulumu
# ===================================================================
step_install_profile() {
    # Internet kontrolu
    if ! ping -c 1 -W 3 1.1.1.1 &>/dev/null; then
        whiptail --backtitle "$BACKTITLE" \
            --title "Internet Baglantisi Yok" \
            --msgbox "Kurulum icin internet gerekli.\nEthernet baglayip tekrar deneyin.\n\nSistem yeniden baslatildiginda wizard tekrar calisacak." \
            10 55
        log "Kurulum iptal — internet yok"
        # Sentinel dosyasini silme (wizard tekrar calissin)
        touch /opt/klipperos-ai/.first-boot
        return 1
    fi

    whiptail --backtitle "$BACKTITLE" \
        --title "Kurulum Basliyor" \
        --msgbox "\
  Profil: ${SELECTED_PROFILE}

  Simdi yazilim kuruluyor. Bu islem internet
  hiziniza bagli olarak 10-30 dakika surebilir.

  Lutfen bekleyin ve sistemi kapatmayin." \
        12 55

    log "Profil kurulumu basliyor: ${SELECTED_PROFILE}"

    # Profil installer'i calistir
    local installer=""
    case "$SELECTED_PROFILE" in
        LIGHT)    installer="${INSTALL_DIR}/scripts/install-light.sh" ;;
        STANDARD) installer="${INSTALL_DIR}/scripts/install-standard.sh" ;;
        FULL)     installer="${INSTALL_DIR}/scripts/install-full.sh" ;;
    esac

    if [ -x "$installer" ]; then
        bash "$installer" 2>&1 | tee -a "$LOG_FILE"
    else
        log "HATA: Installer bulunamadi: ${installer}"
        whiptail --backtitle "$BACKTITLE" \
            --title "Hata" \
            --msgbox "Installer bulunamadi: ${installer}" \
            8 55
        return 1
    fi

    log "Profil kurulumu tamamlandi: ${SELECTED_PROFILE}"
}

# ===================================================================
# Adim 8: Tamamlandi
# ===================================================================
step_complete() {
    local ip_addr
    ip_addr=$(ip route get 1.1.1.1 2>/dev/null | grep -oP 'src \K\S+' || echo "bilinmiyor")

    whiptail --backtitle "$BACKTITLE" \
        --title "Kurulum Tamamlandi!" \
        --msgbox "\
  KlipperAI-OS basariyla kuruldu!

  Profil:     ${SELECTED_PROFILE}
  IP Adresi:  ${ip_addr}
  Web UI:     http://klipperos.local
  SSH:        ssh klipper@${ip_addr}

  Sonraki adimlar:
  1. printer.cfg'yi yaziciya gore duzenleyin
  2. MCU firmware flash: kos_mcu flash
  3. Web arayuzunden yaziciyi test edin

  Sistem simdi yeniden baslatilacak." \
        18 55

    log "Wizard tamamlandi. Reboot."
}

# ===================================================================
# Ana
# ===================================================================
main() {
    log "=== KlipperAI-OS First Boot Wizard v${VERSION} ==="

    step_welcome
    step_detect_hardware
    step_select_profile
    step_network
    step_user_settings
    step_disk_install
    step_install_profile || {
        log "Kurulum basarisiz. Wizard sonlandirildi."
        exit 1
    }
    step_complete

    # Reboot
    sleep 2
    reboot
}

main "$@"
```

**Test:**

```bash
bash -n image-builder/first-boot-wizard.sh && echo "OK"
# Fonksiyon sayisi kontrolu
grep -c "^step_" image-builder/first-boot-wizard.sh
# Beklenen: 7 (welcome, detect_hardware, select_profile, network, user_settings, disk_install, install_profile) + complete = 8
```

**Commit:**

```bash
git add image-builder/first-boot-wizard.sh
git commit -m "feat: add first-boot wizard with hardware detection and profile selection"
```

---

### Task 5: GRUB Bootloader Config

**Files:**
- Create: `image-builder/config/bootloaders/grub/grub.cfg`

**Amac:** USB boot sirasinda gorunen GRUB menu.

**grub.cfg icerigi:**

```
set default=0
set timeout=5

menuentry "KlipperAI-OS — Baslat" {
    linux /live/vmlinuz boot=live components quiet splash
    initrd /live/initrd.img
}

menuentry "KlipperAI-OS — Guvenli Mod (nomodeset)" {
    linux /live/vmlinuz boot=live components nomodeset
    initrd /live/initrd.img
}

menuentry "KlipperAI-OS — Debug (verbose)" {
    linux /live/vmlinuz boot=live components
    initrd /live/initrd.img
}
```

**Test:**

```bash
# GRUB config icinde 3 menuentry olmali
grep -c "menuentry" image-builder/config/bootloaders/grub/grub.cfg
# Beklenen: 3
```

**Commit:**

```bash
git add image-builder/config/bootloaders/grub/grub.cfg
git commit -m "feat: add GRUB bootloader config with 3 boot options"
```

---

### Task 6: Shell Test Suite

**Files:**
- Create: `tests/test_image_builder.py`

**Amac:** Tum image-builder dosyalarinin syntax, yapisal butunluk ve icerik testleri.

**test_image_builder.py icerigi:**

```python
"""Tests for KlipperAI-OS image builder scripts and configs."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "image-builder"


class TestBuildScript:
    """build-image.sh syntax and structure tests."""

    def test_exists(self):
        assert (IMG_DIR / "build-image.sh").exists()

    def test_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(IMG_DIR / "build-image.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_has_lb_config(self):
        content = (IMG_DIR / "build-image.sh").read_text()
        assert "lb config" in content

    def test_has_lb_build(self):
        content = (IMG_DIR / "build-image.sh").read_text()
        assert "lb build" in content

    def test_has_version(self):
        content = (IMG_DIR / "build-image.sh").read_text()
        assert 'VERSION=' in content


class TestPackageList:
    """Package list tests."""

    def test_exists(self):
        assert (IMG_DIR / "config" / "package-lists" / "klipperos.list.chroot").exists()

    def test_has_essential_packages(self):
        content = (IMG_DIR / "config" / "package-lists" / "klipperos.list.chroot").read_text()
        essential = ["python3", "git", "nginx", "network-manager", "whiptail", "sudo"]
        for pkg in essential:
            assert pkg in content, f"Missing package: {pkg}"

    def test_has_klipper_build_deps(self):
        content = (IMG_DIR / "config" / "package-lists" / "klipperos.list.chroot").read_text()
        assert "gcc-arm-none-eabi" in content

    def test_has_gtk_packages(self):
        content = (IMG_DIR / "config" / "package-lists" / "klipperos.list.chroot").read_text()
        assert "gir1.2-gtk-3.0" in content


class TestBuildHook:
    """Build hook tests."""

    def test_exists(self):
        assert (IMG_DIR / "config" / "hooks" / "live" / "0100-setup.hook.chroot").exists()

    def test_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(IMG_DIR / "config" / "hooks" / "live" / "0100-setup.hook.chroot")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_creates_klipper_user(self):
        content = (IMG_DIR / "config" / "hooks" / "live" / "0100-setup.hook.chroot").read_text()
        assert "useradd" in content
        assert "klipper" in content

    def test_has_sudoers(self):
        content = (IMG_DIR / "config" / "hooks" / "live" / "0100-setup.hook.chroot").read_text()
        assert "sudoers" in content


class TestFirstBootService:
    """Systemd service tests."""

    def test_exists(self):
        svc = IMG_DIR / "config" / "includes.chroot" / "etc" / "systemd" / "system" / "klipperai-first-boot.service"
        assert svc.exists()

    def test_has_condition(self):
        svc = IMG_DIR / "config" / "includes.chroot" / "etc" / "systemd" / "system" / "klipperai-first-boot.service"
        content = svc.read_text()
        assert "ConditionPathExists" in content
        assert ".first-boot" in content

    def test_execstart_points_to_wizard(self):
        svc = IMG_DIR / "config" / "includes.chroot" / "etc" / "systemd" / "system" / "klipperai-first-boot.service"
        content = svc.read_text()
        assert "klipperai-wizard" in content


class TestWizard:
    """First boot wizard tests."""

    def test_exists(self):
        assert (IMG_DIR / "first-boot-wizard.sh").exists()

    def test_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(IMG_DIR / "first-boot-wizard.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_has_all_steps(self):
        content = (IMG_DIR / "first-boot-wizard.sh").read_text()
        steps = [
            "step_welcome", "step_detect_hardware", "step_select_profile",
            "step_network", "step_user_settings", "step_disk_install",
            "step_install_profile", "step_complete",
        ]
        for step in steps:
            assert step in content, f"Missing step: {step}"

    def test_has_profile_recommendation(self):
        content = (IMG_DIR / "first-boot-wizard.sh").read_text()
        assert "RECOMMENDED_PROFILE" in content
        assert "LIGHT" in content
        assert "STANDARD" in content
        assert "FULL" in content

    def test_has_disk_install(self):
        content = (IMG_DIR / "first-boot-wizard.sh").read_text()
        assert "parted" in content
        assert "rsync" in content
        assert "grub-install" in content


class TestGrubConfig:
    """GRUB config tests."""

    def test_exists(self):
        assert (IMG_DIR / "config" / "bootloaders" / "grub" / "grub.cfg").exists()

    def test_has_menu_entries(self):
        content = (IMG_DIR / "config" / "bootloaders" / "grub" / "grub.cfg").read_text()
        assert content.count("menuentry") >= 2

    def test_has_klipperai_branding(self):
        content = (IMG_DIR / "config" / "bootloaders" / "grub" / "grub.cfg").read_text()
        assert "KlipperAI-OS" in content
```

**Test komutu:**

```bash
python -m pytest tests/test_image_builder.py -v
```

**Commit:**

```bash
git add tests/test_image_builder.py
git commit -m "test: add image builder integration tests"
```

---

### Task 7: Final Integration + Push

**Amac:** Tum testleri calistir, dogrula, push et.

**Adimlar:**

```bash
# Tum testleri calistir
python -m pytest tests/ -v

# Image builder dosyalarini dogrula
ls -la image-builder/
ls -la image-builder/config/package-lists/
ls -la image-builder/config/hooks/live/
ls -la image-builder/config/includes.chroot/etc/systemd/system/
ls -la image-builder/config/bootloaders/grub/

# Push
git push origin master
```

**Beklenen toplam yeni dosyalar:**

| Dosya | Amac |
|-------|------|
| `image-builder/build-image.sh` | Ana build scripti |
| `image-builder/config/package-lists/klipperos.list.chroot` | Debian paket listesi |
| `image-builder/config/hooks/live/0100-setup.hook.chroot` | Build hook |
| `image-builder/config/includes.chroot/etc/systemd/system/klipperai-first-boot.service` | Wizard servisi |
| `image-builder/config/bootloaders/grub/grub.cfg` | GRUB menu |
| `image-builder/first-boot-wizard.sh` | Ilk boot wizard |
| `tests/test_image_builder.py` | Test suite |

**Toplam: 7 yeni dosya**
