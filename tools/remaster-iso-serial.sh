#!/bin/bash
# ISO'yu console=ttyS0 ile yeniden olustur (grub.cfg update)
set -e

ISO="/mnt/c/linux_ai/klipperos-v4.0.0-netinstall.iso"
ISO_NEW="/mnt/c/linux_ai/klipperos-v4.0.0-serial.iso"
WORK="/tmp/iso-remaster"

# Temizlik
rm -rf "$WORK"
mkdir -p "$WORK"

# ISO icerigini cikart
echo "[1/4] ISO icerigini cikartiyor..."
xorriso -osirrox on -indev "$ISO" -extract / "$WORK" 2>&1 | tail -3
chmod -R u+w "$WORK"

# grub.cfg'ye console=ttyS0 ekle
echo "[2/4] grub.cfg guncelleniyor..."
GRUB="$WORK/boot/grub/grub.cfg"

# Her linux satirina console=ttyS0 ekle
sed -i 's/keyboard-layouts=tr$/keyboard-layouts=tr console=tty0 console=ttyS0,115200/' "$GRUB"

echo "--- Updated grub.cfg ---"
cat "$GRUB"

# ISO yeniden olustur
echo "[3/4] ISO yeniden olusturuluyor..."

# efiboot.img varsa UEFI de ekle
if [ -f "$WORK/boot/grub/efiboot.img" ]; then
    echo "  UEFI + BIOS hibrit ISO"
    xorriso -as mkisofs \
        -o "$ISO_NEW" \
        -iso-level 3 \
        -full-iso9660-filenames \
        -volid "KLIPPEROS_AI" \
        -eltorito-boot boot/grub/bios.img \
        -no-emul-boot \
        -boot-load-size 4 \
        -boot-info-table \
        --grub2-boot-info \
        --grub2-mbr /usr/lib/grub/i386-pc/boot_hybrid.img \
        -append_partition 2 0xef "$WORK/boot/grub/efiboot.img" \
        -eltorito-alt-boot \
        -e --interval:appended_partition_2:all:: \
        -no-emul-boot \
        -isohybrid-gpt-basdat \
        "$WORK" 2>&1 | tail -5
else
    echo "  BIOS-only ISO"
    xorriso -as mkisofs \
        -o "$ISO_NEW" \
        -iso-level 3 \
        -full-iso9660-filenames \
        -volid "KLIPPEROS_AI" \
        -eltorito-boot boot/grub/bios.img \
        -no-emul-boot \
        -boot-load-size 4 \
        -boot-info-table \
        --grub2-boot-info \
        --grub2-mbr /usr/lib/grub/i386-pc/boot_hybrid.img \
        "$WORK" 2>&1 | tail -5
fi

echo "[4/4] Temizlik..."
rm -rf "$WORK"

ls -lh "$ISO_NEW"
echo "DONE! Serial-enabled ISO: $ISO_NEW"
