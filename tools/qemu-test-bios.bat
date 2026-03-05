@echo off
REM =============================================================================
REM KlipperOS-AI — QEMU Test: ISO'dan BIOS (Legacy) Boot
REM =============================================================================
REM UEFI destegi olmayan donanim senaryosunu test eder.
REM OVMF kullanilmaz → SeaBIOS (QEMU default BIOS) ile boot eder.
REM
REM Kullanim: tools\qemu-test-bios.bat
REM =============================================================================

set QEMU=%USERPROFILE%\scoop\apps\qemu\current\qemu-system-x86_64w.exe
set ISO=C:\linux_ai\klipperos-v4.0.0-netinstall.iso
set DISK=C:\linux_ai\test-disk-bios.qcow2

REM Kontroller
if not exist "%QEMU%" (
    echo [HATA] QEMU bulunamadi: %QEMU%
    echo   Kur: scoop install qemu
    pause
    exit /b 1
)
if not exist "%ISO%" (
    echo [HATA] ISO bulunamadi: %ISO%
    echo   WSL2'de build edin: sudo ./image-builder/build-netinstall-image.sh
    pause
    exit /b 1
)
if not exist "%DISK%" (
    echo [INFO] BIOS test diski olusturuluyor: %DISK%
    "%USERPROFILE%\scoop\apps\qemu\current\qemu-img.exe" create -f qcow2 "%DISK%" 20G
)

echo.
echo === KlipperOS-AI QEMU Test (BIOS / Legacy) ===
echo   ISO:  %ISO%
echo   Disk: %DISK%
echo   Mod:  BIOS (SeaBIOS — MBR + GRUB i386-pc)
echo.
echo   SSH:  ssh -p 2223 klipper@localhost
echo   Kapat: Ctrl+C veya pencereyi kapat
echo.

"%QEMU%" ^
    -m 2G ^
    -smp 2 ^
    -cpu max ^
    -cdrom "%ISO%" ^
    -boot d ^
    -drive file="%DISK%",if=virtio,format=qcow2 ^
    -nic user,model=virtio-net-pci,hostfwd=tcp::2223-:22 ^
    -display sdl ^
    -vga virtio
