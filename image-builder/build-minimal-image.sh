#!/bin/bash
# =============================================================================
# KlipperOS-AI — Minimal Image Builder
# =============================================================================
# Minimal ISO: sadece Python TUI installer icerir.
# Tum Klipper ekosistemi internet uzerinden kurulur.
#
# Kullanim:
#   sudo ./build-minimal-image.sh
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${SCRIPT_DIR}/build"
VERSION="3.0.0-minimal"
IMAGE_NAME="klipperos-minimal-v${VERSION}"

# Ubuntu Server ISO bilgileri
UBUNTU_VERSION="24.04.2"
UBUNTU_ISO_URL="https://releases.ubuntu.com/${UBUNTU_VERSION}/ubuntu-${UBUNTU_VERSION}-live-server-amd64.iso"
UBUNTU_ISO_FILE="ubuntu-${UBUNTU_VERSION}-live-server-amd64.iso"
UBUNTU_ISO_SHA_URL="https://releases.ubuntu.com/${UBUNTU_VERSION}/SHA256SUMS"

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

# --- Gerekli araclari kontrol et ---
for cmd in xorriso wget; do
    if ! command -v "$cmd" &>/dev/null; then
        err "${cmd} kurulu degil. Kuruluyor..."
        apt-get update && apt-get install -y "$cmd"
    fi
done

# --- Build dizini hazirla ---
log "Build dizini hazirlaniyor: ${BUILD_DIR}"
mkdir -p "$BUILD_DIR"
cd "$BUILD_DIR"

# =============================================================================
# ADIM 1: Ubuntu Server ISO indir
# =============================================================================
if [ -f "${BUILD_DIR}/${UBUNTU_ISO_FILE}" ]; then
    log "Ubuntu Server ISO cache'de mevcut: ${UBUNTU_ISO_FILE}"
else
    log "Ubuntu Server ${UBUNTU_VERSION} ISO indiriliyor..."
    wget --progress=dot:mega -O "${BUILD_DIR}/${UBUNTU_ISO_FILE}" "$UBUNTU_ISO_URL"
fi

# SHA256 dogrulama
if [ "${SKIP_SHA_CHECK:-}" != "1" ]; then
    log "SHA256 dogrulamasi yapiliyor..."
    if wget -q -O "${BUILD_DIR}/SHA256SUMS" "$UBUNTU_ISO_SHA_URL" 2>/dev/null; then
        expected_sha=$(grep "$UBUNTU_ISO_FILE" "${BUILD_DIR}/SHA256SUMS" | awk '{print $1}')
        actual_sha=$(sha256sum "${BUILD_DIR}/${UBUNTU_ISO_FILE}" | awk '{print $1}')
        if [ "$expected_sha" = "$actual_sha" ]; then
            log "SHA256 dogrulandi"
        else
            err "SHA256 uyusmuyor! ISO bozuk olabilir."
            rm -f "${BUILD_DIR}/${UBUNTU_ISO_FILE}"
            exit 1
        fi
    else
        warn "SHA256SUMS indirilemedi — dogrulama atlaniyor."
    fi
fi

# =============================================================================
# ADIM 2: ISO'yu ac
# =============================================================================
ISO_EXTRACT="${BUILD_DIR}/iso-extract"
log "ISO cikariliyor: ${ISO_EXTRACT}"
rm -rf "$ISO_EXTRACT"
mkdir -p "$ISO_EXTRACT"

xorriso -osirrox on -indev "${BUILD_DIR}/${UBUNTU_ISO_FILE}" \
    -extract / "$ISO_EXTRACT" 2>/dev/null

chmod -R u+w "$ISO_EXTRACT"
log "ISO cikarildi: $(du -sh "$ISO_EXTRACT" | cut -f1)"

# =============================================================================
# ADIM 3: Autoinstall config ekle
# =============================================================================
log "Autoinstall yapilandirmasi ekleniyor..."
AUTOINSTALL_DIR="${ISO_EXTRACT}/autoinstall"
mkdir -p "$AUTOINSTALL_DIR"

cp "${SCRIPT_DIR}/autoinstall/user-data" "${AUTOINSTALL_DIR}/user-data"
cp "${SCRIPT_DIR}/autoinstall/meta-data" "${AUTOINSTALL_DIR}/meta-data"

