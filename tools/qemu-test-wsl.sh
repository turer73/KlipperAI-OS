#!/bin/bash
# =============================================================================
# KlipperOS-AI — QEMU Test: WSL2 icinde BIOS headless
# =============================================================================
# ISO'dan boot → TUI installer → disk kurulum → GRUB → reboot testi
#
# Kullanim: wsl -d Ubuntu -- bash tools/qemu-test-wsl.sh
# Serial log: /tmp/qemu-serial.log
# =============================================================================

set -e

ISO="/mnt/c/linux_ai/klipperos-v4.0.0-netinstall.iso"
DISK="/mnt/c/linux_ai/test-disk.qcow2"
SERIAL_LOG="/tmp/qemu-serial.log"

# Kontrol
if [ ! -f "$ISO" ]; then
    echo "[HATA] ISO bulunamadi: $ISO"
    echo "  Build: sudo ./image-builder/build-netinstall-image.sh"
    exit 1
fi

# Diski sifirla (temiz test)
echo "[INFO] Test diski sifirlaniyor (20G)..."
qemu-img create -f qcow2 "$DISK" 20G

echo
echo "=== KlipperOS-AI QEMU Test (BIOS / Headless) ==="
echo "  ISO:  $ISO"
echo "  Disk: $DISK"
echo "  Mod:  BIOS (SeaBIOS — MBR + GRUB i386-pc)"
echo "  Serial: $SERIAL_LOG"
echo
echo "  SSH (kurulum sonrasi): ssh -p 2222 klipper@localhost"
echo "  Durdur: Ctrl+A, X (QEMU monitor)"
echo

# Headless QEMU — serial console + monitor
qemu-system-x86_64 \
    -m 2G \
    -smp 2 \
    -cpu max \
    -cdrom "$ISO" \
    -boot d \
    -drive file="$DISK",if=virtio,format=qcow2 \
    -nic user,model=virtio-net-pci,hostfwd=tcp::2222-:22 \
    -nographic \
    -serial "file:$SERIAL_LOG" \
    -monitor stdio
