#!/bin/bash
# =============================================================================
# KlipperOS-AI — Debootstrap Minimal Live ISO Builder
# =============================================================================
# debootstrap ile sifirdan Ubuntu Noble rootfs olusturur, squashfs ile
# sikistirir ve ~500 MB hybrid BIOS+UEFI bootable live ISO uretir.
#
# Kullanim:
#   sudo ./build-minimal-image.sh
#
# Ortam degiskenleri:
#   SKIP_DEBOOTSTRAP=1   — Onceki rootfs'i yeniden kullan (hizli iterasyon)
#   CLEANUP=0            — Gecici dosyalari silme
#   NO_FIRMWARE=1        — linux-firmware paketini dahil etme (daha kucuk ISO)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="${SCRIPT_DIR}/build"
VERSION="4.0.0-live"
IMAGE_NAME="klipperos-minimal-v${VERSION}"

# Ubuntu Noble (24.04)
UBUNTU_SUITE="noble"
UBUNTU_MIRROR="http://archive.ubuntu.com/ubuntu"
ARCH="amd64"

# Build dizinleri
ROOTFS_DIR="${BUILD_DIR}/rootfs"
ISO_DIR="${BUILD_DIR}/iso-staging"
OUTPUT_ISO="${SCRIPT_DIR}/${IMAGE_NAME}.iso"

