@echo off
REM =============================================================================
REM KlipperOS-AI — QEMU Test: Diskten Boot (Kurulum Sonrasi)
REM =============================================================================
REM ISO OLMADAN boot → GRUB → Linux → kalici sistem testi.
REM Kurulum tamamlandiktan sonra bu script ile diskten boot edin.
REM
REM Kullanim: tools\qemu-test-reboot.bat [uefi|bios]
REM   uefi  → OVMF UEFI firmware ile boot (varsayilan)
REM   bios  → SeaBIOS legacy boot
REM =============================================================================

set QEMU=%USERPROFILE%\scoop\apps\qemu\current\qemu-system-x86_64w.exe
set OVMF=%USERPROFILE%\scoop\apps\qemu\current\share\edk2-x86_64-code.fd

REM Kontroller
if not exist "%QEMU%" (
    echo [HATA] QEMU bulunamadi: %QEMU%
    echo   Kur: scoop install qemu
    pause
    exit /b 1
)

REM Mod secimi (varsayilan: uefi)
set MODE=%~1
if "%MODE%"=="" set MODE=uefi

if /I "%MODE%"=="uefi" (
    set DISK=C:\linux_ai\test-disk.qcow2
    set BIOS_FLAG=-drive if=pflash,format=raw,readonly=on,file="%OVMF%"
    set SSH_PORT=2222
    echo === KlipperOS-AI — Diskten Boot [UEFI] ===
) else if /I "%MODE%"=="bios" (
    set DISK=C:\linux_ai\test-disk-bios.qcow2
    set BIOS_FLAG=
    set SSH_PORT=2223
    echo === KlipperOS-AI — Diskten Boot [BIOS] ===
) else (
    echo [HATA] Gecersiz mod: %MODE%
    echo   Kullanim: qemu-test-reboot.bat [uefi^|bios]
    pause
    exit /b 1
)

if not exist "%DISK%" (
    echo [HATA] Sanal disk bulunamadi: %DISK%
    echo   Once qemu-test.bat veya qemu-test-bios.bat ile kurulum yapin.
    pause
    exit /b 1
)

echo   Disk: %DISK%
echo   Mod:  %MODE%
echo.
echo   SSH:  ssh -p %SSH_PORT% klipper@localhost
echo   Kapat: Ctrl+C veya pencereyi kapat
echo.
echo   NOT: ISO yok — sadece diskten boot ediliyor.
echo        GRUB ekrani gorunmuyorsa kurulum basarisiz olmus olabilir.
echo.

"%QEMU%" ^
    -m 2G ^
    -smp 2 ^
    -cpu max ^
    -drive file="%DISK%",if=virtio,format=qcow2 ^
    %BIOS_FLAG% ^
    -nic user,model=virtio-net-pci,hostfwd=tcp::%SSH_PORT%-:22 ^
    -display sdl ^
    -vga virtio
