@echo off
REM KlipperOS-AI QEMU Direct Boot — Serial Port 5555
set ISO=C:\linux_ai\klipperos-v4.0.0-netinstall.iso
set DISK=C:\linux_ai\test-disk.qcow2
set KERNEL=C:\linux_ai\qemu-boot\vmlinuz
set INITRD=C:\linux_ai\qemu-boot\initrd.img
set QEMU=C:\Users\sevdi\scoop\apps\qemu\current\qemu-system-x86_64.exe

REM Fresh disk
if exist "%DISK%" del /f "%DISK%"
"C:\Users\sevdi\scoop\apps\qemu\current\qemu-img.exe" create -f qcow2 "%DISK%" 20G

REM Launch QEMU — direct kernel boot bypasses GRUB
start "" "%QEMU%" ^
    -m 2G ^
    -smp 2 ^
    -cpu max ^
    -cdrom "%ISO%" ^
    -kernel "%KERNEL%" ^
    -initrd "%INITRD%" ^
    -append "boot=live components console=ttyS0,115200 locales=tr_TR.UTF-8 keyboard-layouts=tr" ^
    -drive "file=%DISK%,if=virtio,format=qcow2" ^
    -nic user,model=virtio-net-pci ^
    -serial tcp::5555,server,nowait ^
    -display sdl

echo QEMU started on serial port 5555
