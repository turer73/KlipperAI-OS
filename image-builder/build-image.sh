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
    --mode debian \
    --system live \
    --distribution bookworm \
    --parent-distribution bookworm \
    --archive-areas "main contrib non-free non-free-firmware" \
    --parent-archive-areas "main contrib non-free non-free-firmware" \
    --parent-mirror-bootstrap "http://deb.debian.org/debian" \
    --parent-mirror-chroot "http://deb.debian.org/debian" \
    --parent-mirror-binary "http://deb.debian.org/debian" \
    --mirror-bootstrap "http://deb.debian.org/debian" \
    --mirror-chroot "http://deb.debian.org/debian" \
    --mirror-binary "http://deb.debian.org/debian" \
    --architectures amd64 \
    --binary-images iso-hybrid \
    --linux-packages none \
    --debian-installer false \
    --memtest none \
    --iso-application "KlipperAI-OS" \
    --iso-volume "KlipperAI-OS v${VERSION}" \
    --apt-recommends false \
    --security false \
    --cache true

# Syslinux/isolinux sorunlu: Ubuntu runner'da live-build binary_syslinux
# asamasi /root/isolinux/ dizinini chroot icinde ariyor ama bulamiyor.
# Modern sistemlerde UEFI + GRUB yeterli. Syslinux devre disi birakildi.
log "Bootloader: syslinux devre disi, sadece grub-efi kullaniliyor..."
if [ -f "${BUILD_DIR}/config/binary" ]; then
    log "config/binary mevcut icerik:"
    cat "${BUILD_DIR}/config/binary"
    # Tum bootloader referanslarini temizle ve grub-efi yaz
    sed -i '/LB_BOOTLOADERS/d' "${BUILD_DIR}/config/binary"
    sed -i '/LB_BOOTLOADER=/d' "${BUILD_DIR}/config/binary"
    echo 'LB_BOOTLOADERS="grub-efi"' >> "${BUILD_DIR}/config/binary"
    log "config/binary guncellenmis icerik:"
    cat "${BUILD_DIR}/config/binary"
else
    warn "config/binary bulunamadi, olusturuluyor..."
    mkdir -p "${BUILD_DIR}/config"
    echo 'LB_BOOTLOADERS="grub-efi"' > "${BUILD_DIR}/config/binary"
fi

# Bookworm security repo dogru URL ile ekleniyor
# (live-build eski bookworm/updates formatini kullaniyor, dogru format bookworm-security)
mkdir -p "${BUILD_DIR}/config/archives"
echo "deb http://deb.debian.org/debian-security bookworm-security main contrib non-free non-free-firmware" \
    > "${BUILD_DIR}/config/archives/security.list.chroot"
echo "deb http://deb.debian.org/debian bookworm-updates main contrib non-free non-free-firmware" \
    > "${BUILD_DIR}/config/archives/updates.list.chroot"

# --- Paket listesi kopyala ---
log "Paket listesi kopyalaniyor..."
cp "${SCRIPT_DIR}/config/package-lists/klipperos.list.chroot" \
    "${BUILD_DIR}/config/package-lists/"

# --- includes.chroot: proje dosyalarini kopyala ---
log "Proje dosyalari kopyalaniyor..."
CHROOT="${BUILD_DIR}/config/includes.chroot"
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
    IMG_SIZE=$(du -h "${SCRIPT_DIR}/${IMAGE_NAME}.img" | cut -f1)
    echo ""
    log "Imaj olusturuldu!"
    log "Dosya: ${SCRIPT_DIR}/${IMAGE_NAME}.img"
    log "Boyut: ${IMG_SIZE}"
    echo ""
    echo -e "${GREEN}USB'ye yazmak icin:${NC}"
    echo "  sudo dd if=${IMAGE_NAME}.img of=/dev/sdX bs=4M status=progress"
    echo "  veya Balena Etcher / Rufus kullanin."
else
    err "Imaj olusturulamadi! build.log dosyasini kontrol edin."
    exit 1
fi
