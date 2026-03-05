@echo off
REM =============================================================================
REM KlipperOS-AI — QEMU Test: ISO'dan UEFI Boot
REM =============================================================================
REM Disk kurulumunu test etmek icin: ISO boot → installer → diske kur
REM
REM NOT: ISO, -cdrom yerine raw drive olarak tanitilir.
REM      Boylece ISO sonundaki EFI partition (appended_partition_2)
REM      UEFI firmware tarafindan gorulebilir.
REM
REM Kullanim: tools\qemu-test.bat
REM =============================================================================

set QEMU=%USERPROFILE%\scoop\apps\qemu\current\qemu-system-x86_64w.exe
set ISO=C:\linux_ai\klipperos-v4.0.0-netinstall.iso
set DISK=C:\linux_ai\test-disk.qcow2
set OVMF=%USERPROFILE%\scoop\apps\qemu\current\share\edk2-x86_64-code.fd

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
    echo [INFO] Sanal disk olusturuluyor: %DISK%
    "%USERPROFILE%\scoop\apps\qemu\current\qemu-img.exe" create -f qcow2 "%DISK%" 20G
)

echo.
echo === KlipperOS-AI QEMU Test (UEFI) ===
echo   ISO:  %ISO%
echo   Disk: %DISK%
echo   Mod:  UEFI (pflash + raw ISO)
echo.
echo   SSH:  ssh -p 2222 klipper@localhost
echo   Kapat: Ctrl+C veya pencereyi kapat
echo.

REM ISO'yu raw drive olarak tanimla (EFI partition gorunsun)
REM Hedef diski virtio ile tanimla
"%QEMU%" ^
    -m 2G ^
    -smp 2 ^
    -cpu max ^
    -drive file="%ISO%",media=cdrom,readonly=on,if=none,id=iso ^
    -device ide-cd,drive=iso,bootindex=1 ^
    -drive file="%DISK%",if=virtio,format=qcow2 ^
    -drive if=pflash,format=raw,readonly=on,file="%OVMF%" ^
    -nic user,model=virtio-net-pci,hostfwd=tcp::2222-:22 ^
    -display sdl ^
    -vga virtio
