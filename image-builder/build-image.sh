#!/bin/bash
# =============================================================================
# KlipperAI-OS — Image Builder (Ubuntu Server ISO Repackaging)
# =============================================================================
# Ubuntu Server 24.04 LTS ISO'sunu indirir, autoinstall config ve
# KlipperOS-AI dosyalarini ekleyerek ozel bir kurulum ISO'su olusturur.
#
# Yontem:
#   1. Ubuntu Server 24.04 ISO indir (veya cache'den kullan)
#   2. ISO'yu xorriso ile ac
#   3. autoinstall/ dizinini ekle (user-data, meta-data)
#   4. KlipperOS-AI proje dosyalarini /klipperos-ai/ olarak ekle
#   5. GRUB config'e autoinstall parametresini ekle
#   6. xorriso ile yeniden paketle
#
# Gereksinimler:
#   sudo apt-get install xorriso p7zip-full wget
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
# ADIM 1: Ubuntu Server ISO'sunu indir
# =============================================================================
if [ -f "${BUILD_DIR}/${UBUNTU_ISO_FILE}" ]; then
    log "Ubuntu Server ISO cache'de mevcut: ${UBUNTU_ISO_FILE}"
else
    log "Ubuntu Server ${UBUNTU_VERSION} ISO indiriliyor..."
    log "URL: ${UBUNTU_ISO_URL}"
    wget --progress=dot:mega -O "${BUILD_DIR}/${UBUNTU_ISO_FILE}" "$UBUNTU_ISO_URL"
    log "ISO indirildi: $(du -h "${BUILD_DIR}/${UBUNTU_ISO_FILE}" | cut -f1)"
fi

# SHA256 dogrulama (opsiyonel — CI'da zaman kazanmak icin atlanabilir)
if [ "${SKIP_SHA_CHECK:-}" != "1" ]; then
    log "SHA256 dogrulamasi yapiliyor..."
    if wget -q -O "${BUILD_DIR}/SHA256SUMS" "$UBUNTU_ISO_SHA_URL" 2>/dev/null; then
        expected_sha=$(grep "$UBUNTU_ISO_FILE" "${BUILD_DIR}/SHA256SUMS" | awk '{print $1}')
        actual_sha=$(sha256sum "${BUILD_DIR}/${UBUNTU_ISO_FILE}" | awk '{print $1}')
        if [ "$expected_sha" = "$actual_sha" ]; then
            log "SHA256 dogrulandi ✓"
        else
            err "SHA256 uyusmuyor! ISO bozuk olabilir."
            err "  Beklenen: ${expected_sha}"
            err "  Gercek:   ${actual_sha}"
            rm -f "${BUILD_DIR}/${UBUNTU_ISO_FILE}"
            exit 1
        fi
    else
        warn "SHA256SUMS indirilemedi — dogrulama atlanıyor."
    fi
fi

# =============================================================================
# ADIM 2: ISO'yu ac
# =============================================================================
ISO_EXTRACT="${BUILD_DIR}/iso-extract"
log "ISO cikariliyor: ${ISO_EXTRACT}"
rm -rf "$ISO_EXTRACT"
mkdir -p "$ISO_EXTRACT"

# xorriso ile ISO icerigini cikart
xorriso -osirrox on -indev "${BUILD_DIR}/${UBUNTU_ISO_FILE}" \
    -extract / "$ISO_EXTRACT" 2>/dev/null

# Yazma izinlerini ayarla (ISO read-only olarak cikar)
chmod -R u+w "$ISO_EXTRACT"

log "ISO cikarildi: $(du -sh "$ISO_EXTRACT" | cut -f1)"

# Debug: ISO icerigini listele
log "ISO yapisi (onemli dosyalar):"
find "$ISO_EXTRACT" -name "*.img" -o -name "*.bin" -o -name "grub.cfg" -o -name "efi*" 2>/dev/null | head -20 | while read -r f; do
    log "  $(ls -lh "$f" | awk '{print $5, $NF}')"
done

# =============================================================================
# ADIM 3: Autoinstall config ekle
# =============================================================================
log "Autoinstall yapilandirmasi ekleniyor..."
AUTOINSTALL_DIR="${ISO_EXTRACT}/autoinstall"
mkdir -p "$AUTOINSTALL_DIR"

# user-data ve meta-data kopyala
cp "${SCRIPT_DIR}/autoinstall/user-data" "${AUTOINSTALL_DIR}/user-data"
cp "${SCRIPT_DIR}/autoinstall/meta-data" "${AUTOINSTALL_DIR}/meta-data"

