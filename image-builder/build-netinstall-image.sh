#!/bin/bash
# =============================================================================
# KlipperOS-AI — Netinstall ISO Builder
# =============================================================================
# ~200-300 MB'lik minimal ISO uretir. Sadece boot + ag + wizard icerir.
# Klipper, AI, X11, gcc-arm vb. tamami ilk boot'ta internetten indirilir.
#
# Kullanim:
#   sudo ./build-netinstall-image.sh
#
# Hedef boyut: ~1 GB (firmware dahil, varsayilan)
#
# Ortam degiskenleri:
#   SKIP_DEBOOTSTRAP=1   — Onceki rootfs'i yeniden kullan
#   CLEANUP=0            — Gecici dosyalari silme
#   NO_FIRMWARE=1        — linux-firmware HARIC tut (WiFi calismaz, ISO ~350 MB)
#   ARCH=arm64           — Mimari degistir (varsayilan: amd64)
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
VERSION="4.0.0-netinstall"
IMAGE_NAME="klipperos-v${VERSION}"

# Build dizini: Linux native FS kullan (NTFS debootstrap'i bozar)
BUILD_DIR="/tmp/kos-build"

# Ubuntu Noble (24.04)
UBUNTU_SUITE="noble"
UBUNTU_MIRROR="http://archive.ubuntu.com/ubuntu"
ARCH="${ARCH:-amd64}"

# Build dizinleri
ROOTFS_DIR="${BUILD_DIR}/rootfs"
ISO_DIR="${BUILD_DIR}/iso-staging"
OUTPUT_ISO="${BUILD_DIR}/${IMAGE_NAME}.iso"

# Renkler
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
NC='\033[0m'