# Password hash
if command -v openssl &>/dev/null; then
    RANDOM_SALT=$(openssl rand -hex 8)
    PASS_HASH=$(openssl passwd -6 -salt "${RANDOM_SALT}" "klipper")
    sed -i "s|password: .*|password: \"${PASS_HASH}\"|" "${AUTOINSTALL_DIR}/user-data"
    log "Password hash olusturuldu"
fi

# =============================================================================
# ADIM 4: Sadece installer dosyalarini ekle (MINIMAL)
# =============================================================================
log "Minimal installer dosyalari ekleniyor..."
KLIPPEROS_DIR="${ISO_EXTRACT}/klipperos-ai"
mkdir -p "$KLIPPEROS_DIR"

# Sadece Python installer paketi
cp -r "${PROJECT_ROOT}/packages" "${KLIPPEROS_DIR}/"
cp "${PROJECT_ROOT}/pyproject.toml" "${KLIPPEROS_DIR}/"

# Systemd service dosyasi
mkdir -p "${KLIPPEROS_DIR}/systemd"
cp "${SCRIPT_DIR}/config/includes.chroot/etc/systemd/system/kos-installer.service" \
    "${KLIPPEROS_DIR}/systemd/"

log "Minimal dosyalar eklendi: $(du -sh "$KLIPPEROS_DIR" | cut -f1)"

# =============================================================================
# ADIM 5: GRUB config guncelle
# =============================================================================
log "GRUB yapilandirmasi guncelleniyor..."

GRUB_CFG="${ISO_EXTRACT}/boot/grub/grub.cfg"
if [ -f "$GRUB_CFG" ]; then
    cp "$GRUB_CFG" "${GRUB_CFG}.orig"
    sed -i 's|---$|autoinstall ds=nocloud\\;s=/cdrom/autoinstall/ ---|' "$GRUB_CFG"
    sed -i '/vmlinuz/{ /autoinstall/! s|$| autoinstall ds=nocloud\\;s=/cdrom/autoinstall/| }' "$GRUB_CFG"
    log "GRUB config guncellendi"
else
    warn "GRUB config bulunamadi: ${GRUB_CFG}"
    find "$ISO_EXTRACT" -name "grub.cfg" -type f 2>/dev/null | while read -r f; do
        cp "$f" "${f}.orig"
        sed -i 's|---$|autoinstall ds=nocloud\\;s=/cdrom/autoinstall/ ---|' "$f"
        sed -i '/vmlinuz/{ /autoinstall/! s|$| autoinstall ds=nocloud\\;s=/cdrom/autoinstall/| }' "$f"
    done
fi

LOOPBACK_CFG="${ISO_EXTRACT}/boot/grub/loopback.cfg"
if [ -f "$LOOPBACK_CFG" ]; then
    cp "$LOOPBACK_CFG" "${LOOPBACK_CFG}.orig"
    sed -i 's|---$|autoinstall ds=nocloud\\;s=/cdrom/autoinstall/ ---|' "$LOOPBACK_CFG"
fi

# =============================================================================
# ADIM 6: ISO'yu yeniden paketle
# =============================================================================
log "ISO yeniden paketleniyor..."

OUTPUT_ISO="${SCRIPT_DIR}/${IMAGE_NAME}.iso"

# MBR parcasi
dd if="${BUILD_DIR}/${UBUNTU_ISO_FILE}" bs=1 count=446 of="${BUILD_DIR}/mbr.bin" 2>/dev/null

# EFI partition
EFI_IMG="${BUILD_DIR}/efi.img"
EFI_CANDIDATES=(
    "${ISO_EXTRACT}/boot/grub/efi.img"
    "${ISO_EXTRACT}/EFI/BOOT/efiboot.img"
    "${ISO_EXTRACT}/efi.img"
)
EFI_FOUND=""
for candidate in "${EFI_CANDIDATES[@]}"; do
    if [ -f "$candidate" ]; then
        EFI_FOUND="$candidate"
        break
    fi
done