# Password hash'i build sirasinda olustur (guvenli)
if command -v openssl &>/dev/null; then
    PASS_HASH=$(openssl passwd -6 -salt "klipperai" "klipper")
    sed -i "s|password: .*|password: \"${PASS_HASH}\"|" "${AUTOINSTALL_DIR}/user-data"
    log "Password hash olusturuldu (openssl)"
fi

log "Autoinstall dosyalari eklendi: user-data, meta-data"

# =============================================================================
# ADIM 4: KlipperOS-AI proje dosyalarini ekle
# =============================================================================
log "KlipperOS-AI proje dosyalari ekleniyor..."
KLIPPEROS_DIR="${ISO_EXTRACT}/klipperos-ai"
mkdir -p "$KLIPPEROS_DIR"

# Proje dizinleri
for dir in scripts ai-monitor config tools ks-panels data; do
    if [ -d "${PROJECT_ROOT}/${dir}" ]; then
        cp -r "${PROJECT_ROOT}/${dir}" "${KLIPPEROS_DIR}/"
        log "  + ${dir}/"
    fi
done

# Ertelenmis paket listesi
mkdir -p "${KLIPPEROS_DIR}/config/package-lists"
cp "${SCRIPT_DIR}/config/package-lists/klipperos-deferred.list" \
    "${KLIPPEROS_DIR}/config/package-lists/" 2>/dev/null || true

# pyproject.toml ve README
cp "${PROJECT_ROOT}/pyproject.toml" "${KLIPPEROS_DIR}/" 2>/dev/null || true
cp "${PROJECT_ROOT}/README.md" "${KLIPPEROS_DIR}/" 2>/dev/null || true

# First-boot wizard
mkdir -p "${KLIPPEROS_DIR}/image-builder"
cp "${SCRIPT_DIR}/first-boot-wizard.sh" "${KLIPPEROS_DIR}/image-builder/"

# Calistirilabilir izinler
chmod +x "${KLIPPEROS_DIR}/scripts/"*.sh 2>/dev/null || true
chmod +x "${KLIPPEROS_DIR}/image-builder/first-boot-wizard.sh" 2>/dev/null || true

# Systemd service dosyasi
mkdir -p "${KLIPPEROS_DIR}/systemd"
cp "${SCRIPT_DIR}/config/includes.chroot/etc/systemd/system/klipperai-first-boot.service" \
    "${KLIPPEROS_DIR}/systemd/" 2>/dev/null || true

log "Proje dosyalari eklendi: $(du -sh "$KLIPPEROS_DIR" | cut -f1)"

# =============================================================================
# ADIM 5: GRUB config'i guncelle — autoinstall parametresi ekle
# =============================================================================
log "GRUB yapilandirmasi guncelleniyor..."

# Ubuntu Server ISO'daki GRUB config dosyalarini bul ve guncelle
# UEFI: /boot/grub/grub.cfg
# Legacy: /boot/grub/grub.cfg (ayni dosya, mbr_force ile)

GRUB_CFG="${ISO_EXTRACT}/boot/grub/grub.cfg"
if [ -f "$GRUB_CFG" ]; then
    log "GRUB config bulundu: ${GRUB_CFG}"

    # Mevcut GRUB config'in yedegini al
    cp "$GRUB_CFG" "${GRUB_CFG}.orig"

    # autoinstall kernel parametresini ekle
    # Ubuntu Server ISO'da linux satiri: linux /casper/vmlinuz ---
    # Biz ekliyoruz: autoinstall ds=nocloud\;s=/cdrom/autoinstall/
    sed -i 's|---$|autoinstall ds=nocloud\\;s=/cdrom/autoinstall/ ---|' "$GRUB_CFG"

    # Eger --- olmayan satirlar varsa (fallback)
    sed -i '/vmlinuz/{ /autoinstall/! s|$| autoinstall ds=nocloud\\;s=/cdrom/autoinstall/| }' "$GRUB_CFG"

    log "GRUB config guncellendi — autoinstall parametresi eklendi"
else
    warn "GRUB config bulunamadi: ${GRUB_CFG}"
    warn "Alternatif konumlar aranıyor..."
    find "$ISO_EXTRACT" -name "grub.cfg" -type f 2>/dev/null | while read -r f; do
        log "  Bulunan: $f"
        cp "$f" "${f}.orig"
        sed -i 's|---$|autoinstall ds=nocloud\\;s=/cdrom/autoinstall/ ---|' "$f"
        sed -i '/vmlinuz/{ /autoinstall/! s|$| autoinstall ds=nocloud\\;s=/cdrom/autoinstall/| }' "$f"
        log "  Guncellendi: $f"
    done