log()  { echo -e "${GREEN}[BUILD]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err()  { echo -e "${RED}[ERROR]${NC} $*" >&2; }
info() { echo -e "${CYAN}[INFO]${NC} $*"; }

# =============================================================================
# FAZ 0: Hazirlik
# =============================================================================
if [ "$(id -u)" -ne 0 ]; then
    err "Root yetkisi gerekli: sudo $0"
    exit 1
fi

info "KlipperOS-AI Netinstall ISO Builder v${VERSION}"
info "Mimari: ${ARCH}"
info "Hedef: Minimal boot ISO (~200-350 MB)"
echo ""

REQUIRED_CMDS=(debootstrap mksquashfs xorriso grub-mkimage mcopy mkfs.vfat)
for cmd in "${REQUIRED_CMDS[@]}"; do
    if ! command -v "$cmd" &>/dev/null; then
        err "${cmd} bulunamadi. Gerekli paketler kuruluyor..."
        apt-get update -qq
        apt-get install -y -qq debootstrap squashfs-tools xorriso \
            grub-efi-amd64-bin grub-pc-bin mtools dosfstools
        break
    fi
done

log "Build dizini: ${BUILD_DIR}"
mkdir -p "$BUILD_DIR"

# =============================================================================
# FAZ 1: debootstrap — Ultra minimal rootfs
# =============================================================================
if [ "${SKIP_DEBOOTSTRAP:-}" = "1" ] && [ -d "${ROOTFS_DIR}/bin" ]; then
    log "Mevcut rootfs kullaniliyor (SKIP_DEBOOTSTRAP=1)"
else
    log "debootstrap baslatiliyor: ${UBUNTU_SUITE} (${ARCH})..."
    rm -rf "$ROOTFS_DIR"

    # --variant=minbase: en kucuk olasi rootfs
    # --include: sadece boot + ag + wizard icin gereken minimum
    debootstrap --arch="${ARCH}" --variant=minbase \
        --include=systemd-sysv,dbus \
        "$UBUNTU_SUITE" "$ROOTFS_DIR" "$UBUNTU_MIRROR"

    log "debootstrap tamamlandi: $(du -sh "$ROOTFS_DIR" | cut -f1)"
fi

# =============================================================================
# FAZ 2: APT kaynaklari
# =============================================================================
log "APT kaynaklari ayarlaniyor..."
cat > "${ROOTFS_DIR}/etc/apt/sources.list" << EOF
deb ${UBUNTU_MIRROR} ${UBUNTU_SUITE} main restricted universe
deb ${UBUNTU_MIRROR} ${UBUNTU_SUITE}-updates main restricted universe
deb http://security.ubuntu.com/ubuntu ${UBUNTU_SUITE}-security main restricted universe
EOF

# =============================================================================
# FAZ 3: Bind mount'lar
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

# =============================================================================
# FAZ 4: Minimal paket kurulumu
# =============================================================================
# SADECE boot + ag + wizard icin gereken minimum paketler
# Diger her sey internetten indirilecek
PACKAGES=(
    # Kernel + live-boot (zorunlu)
    linux-image-generic
    live-boot

    # Bootloader (zorunlu)
    grub-efi-amd64-signed
    shim-signed
    grub-pc-bin

    # Ag (ilk boot'ta internet baglantisi icin zorunlu)
    network-manager
    wpasupplicant
    rfkill

    # Python (wizard icin minimum)
    python3

    # Wizard araclari (TUI + klavye)
    whiptail
    kbd

    # Disk kurulumu icin
    parted
    dosfstools
    rsync

    # Temel (SSH + DNS)
    openssh-server
    avahi-daemon
    sudo
    ca-certificates
    curl
)

# linux-firmware (WiFi surucileri — varsayilan DAHIL)
# Kucuk ISO icin: NO_FIRMWARE=1 ile calistirin
if [ "${NO_FIRMWARE:-}" = "1" ]; then
    info "linux-firmware DAHIL DEGIL — ISO daha kucuk (~200-350 MB)"
    info "WiFi icin: NO_FIRMWARE=1 kaldirilmali"
else
    PACKAGES+=(linux-firmware)
    info "linux-firmware DAHIL — WiFi destegi aktif"
fi

PKG_LIST="${PACKAGES[*]}"
log "Paketler kuruluyor (${#PACKAGES[@]} paket — netinstall minimum)..."
chroot "$ROOTFS_DIR" /bin/bash -c "
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y --no-install-recommends $PKG_LIST
    apt-get clean
"
log "Paket kurulumu tamamlandi: $(du -sh "$ROOTFS_DIR" | cut -f1)"

# =============================================================================
# FAZ 5: chroot-setup.sh — Sistem yapilandirmasi
# =============================================================================
log "Sistem yapilandirmasi baslatiliyor..."
cp "${SCRIPT_DIR}/chroot-setup.sh" "${ROOTFS_DIR}/tmp/chroot-setup.sh"
chroot "$ROOTFS_DIR" /bin/bash /tmp/chroot-setup.sh
rm -f "${ROOTFS_DIR}/tmp/chroot-setup.sh"
log "Sistem yapilandirmasi tamamlandi"

# =============================================================================
# FAZ 6: KlipperOS-AI dosyalarini kopyala (sadece installer + scripts)
# =============================================================================
log "KlipperOS-AI installer dosyalari kopyalaniyor..."
KLIPPEROS_DIR="${ROOTFS_DIR}/opt/klipperos-ai"
mkdir -p "$KLIPPEROS_DIR"

# Python installer paketi (TUI + API modelleri)
cp -r "${PROJECT_ROOT}/packages" "${KLIPPEROS_DIR}/"
cp "${PROJECT_ROOT}/pyproject.toml" "${KLIPPEROS_DIR}/"

# Install scriptleri (profil bazli kurulum — internetten indirecek)
mkdir -p "${KLIPPEROS_DIR}/scripts"
cp "${PROJECT_ROOT}"/scripts/install-*.sh "${KLIPPEROS_DIR}/scripts/" 2>/dev/null || true
cp "${PROJECT_ROOT}"/scripts/setup-*.sh "${KLIPPEROS_DIR}/scripts/" 2>/dev/null || true
cp "${PROJECT_ROOT}"/scripts/generate-*.sh "${KLIPPEROS_DIR}/scripts/" 2>/dev/null || true
chmod +x "${KLIPPEROS_DIR}/scripts/"*.sh 2>/dev/null || true

# AI monitor dosyalari (internet sonrasi kurulacak ama config icin gerekli)
if [ -d "${PROJECT_ROOT}/ai-monitor" ]; then
    cp -r "${PROJECT_ROOT}/ai-monitor" "${KLIPPEROS_DIR}/"
fi

# Config dosyalari
if [ -d "${PROJECT_ROOT}/config" ]; then
    cp -r "${PROJECT_ROOT}/config" "${KLIPPEROS_DIR}/"
fi

# Araclar (kos_plr, kos_rewind vb.)
if [ -d "${PROJECT_ROOT}/tools" ]; then
    cp -r "${PROJECT_ROOT}/tools" "${KLIPPEROS_DIR}/"
fi

# First-boot wizard
cp "${SCRIPT_DIR}/first-boot-wizard.sh" "${KLIPPEROS_DIR}/first-boot-wizard.sh"
chmod +x "${KLIPPEROS_DIR}/first-boot-wizard.sh"

# Wizard'i /usr/local/bin'e kopyala (kolay erisim)
cp "${SCRIPT_DIR}/first-boot-wizard.sh" "${ROOTFS_DIR}/usr/local/bin/klipperai-wizard"
chmod +x "${ROOTFS_DIR}/usr/local/bin/klipperai-wizard"

# Systemd: kos-installer.service (wizard'i first-boot'ta calistirir)
if [ -f "${SCRIPT_DIR}/config/includes.chroot/etc/systemd/system/kos-installer.service" ]; then
    cp "${SCRIPT_DIR}/config/includes.chroot/etc/systemd/system/kos-installer.service" \
        "${ROOTFS_DIR}/etc/systemd/system/"
    chroot "$ROOTFS_DIR" systemctl enable kos-installer.service 2>/dev/null || true
    log "kos-installer.service etkinlestirildi"
fi

# .bashrc fallback: service basarisiz olursa login'de Python installer calistir
cat >> "${ROOTFS_DIR}/home/klipper/.bashrc" << 'WIZARD_FALLBACK'

# --- KlipperOS-AI First-Boot Installer Fallback ---
if [ -f /opt/klipperos-ai/.first-boot ]; then
    echo ""
    echo "==================================================="
    echo "  KlipperOS-AI - Ilk Kurulum Sihirbazi"
    echo "==================================================="
    echo ""
    echo "  Installer baslatiliyor... (3 saniye)"
    sleep 3
    cd /opt/klipperos-ai && exec sudo /usr/bin/python3 -m packages.installer
fi
WIZARD_FALLBACK

# Deferred packages listesi
mkdir -p "${KLIPPEROS_DIR}/config/package-lists"
if [ -f "${SCRIPT_DIR}/config/package-lists/klipperos-deferred.list" ]; then
    cp "${SCRIPT_DIR}/config/package-lists/klipperos-deferred.list" \
        "${KLIPPEROS_DIR}/config/package-lists/"
fi

# First-boot sentinel
touch "${KLIPPEROS_DIR}/.first-boot"

# Sahiplik
chroot "$ROOTFS_DIR" chown -R klipper:klipper /opt/klipperos-ai

log "KlipperOS-AI dosyalari eklendi: $(du -sh "$KLIPPEROS_DIR" | cut -f1)"

# =============================================================================
# FAZ 7: Agresif temizlik — minimum boyut
# =============================================================================
log "Agresif rootfs temizligi basliyor..."
chroot "$ROOTFS_DIR" /bin/bash -c "
    # APT cache
    apt-get clean
    rm -rf /var/lib/apt/lists/*
    rm -rf /var/cache/apt/archives/*.deb

    # Gecici dosyalar
    rm -rf /tmp/* /var/tmp/*
    rm -f /var/log/*.log /var/log/apt/*

    # Dokumantasyon (~50 MB tasarruf)
    rm -rf /usr/share/man/*
    rm -rf /usr/share/doc/*
    rm -rf /usr/share/info/*
    rm -rf /usr/share/lintian/*
    rm -rf /usr/share/bash-completion/*

    # Locale (sadece en + tr)
    find /usr/share/locale -mindepth 1 -maxdepth 1 \
        ! -name 'en*' ! -name 'tr*' ! -name 'locale.alias' \
        -exec rm -rf {} + 2>/dev/null || true

    # Gereksiz kernel modulleri icin kaynak dosyalari
    rm -rf /usr/src/*
    rm -rf /lib/modules/*/build
    rm -rf /lib/modules/*/source

    # Python cache
    find / -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
    find / -name '*.pyc' -delete 2>/dev/null || true
"
log "Temizlik sonrasi rootfs: $(du -sh "$ROOTFS_DIR" | cut -f1)"

# =============================================================================
# FAZ 8: Bind mount'lari kaldir
# =============================================================================
cleanup_mounts
trap - EXIT

# =============================================================================
# FAZ 9: squashfs olustur (maksimum sikistirma)
# =============================================================================
log "squashfs olusturuluyor (XZ, maksimum sikistirma)..."
rm -rf "$ISO_DIR"
mkdir -p "${ISO_DIR}/live"

mksquashfs "$ROOTFS_DIR" "${ISO_DIR}/live/filesystem.squashfs" \
    -comp xz -b 1M -Xdict-size 100% -Xbcj x86 -no-recovery -quiet

SQUASHFS_SIZE=$(du -h "${ISO_DIR}/live/filesystem.squashfs" | cut -f1)
log "squashfs olusturuldu: ${SQUASHFS_SIZE}"

# =============================================================================
# FAZ 10: Kernel + initrd
# =============================================================================
log "Kernel ve initrd kopyalaniyor..."
cp "${ROOTFS_DIR}"/boot/vmlinuz-* "${ISO_DIR}/live/vmlinuz"
cp "${ROOTFS_DIR}"/boot/initrd.img-* "${ISO_DIR}/live/initrd.img"

mkdir -p "${ISO_DIR}/.disk"
echo "KlipperOS-AI Netinstall ${VERSION}" > "${ISO_DIR}/.disk/info"

# =============================================================================
# FAZ 11: GRUB yapilandirmasi (BIOS + UEFI)
# =============================================================================
log "GRUB yapilandirmasi hazirlaniyor..."

# --- grub.cfg (netinstall icin ozel) ---
mkdir -p "${ISO_DIR}/boot/grub"
cat > "${ISO_DIR}/boot/grub/grub.cfg" << 'GRUBCFG'
set default=0
set timeout=5

# Renkler
set color_normal=white/black
set color_highlight=black/cyan

menuentry "KlipperOS-AI -- Kur (Netinstall)" {
    linux /live/vmlinuz boot=live components quiet splash \
        toram locales=tr_TR.UTF-8 keyboard-layouts=tr
    initrd /live/initrd.img
}

menuentry "KlipperOS-AI -- Kur (Guvenli Mod)" {
    linux /live/vmlinuz boot=live components nomodeset \
        toram locales=tr_TR.UTF-8 keyboard-layouts=tr
    initrd /live/initrd.img
}

menuentry "KlipperOS-AI -- RAM'de Calistir (RAM > 2GB)" {
    linux /live/vmlinuz boot=live components toram quiet splash \
        locales=tr_TR.UTF-8 keyboard-layouts=tr
    initrd /live/initrd.img
}

menuentry "Baslat -- Debug Modu" {
    linux /live/vmlinuz boot=live components \
        locales=tr_TR.UTF-8 keyboard-layouts=tr systemd.log_level=debug
    initrd /live/initrd.img
}
GRUBCFG

# --- EFI imaj ---
EFI_IMG="${BUILD_DIR}/efi.img"
dd if=/dev/zero of="$EFI_IMG" bs=1M count=4 2>/dev/null
mkfs.vfat "$EFI_IMG" >/dev/null

MTOOLS_SKIP_CHECK=1 mmd -i "$EFI_IMG" ::/EFI ::/EFI/BOOT

# Signed EFI binary (Secure Boot)
SHIM_EFI="${ROOTFS_DIR}/usr/lib/shim/shimx64.efi.signed"
GRUB_EFI="${ROOTFS_DIR}/usr/lib/grub/x86_64-efi-signed/grubx64.efi.signed"

if [ -f "$SHIM_EFI" ] && [ -f "$GRUB_EFI" ]; then
    log "Signed EFI: Secure Boot destekli"
    mcopy -i "$EFI_IMG" "$SHIM_EFI" ::/EFI/BOOT/BOOTX64.EFI
    mcopy -i "$EFI_IMG" "$GRUB_EFI" ::/EFI/BOOT/grubx64.efi
elif [ -f "$GRUB_EFI" ]; then
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

# EFI grub.cfg
mkdir -p "${BUILD_DIR}/efi-grub"
cat > "${BUILD_DIR}/efi-grub/grub.cfg" << 'EFIGRUB'
search --set=root --file /.disk/info
set prefix=($root)/boot/grub
configfile $prefix/grub.cfg
EFIGRUB
mcopy -i "$EFI_IMG" "${BUILD_DIR}/efi-grub/grub.cfg" ::/EFI/BOOT/grub.cfg

# --- BIOS boot ---
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
    warn "BIOS cdboot.img bulunamadi — sadece UEFI boot"
fi

# GRUB modulleri
if [ -d /usr/lib/grub/x86_64-efi ]; then
    cp -r /usr/lib/grub/x86_64-efi "${ISO_DIR}/boot/grub/"
fi
if [ -d /usr/lib/grub/i386-pc ]; then
    cp -r /usr/lib/grub/i386-pc "${ISO_DIR}/boot/grub/"
fi

# =============================================================================
# FAZ 12: xorriso ile ISO olustur
# =============================================================================
log "ISO olusturuluyor..."

BOOT_HYBRID="/usr/lib/grub/i386-pc/boot_hybrid.img"
BIOS_BOOT="${ISO_DIR}/boot/grub/bios.img"

if [ -f "$BOOT_HYBRID" ] && [ -f "$BIOS_BOOT" ]; then
    log "Hybrid boot ISO (BIOS + UEFI)..."
    xorriso -as mkisofs \
        -r -V "KOS-NETINST" \
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
    log "UEFI-only ISO..."
    xorriso -as mkisofs \
        -r -V "KOS-NETINST" \
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
# FAZ 13: Sonuc
# =============================================================================
if [ -f "$OUTPUT_ISO" ] && [ -s "$OUTPUT_ISO" ]; then
    ISO_SIZE=$(du -h "$OUTPUT_ISO" | cut -f1)
    ISO_SIZE_MB=$(du -m "$OUTPUT_ISO" | cut -f1)
    ISO_SHA=$(sha256sum "$OUTPUT_ISO" | awk '{print $1}')
    echo "${ISO_SHA}  ${IMAGE_NAME}.iso" > "${OUTPUT_ISO}.sha256"

    echo ""
    log "============================================"
    log "  KlipperOS-AI Netinstall ISO"
    log "============================================"
    log "Dosya:     ${OUTPUT_ISO}"
    log "Boyut:     ${ISO_SIZE} (${ISO_SIZE_MB} MB)"
    log "SHA256:    ${ISO_SHA}"
    log "squashfs:  ${SQUASHFS_SIZE}"
    echo ""

    if [ "$ISO_SIZE_MB" -lt 2000 ]; then
        echo -e "${GREEN}  Boyut hedefi basarili! (firmware dahil, < 2 GB)${NC}"
    else
        echo -e "${YELLOW}  ISO beklentiden buyuk (> 2 GB).${NC}"
    fi

    echo ""
    echo -e "${GREEN}USB'ye yazmak icin:${NC}"
    echo "  sudo dd if=${OUTPUT_ISO} of=/dev/sdX bs=4M status=progress oflag=sync"
    echo ""
    echo -e "${GREEN}QEMU ile test:${NC}"
    echo "  qemu-system-x86_64 -m 2G -cdrom ${OUTPUT_ISO} -boot d \\"
    echo "    -enable-kvm -cpu host -smp 2 \\"
    echo "    -nic user,model=virtio-net-pci \\"
    echo "    -drive file=disk.qcow2,if=virtio,format=qcow2"
    echo ""
    echo -e "${CYAN}NOT: Bu ISO sadece boot + ag icin yeterli.${NC}"
    echo -e "${CYAN}Klipper, AI, diger paketler ilk boot'ta internetten indirilir.${NC}"
    echo -e "${CYAN}WiFi ve Ethernet destegi varsayilan olarak aktif.${NC}"

    if [ "${CLEANUP:-1}" = "1" ]; then
        rm -rf "$ISO_DIR"
        rm -f "${BUILD_DIR}/efi.img" "${BUILD_DIR}/core.img"
        rm -rf "${BUILD_DIR}/efi-grub"
    fi
else
    err "ISO olusturulamadi!"
    exit 1
fi