# Renkler
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log()  { echo -e "${GREEN}[BUILD]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }

# =============================================================================
# FAZ 0: Hazirlik
# =============================================================================
if [ "$(id -u)" -ne 0 ]; then
    err "Root yetkisi gerekli: sudo $0"
    exit 1
fi

REQUIRED_CMDS=(debootstrap mksquashfs xorriso grub-mkimage mcopy mkfs.vfat)
for cmd in "${REQUIRED_CMDS[@]}"; do
    if ! command -v "$cmd" &>/dev/null; then
        err "${cmd} bulunamadi. Kuruluyor..."
        apt-get update -qq
        apt-get install -y -qq debootstrap squashfs-tools xorriso \
            grub-efi-amd64-bin grub-pc-bin mtools dosfstools
        break
    fi
done

log "Build dizini hazirlaniyor: ${BUILD_DIR}"
mkdir -p "$BUILD_DIR"

# =============================================================================
# FAZ 1: debootstrap — Minimal rootfs olustur
# =============================================================================
if [ "${SKIP_DEBOOTSTRAP:-}" = "1" ] && [ -d "${ROOTFS_DIR}/bin" ]; then
    log "Mevcut rootfs kullaniliyor (SKIP_DEBOOTSTRAP=1)"
else
    log "debootstrap baslatiliyor: ${UBUNTU_SUITE} (${ARCH})..."
    rm -rf "$ROOTFS_DIR"
    debootstrap --arch="${ARCH}" --variant=minbase \
        --include=systemd-sysv,dbus,apt,locales,console-setup \
        "$UBUNTU_SUITE" "$ROOTFS_DIR" "$UBUNTU_MIRROR"
    log "debootstrap tamamlandi: $(du -sh "$ROOTFS_DIR" | cut -f1)"
fi

# =============================================================================
# FAZ 2: APT kaynaklari yapilandir
# =============================================================================
log "APT kaynaklari ayarlaniyor..."
cat > "${ROOTFS_DIR}/etc/apt/sources.list" << EOF
deb ${UBUNTU_MIRROR} ${UBUNTU_SUITE} main restricted universe
deb ${UBUNTU_MIRROR} ${UBUNTU_SUITE}-updates main restricted universe
deb http://security.ubuntu.com/ubuntu ${UBUNTU_SUITE}-security main restricted universe
EOF

# =============================================================================
# FAZ 3: Chroot icinde paketleri kur
# =============================================================================
log "Bind mount'lar hazirlaniyor..."
cleanup_mounts() {
    log "Bind mount'lar kaldiriliyor..."
    umount "${ROOTFS_DIR}/run"      2>/dev/null || true
    umount "${ROOTFS_DIR}/sys"      2>/dev/null || true
    umount "${ROOTFS_DIR}/proc"     2>/dev/null || true
    umount "${ROOTFS_DIR}/dev/pts"  2>/dev/null || true
    umount "${ROOTFS_DIR}/dev"      2>/dev/null || true
}
trap cleanup_mounts EXIT

mount --bind /dev     "${ROOTFS_DIR}/dev"
mount --bind /dev/pts "${ROOTFS_DIR}/dev/pts"
mount -t proc proc    "${ROOTFS_DIR}/proc"
mount -t sysfs sysfs  "${ROOTFS_DIR}/sys"
mount --bind /run     "${ROOTFS_DIR}/run"

# Paket listesi
PACKAGES=(
    # Kernel + live-boot
    linux-image-generic
    live-boot

    # Bootloader
    grub-efi-amd64-signed
    shim-signed
    grub-pc-bin

    # Ag
    network-manager
    wpasupplicant
    avahi-daemon
    avahi-utils
    openssh-server

    # Python (TUI installer icin)
    python3
    python3-venv
    python3-pip
    python3-dev

    # Temel araclar
    curl
    wget
    git
    whiptail
    sudo
    ca-certificates
    gnupg

    # Sistem araclari
    nano
    htop
    less
    earlyoom

    # Disk kurulumu icin
    parted
    dosfstools
    rsync
)

# Opsiyonel: linux-firmware (WiFi/Ethernet surucileri — ~300 MB)
if [ "${NO_FIRMWARE:-}" != "1" ]; then
    PACKAGES+=(linux-firmware)
    log "linux-firmware dahil edilecek (NO_FIRMWARE=1 ile devre disi birakilabilir)"
else
    warn "linux-firmware DAHIL EDILMIYOR — bazi donanim destekleri eksik olabilir"
fi

PKG_LIST="${PACKAGES[*]}"

log "Paketler kuruluyor (${#PACKAGES[@]} paket)..."
chroot "$ROOTFS_DIR" /bin/bash -c "
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y --no-install-recommends $PKG_LIST
    apt-get clean
"
log "Paket kurulumu tamamlandi: $(du -sh "$ROOTFS_DIR" | cut -f1)"

# =============================================================================
# FAZ 4: chroot-setup.sh — Sistem yapilandirmasi
# =============================================================================
log "Sistem yapilandirmasi baslatiliyor..."
cp "${SCRIPT_DIR}/chroot-setup.sh" "${ROOTFS_DIR}/tmp/chroot-setup.sh"
chroot "$ROOTFS_DIR" /bin/bash /tmp/chroot-setup.sh
rm -f "${ROOTFS_DIR}/tmp/chroot-setup.sh"
log "Sistem yapilandirmasi tamamlandi"

# =============================================================================
# FAZ 5: KlipperOS-AI dosyalarini kopyala
# =============================================================================
log "KlipperOS-AI dosyalari kopyalaniyor..."
KLIPPEROS_DIR="${ROOTFS_DIR}/opt/klipperos-ai"
mkdir -p "$KLIPPEROS_DIR"

# Python installer paketi
cp -r "${PROJECT_ROOT}/packages" "${KLIPPEROS_DIR}/"
cp "${PROJECT_ROOT}/pyproject.toml" "${KLIPPEROS_DIR}/"

# systemd service
cp "${SCRIPT_DIR}/config/includes.chroot/etc/systemd/system/kos-installer.service" \
    "${ROOTFS_DIR}/etc/systemd/system/"
chroot "$ROOTFS_DIR" systemctl enable kos-installer.service 2>/dev/null || true

# First-boot sentinel
touch "${KLIPPEROS_DIR}/.first-boot"

# Deferred packages listesi
mkdir -p "${KLIPPEROS_DIR}/config/package-lists"
if [ -f "${SCRIPT_DIR}/config/package-lists/klipperos-deferred.list" ]; then
    cp "${SCRIPT_DIR}/config/package-lists/klipperos-deferred.list" \
        "${KLIPPEROS_DIR}/config/package-lists/"
fi

# Sahiplik
chroot "$ROOTFS_DIR" chown -R klipper:klipper /opt/klipperos-ai

log "KlipperOS-AI dosyalari eklendi: $(du -sh "$KLIPPEROS_DIR" | cut -f1)"

# =============================================================================
# FAZ 6: Temizlik — rootfs boyutunu azalt
# =============================================================================
log "Rootfs temizleniyor..."
chroot "$ROOTFS_DIR" /bin/bash -c "
    apt-get clean
    rm -rf /var/lib/apt/lists/*
    rm -rf /tmp/* /var/tmp/*
    rm -f /var/log/*.log /var/log/apt/*
    # Man sayfalari ve dokumantasyon (~50 MB)
    rm -rf /usr/share/man/*
    rm -rf /usr/share/doc/*
    rm -rf /usr/share/info/*
    # Gereksiz locale'ler (en + tr haric)
    find /usr/share/locale -mindepth 1 -maxdepth 1 \
        ! -name 'en*' ! -name 'tr*' ! -name 'locale.alias' \
        -exec rm -rf {} + 2>/dev/null || true
"
log "Temizlik sonrasi rootfs: $(du -sh "$ROOTFS_DIR" | cut -f1)"

# =============================================================================
# FAZ 7: Bind mount'lari kaldir
# =============================================================================
cleanup_mounts
trap - EXIT

# =============================================================================
# FAZ 8: squashfs olustur
# =============================================================================
log "squashfs olusturuluyor (XZ sikistirma)..."
rm -rf "$ISO_DIR"
mkdir -p "${ISO_DIR}/live"

mksquashfs "$ROOTFS_DIR" "${ISO_DIR}/live/filesystem.squashfs" \
    -comp xz -b 1M -Xdict-size 100% -no-recovery -quiet

SQUASHFS_SIZE=$(du -h "${ISO_DIR}/live/filesystem.squashfs" | cut -f1)
log "squashfs olusturuldu: ${SQUASHFS_SIZE}"

# =============================================================================
# FAZ 9: Kernel ve initrd kopyala
# =============================================================================
log "Kernel ve initrd kopyalaniyor..."
cp "${ROOTFS_DIR}"/boot/vmlinuz-* "${ISO_DIR}/live/vmlinuz"
cp "${ROOTFS_DIR}"/boot/initrd.img-* "${ISO_DIR}/live/initrd.img"

# .disk bilgisi
mkdir -p "${ISO_DIR}/.disk"
echo "KlipperOS-AI Live ${VERSION}" > "${ISO_DIR}/.disk/info"

# =============================================================================
# FAZ 10: GRUB yapilandirmasi (BIOS + UEFI)
# =============================================================================
log "GRUB yapilandirmasi hazirlaniyor..."

# --- grub.cfg ---
mkdir -p "${ISO_DIR}/boot/grub"
cp "${SCRIPT_DIR}/config/bootloaders/grub/grub.cfg" "${ISO_DIR}/boot/grub/grub.cfg"

# --- EFI imaj (UEFI boot icin) ---
EFI_IMG="${BUILD_DIR}/efi.img"
dd if=/dev/zero of="$EFI_IMG" bs=1M count=4 2>/dev/null
mkfs.vfat "$EFI_IMG" >/dev/null

MTOOLS_SKIP_CHECK=1 mmd -i "$EFI_IMG" ::/EFI ::/EFI/BOOT

# Signed EFI binary'leri (Secure Boot destegi)
SHIM_EFI="${ROOTFS_DIR}/usr/lib/shim/shimx64.efi.signed"
GRUB_EFI="${ROOTFS_DIR}/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed"

if [ -f "$SHIM_EFI" ] && [ -f "$GRUB_EFI" ]; then
    log "Signed EFI binary'leri kullaniliyor (Secure Boot destekli)"
    mcopy -i "$EFI_IMG" "$SHIM_EFI" ::/EFI/BOOT/BOOTX64.EFI
    mcopy -i "$EFI_IMG" "$GRUB_EFI" ::/EFI/BOOT/grubx64.efi
elif [ -f "$GRUB_EFI" ]; then
    log "Sadece signed GRUB kullaniliyor"
    mcopy -i "$EFI_IMG" "$GRUB_EFI" ::/EFI/BOOT/BOOTX64.EFI
else
    log "Unsigned GRUB EFI olusturuluyor (fallback)"
    grub-mkimage -o "${BUILD_DIR}/bootx64.efi" -p /boot/grub \
        -O x86_64-efi \
        part_gpt part_msdos fat ext2 normal chain boot configfile \
        linux loopback iso9660 search search_label search_fs_uuid \
        search_fs_file test all_video gfxterm font
    mcopy -i "$EFI_IMG" "${BUILD_DIR}/bootx64.efi" ::/EFI/BOOT/BOOTX64.EFI
fi

# EFI icin grub.cfg
mkdir -p "${BUILD_DIR}/efi-grub"
cat > "${BUILD_DIR}/efi-grub/grub.cfg" << 'EFIGRUB'
search --set=root --file /.disk/info
set prefix=($root)/boot/grub
configfile $prefix/grub.cfg
EFIGRUB
mcopy -i "$EFI_IMG" "${BUILD_DIR}/efi-grub/grub.cfg" ::/EFI/BOOT/grub.cfg

# --- BIOS boot (El Torito) ---
CDBOOT_IMG="/usr/lib/grub/i386-pc/cdboot.img"
if [ -f "$CDBOOT_IMG" ]; then
    log "BIOS El Torito imaji olusturuluyor..."
    grub-mkimage -o "${BUILD_DIR}/core.img" -p /boot/grub \
        -O i386-pc \
        biosdisk iso9660 part_gpt part_msdos normal boot linux \
        configfile search search_label search_fs_uuid search_fs_file \
        test all_video gfxterm font
    cat "$CDBOOT_IMG" "${BUILD_DIR}/core.img" > "${ISO_DIR}/boot/grub/bios.img"
else
    warn "BIOS cdboot.img bulunamadi — sadece UEFI boot desteklenecek"
fi

# GRUB modulleri
if [ -d /usr/lib/grub/x86_64-efi ]; then
    cp -r /usr/lib/grub/x86_64-efi "${ISO_DIR}/boot/grub/"
fi
if [ -d /usr/lib/grub/i386-pc ]; then
    cp -r /usr/lib/grub/i386-pc "${ISO_DIR}/boot/grub/"
fi

# =============================================================================
# FAZ 11: xorriso ile ISO olustur
# =============================================================================
log "ISO olusturuluyor..."

BOOT_HYBRID="/usr/lib/grub/i386-pc/boot_hybrid.img"
BIOS_BOOT="${ISO_DIR}/boot/grub/bios.img"

if [ -f "$BOOT_HYBRID" ] && [ -f "$BIOS_BOOT" ]; then
    log "Hybrid boot ISO (BIOS + UEFI)..."
    xorriso -as mkisofs \
        -r -V "KOS-AI-LIVE" \
        -o "$OUTPUT_ISO" \
        --grub2-mbr "$BOOT_HYBRID" \
        -partition_offset 16 \
        --mbr-force-bootable \
        -append_partition 2 28732ac11ff8d211ba4b00a0c93ec93b "$EFI_IMG" \
        -appended_part_as_gpt \
        -iso_mbr_part_type a2a0d0ebe5b9334487c068b6b72699c7 \
        -c '/boot.catalog' \
        -b '/boot/grub/bios.img' \
            -no-emul-boot -boot-load-size 4 -boot-info-table --grub2-boot-info \
        -eltorito-alt-boot \
        -e '--interval:appended_partition_2:::' \
            -no-emul-boot \
        "$ISO_DIR" \
        2>&1 | tail -5
elif [ -f "$EFI_IMG" ]; then
    log "UEFI-only ISO olusturuluyor..."
    xorriso -as mkisofs \
        -r -V "KOS-AI-LIVE" \
        -o "$OUTPUT_ISO" \
        -append_partition 2 28732ac11ff8d211ba4b00a0c93ec93b "$EFI_IMG" \
        -appended_part_as_gpt \
        -e '--interval:appended_partition_2:::' \
            -no-emul-boot \
        "$ISO_DIR" \
        2>&1 | tail -5
else
    err "Boot imajlari olusturulamadi!"
    exit 1
fi

# =============================================================================
# FAZ 12: Sonuc ve temizlik
# =============================================================================
if [ -f "$OUTPUT_ISO" ] && [ -s "$OUTPUT_ISO" ]; then
    ISO_SIZE=$(du -h "$OUTPUT_ISO" | cut -f1)
    ISO_SHA=$(sha256sum "$OUTPUT_ISO" | awk '{print $1}')
    echo "${ISO_SHA}  ${IMAGE_NAME}.iso" > "${OUTPUT_ISO}.sha256"

    echo ""
    log "============================================"
    log "  KlipperOS-AI Live ISO olusturuldu!"
    log "============================================"
    log "Dosya:    ${OUTPUT_ISO}"
    log "Boyut:    ${ISO_SIZE}"
    log "SHA256:   ${ISO_SHA}"
    log "squashfs: ${SQUASHFS_SIZE}"
    echo ""
    echo -e "${GREEN}USB'ye yazmak icin:${NC}"
    echo "  sudo dd if=${IMAGE_NAME}.iso of=/dev/sdX bs=4M status=progress"

    if [ "${CLEANUP:-1}" = "1" ]; then
        rm -rf "$ISO_DIR"
        rm -f "${BUILD_DIR}/efi.img" "${BUILD_DIR}/core.img"
        rm -rf "${BUILD_DIR}/efi-grub"
    fi
else
    err "ISO olusturulamadi!"
    exit 1
fi