fi

# Loopback grub.cfg varsa (Ubuntu bazen /boot/grub/loopback.cfg kullanir)
LOOPBACK_CFG="${ISO_EXTRACT}/boot/grub/loopback.cfg"
if [ -f "$LOOPBACK_CFG" ]; then
    cp "$LOOPBACK_CFG" "${LOOPBACK_CFG}.orig"
    sed -i 's|---$|autoinstall ds=nocloud\\;s=/cdrom/autoinstall/ ---|' "$LOOPBACK_CFG"
    log "loopback.cfg guncellendi"
fi

# =============================================================================
# ADIM 6: ISO'yu yeniden paketle
# =============================================================================
log "ISO yeniden paketleniyor..."

OUTPUT_ISO="${SCRIPT_DIR}/${IMAGE_NAME}.iso"

# Ubuntu Server ISO'nun boot parametrelerini oku
# xorriso -report_el_torito bize orijinal ISO'nun tam boot yapilandirmasini verir
log "Orijinal ISO boot parametreleri okunuyor..."
BOOT_PARAMS=$(xorriso -indev "${BUILD_DIR}/${UBUNTU_ISO_FILE}" \
    -report_el_torito as_mkisofs 2>/dev/null || true)
log "Boot params: ${BOOT_PARAMS}"

# MBR parcasini cikar (hybrid boot icin)
dd if="${BUILD_DIR}/${UBUNTU_ISO_FILE}" bs=1 count=446 of="${BUILD_DIR}/mbr.bin" 2>/dev/null

# EFI partition'i ayri dosya olarak cikar
# Ubuntu Server ISO'da EFI partition genellikle appended partition olarak bulunur
# --interval:appended_partition_2:all:: formatinda xorriso tanimlari vardir
# Bunu orijinal ISO'dan cikarmamiz gerekiyor
EFI_IMG="${BUILD_DIR}/efi.img"
log "EFI partition cikariliyor..."
PART_START=$(xorriso -indev "${BUILD_DIR}/${UBUNTU_ISO_FILE}" \
    -report_el_torito as_mkisofs 2>/dev/null | \
    grep -oP '(?<=-append_partition 2 0xEF )\S+' || true)

if [ -n "$PART_START" ] && [ -f "$PART_START" ]; then
    cp "$PART_START" "$EFI_IMG"
    log "EFI partition dosyadan kopyalandi"
else
    # Alternatif: EFI image'i ISO icerisinden bul
    EFI_CANDIDATES=(
        "${ISO_EXTRACT}/boot/grub/efi.img"
        "${ISO_EXTRACT}/EFI/BOOT/efiboot.img"
        "${ISO_EXTRACT}/efi.img"
    )
    EFI_FOUND=""
    for candidate in "${EFI_CANDIDATES[@]}"; do
        if [ -f "$candidate" ]; then
            EFI_FOUND="$candidate"
            log "EFI image bulundu: ${candidate}"
            break
        fi
    done

    if [ -z "$EFI_FOUND" ]; then
        # EFI partition'i dogrudan orijinal ISO'dan dd ile cikar
        log "EFI image dosya olarak bulunamadi, ISO'dan cikartiliyor..."
        # Ubuntu Server ISO'da EFI partition offset'ini bul
        PART_INFO=$(fdisk -l "${BUILD_DIR}/${UBUNTU_ISO_FILE}" 2>/dev/null | grep "EFI" | head -1 || true)
        if [ -n "$PART_INFO" ]; then
            EFI_START_SECTOR=$(echo "$PART_INFO" | awk '{print $2}')
            EFI_END_SECTOR=$(echo "$PART_INFO" | awk '{print $3}')
            EFI_SECTORS=$((EFI_END_SECTOR - EFI_START_SECTOR + 1))
            dd if="${BUILD_DIR}/${UBUNTU_ISO_FILE}" of="$EFI_IMG" \
                bs=512 skip="$EFI_START_SECTOR" count="$EFI_SECTORS" 2>/dev/null
            log "EFI partition cikarildi: ${EFI_SECTORS} sektorler"
        else
            warn "EFI partition bilgisi bulunamadi!"
        fi
    else
        cp "$EFI_FOUND" "$EFI_IMG"
    fi