if [ -z "$EFI_FOUND" ]; then
    PART_INFO=$(fdisk -l "${BUILD_DIR}/${UBUNTU_ISO_FILE}" 2>/dev/null | grep "EFI" | head -1 || true)
    if [ -n "$PART_INFO" ]; then
        EFI_START_SECTOR=$(echo "$PART_INFO" | awk '{print $2}')
        EFI_END_SECTOR=$(echo "$PART_INFO" | awk '{print $3}')
        EFI_SECTORS=$((EFI_END_SECTOR - EFI_START_SECTOR + 1))
        dd if="${BUILD_DIR}/${UBUNTU_ISO_FILE}" of="$EFI_IMG" \
            bs=512 skip="$EFI_START_SECTOR" count="$EFI_SECTORS" 2>/dev/null
    fi
else
    cp "$EFI_FOUND" "$EFI_IMG"
fi

# BIOS boot image
BIOS_IMG=""
BIOS_CANDIDATES=(
    "${ISO_EXTRACT}/boot/grub/i386-pc/eltorito.img"
    "${ISO_EXTRACT}/boot/grub/bios.img"
    "${ISO_EXTRACT}/isolinux/isolinux.bin"
)
for candidate in "${BIOS_CANDIDATES[@]}"; do
    if [ -f "$candidate" ]; then
        BIOS_IMG="$candidate"
        break
    fi
done

# xorriso ile yeni ISO olustur
if [ -f "$EFI_IMG" ] && [ -f "$BIOS_IMG" ]; then
    log "Hybrid boot ISO olusturuluyor (BIOS + UEFI)..."
    BIOS_REL="${BIOS_IMG#${ISO_EXTRACT}/}"
    xorriso -as mkisofs \
        -r -V "KlipperOS-AI Minimal v${VERSION}" \
        -o "$OUTPUT_ISO" \
        --grub2-mbr "${BUILD_DIR}/mbr.bin" \
        -partition_offset 16 \
        --mbr-force-bootable \
        -append_partition 2 28732ac11ff8d211ba4b00a0c93ec93b "$EFI_IMG" \
        -appended_part_as_gpt \
        -iso_mbr_part_type a2a0d0ebe5b9334487c068b6b72699c7 \
        -c '/boot.catalog' \
        -b "/${BIOS_REL}" \
            -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
        -eltorito-alt-boot \
        -e '--interval:appended_partition_2:::' \
            -no-emul-boot \
        "$ISO_EXTRACT" \
        2>&1 | tail -10
elif [ -f "$EFI_IMG" ]; then
    log "UEFI-only ISO olusturuluyor..."
    xorriso -as mkisofs \
        -r -V "KlipperOS-AI Minimal v${VERSION}" \
        -o "$OUTPUT_ISO" \
        -append_partition 2 28732ac11ff8d211ba4b00a0c93ec93b "$EFI_IMG" \
        -appended_part_as_gpt \
        -e '--interval:appended_partition_2:::' \
            -no-emul-boot \
        "$ISO_EXTRACT" \
        2>&1 | tail -10
else
    warn "Boot image bulunamadi — basit ISO olusturuluyor..."
    xorriso -as mkisofs \
        -r -V "KlipperOS-AI Minimal v${VERSION}" \
        -o "$OUTPUT_ISO" \
        -J -joliet-long \
        "$ISO_EXTRACT" \
        2>&1 | tail -10
fi

# =============================================================================
# ADIM 7: Temizlik ve sonuc
# =============================================================================
if [ -f "$OUTPUT_ISO" ] && [ -s "$OUTPUT_ISO" ]; then
    ISO_SIZE=$(du -h "$OUTPUT_ISO" | cut -f1)
    ISO_SHA=$(sha256sum "$OUTPUT_ISO" | awk '{print $1}')
    echo "${ISO_SHA}  ${IMAGE_NAME}.iso" > "${OUTPUT_ISO}.sha256"

    echo ""
    log "============================================"
    log "  KlipperOS-AI Minimal ISO olusturuldu!"
    log "============================================"
    log "Dosya: ${OUTPUT_ISO}"
    log "Boyut: ${ISO_SIZE}"
    log "SHA256: ${ISO_SHA}"
    echo ""
    echo -e "${GREEN}USB'ye yazmak icin:${NC}"
    echo "  sudo dd if=${IMAGE_NAME}.iso of=/dev/sdX bs=4M status=progress"

    if [ "${CLEANUP:-1}" = "1" ]; then
        rm -rf "$ISO_EXTRACT"
        rm -f "${BUILD_DIR}/mbr.bin"
    fi
else
    err "ISO olusturulamadi!"
    exit 1
fi
