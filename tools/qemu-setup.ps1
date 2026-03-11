# =============================================================================
# KlipperOS-AI — QEMU Test Ortami Kurulumu
# =============================================================================
# Kullanim: powershell -ExecutionPolicy Bypass -File tools\qemu-setup.ps1
# =============================================================================

$ErrorActionPreference = "Stop"

$QEMU_DIR = "$env:USERPROFILE\scoop\apps\qemu\current"
$QEMU_IMG = "$QEMU_DIR\qemu-img.exe"
$DISK_PATH = "C:\linux_ai\test-disk.qcow2"
$DISK_SIZE = "20G"

Write-Host "`n=== KlipperOS-AI QEMU Test Ortami ===" -ForegroundColor Cyan

# 1. QEMU kontrolu
if (-not (Test-Path $QEMU_IMG)) {
    Write-Host "[HATA] QEMU bulunamadi: $QEMU_DIR" -ForegroundColor Red
    Write-Host "  Kur: scoop install qemu" -ForegroundColor Yellow
    exit 1
}
$version = & "$QEMU_DIR\qemu-system-x86_64.exe" --version 2>&1 | Select-Object -First 1
Write-Host "[OK] QEMU: $version" -ForegroundColor Green

# 2. ISO kontrolu
$ISO_PATH = "C:\linux_ai\klipperos-v4.0.0-netinstall.iso"
if (Test-Path $ISO_PATH) {
    $isoSize = [math]::Round((Get-Item $ISO_PATH).Length / 1MB)
    Write-Host "[OK] ISO: $ISO_PATH ($isoSize MB)" -ForegroundColor Green
} else {
    Write-Host "[UYARI] ISO bulunamadi: $ISO_PATH" -ForegroundColor Yellow
    Write-Host "  WSL2 icinde build edin: sudo ./image-builder/build-netinstall-image.sh" -ForegroundColor Yellow
}

# 3. Sanal disk olustur
if (Test-Path $DISK_PATH) {
    Write-Host "[OK] Sanal disk mevcut: $DISK_PATH" -ForegroundColor Green
    $response = Read-Host "  Yeniden olusturmak ister misiniz? (e/h)"
    if ($response -eq "e") {
        Remove-Item $DISK_PATH -Force
    } else {
        Write-Host "  Mevcut disk korunuyor." -ForegroundColor Gray
    }
}

if (-not (Test-Path $DISK_PATH)) {
    Write-Host "[SETUP] Sanal disk olusturuluyor: $DISK_PATH ($DISK_SIZE)..." -ForegroundColor Cyan
    & $QEMU_IMG create -f qcow2 $DISK_PATH $DISK_SIZE
    Write-Host "[OK] Sanal disk olusturuldu!" -ForegroundColor Green
}

# 4. WHPX (Windows Hypervisor) kontrolu
try {
    $whpx = Get-WindowsOptionalFeature -FeatureName HypervisorPlatform -Online
    if ($whpx.State -eq "Enabled") {
        Write-Host "[OK] WHPX (Windows Hypervisor Platform) aktif — hizli VM" -ForegroundColor Green
    } else {
        Write-Host "[INFO] WHPX pasif — VM yavas olacak (TCG modu)" -ForegroundColor Yellow
        Write-Host "  Hizlandirmak icin: Enable-WindowsOptionalFeature -Online -FeatureName HypervisorPlatform" -ForegroundColor Yellow
    }
} catch {
    Write-Host "[INFO] WHPX durumu kontrol edilemedi" -ForegroundColor Yellow
}

# 5. Ozet
Write-Host "`n=== Hazir! ===" -ForegroundColor Green
Write-Host "  ISO boot:   tools\qemu-test.bat" -ForegroundColor White
Write-Host "  BIOS boot:  tools\qemu-test-bios.bat" -ForegroundColor White
Write-Host "  Disk boot:  tools\qemu-test-reboot.bat" -ForegroundColor White
Write-Host ""