fi

# BIOS boot image'ini bul
BIOS_IMG=""
BIOS_CANDIDATES=(
    "${ISO_EXTRACT}/boot/grub/i386-pc/eltorito.img"
    "${ISO_EXTRACT}/boot/grub/bios.img"
    "${ISO_EXTRACT}/isolinux/isolinux.bin"
)
for candidate in "${BIOS_CANDIDATES[@]}"; do
    if [ -f "$candidate" ]; then
        BIOS_IMG="$candidate"
        log "BIOS boot image bulundu: ${candidate}"
        break
    fi
done

# xorriso ile yeni ISO olustur
if [ -f "$EFI_IMG" ] && [ -f "$BIOS_IMG" ]; then
    log "Hybrid boot ISO olusturuluyor (BIOS + UEFI)..."
    BIOS_REL="${BIOS_IMG#${ISO_EXTRACT}/}"

    xorriso -as mkisofs \
        -r -V "KlipperAI-OS v${VERSION}" \
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
        -r -V "KlipperAI-OS v${VERSION}" \
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
        -r -V "KlipperAI-OS v${VERSION}" \
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

    # SHA256 dosyasi olustur (orijinal ISO icin)
    echo "${ISO_SHA}  ${IMAGE_NAME}.iso" > "${OUTPUT_ISO}.sha256"

    # .img kopya (lokal kullanim icin)
    cp "$OUTPUT_ISO" "${SCRIPT_DIR}/${IMAGE_NAME}.img"
    echo "${ISO_SHA}  ${IMAGE_NAME}.img" > "${SCRIPT_DIR}/${IMAGE_NAME}.img.sha256"

    # GitHub Release 2GB limiti — dosyayi 1.9 GB parcalara bol
    ISO_SIZE_BYTES=$(stat --printf="%s" "$OUTPUT_ISO" 2>/dev/null || stat -f%z "$OUTPUT_ISO")
    MAX_PART_SIZE=$((1900 * 1024 * 1024))  # 1.9 GB
    if [ "$ISO_SIZE_BYTES" -gt "$MAX_PART_SIZE" ]; then
        log "ISO boyutu (${ISO_SIZE}) > 1.9 GB — parcalara bolunuyor..."
        SPLIT_PREFIX="${SCRIPT_DIR}/${IMAGE_NAME}.img.part"
        split -b 1900m "${SCRIPT_DIR}/${IMAGE_NAME}.img" "${SPLIT_PREFIX}"
        PART_COUNT=$(ls -1 "${SPLIT_PREFIX}"* 2>/dev/null | wc -l)
        log "ISO ${PART_COUNT} parcaya bolundu"
        # Her parca icin SHA256
        for part in "${SPLIT_PREFIX}"*; do
            part_sha=$(sha256sum "$part" | awk '{print $1}')
            part_name=$(basename "$part")
            echo "${part_sha}  ${part_name}" >> "${SCRIPT_DIR}/${IMAGE_NAME}.img.parts.sha256"
            log "  $(basename "$part"): $(du -h "$part" | cut -f1)"
        done
    else
        log "ISO boyutu 2 GB limitinin altinda, parcalama gerekmiyor."
    fi

    echo ""
    log "============================================"
    log "  KlipperAI-OS ISO olusturuldu!"
    log "============================================"
    log "Dosya: ${OUTPUT_ISO}"
    log "Boyut: ${ISO_SIZE}"
    log "SHA256: ${ISO_SHA}"
    echo ""
    echo -e "${GREEN}USB'ye yazmak icin:${NC}"
    echo "  sudo dd if=${IMAGE_NAME}.iso of=/dev/sdX bs=4M status=progress"
    echo "  veya Balena Etcher / Rufus kullanin."
    echo ""
    echo -e "${CYAN}Not:${NC} Bu ISO, USB'den boot edildiginde Ubuntu Server'i"
    echo "  otomatik olarak kurar ve ilk boot'ta KlipperOS-AI wizard'i baslatir."

    # Extract dizinini temizle (CI'da disk alanı icin)
    if [ "${CLEANUP:-1}" = "1" ]; then
        log "Gecici dosyalar temizleniyor..."
        rm -rf "$ISO_EXTRACT"
        rm -f "${BUILD_DIR}/mbr.bin"
    fi
else
    err "ISO olusturulamadi!"
    err "xorriso ciktisini kontrol edin."
    exit 1
fi
