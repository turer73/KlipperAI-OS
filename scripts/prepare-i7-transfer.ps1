# ============================================================================
# KlipperOS-AI — i7 Transfer Hazirlik Scripti (Windows)
# ============================================================================
# Bu script:
# 1. Model dosyalarini zip'ten cikarir
# 2. Gerekli dosyalari organize eder
# 3. SCP ile i7'ye transfer eder
#
# Kullanim:
#   .\scripts\prepare-i7-transfer.ps1 -TargetIP "192.168.1.XXX"
# ============================================================================

param(
    [string]$TargetIP = "",
    [string]$TargetUser = "root",
    [string]$ModelZip = "$env:USERPROFILE\Downloads\klipperos-ai-3b-model.zip",
    [string]$ModelDir = "$env:USERPROFILE\Downloads\klipperos-ai-3b-gguf",
    [string]$ProjectDir = "C:\linux_ai\KlipperOS-AI"
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "╔═══════════════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   KlipperOS-AI — i7 Transfer Hazirlik            ║" -ForegroundColor Cyan
Write-Host "╚═══════════════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# ---- 1. Model dosyalarini kontrol et ----
Write-Host "[1/4] Model dosyalari kontrol ediliyor..." -ForegroundColor Green

$modelReady = $false

# Oncelik: acilmis dizin (gdown ile indirilen)
if (Test-Path "$ModelDir\config.json") {
    $stFiles = Get-ChildItem "$ModelDir\*.safetensors" -ErrorAction SilentlyContinue
    if ($stFiles.Count -gt 0) {
        $totalGB = [math]::Round(($stFiles | Measure-Object -Property Length -Sum).Sum / 1GB, 2)
        Write-Host "  Model dizini hazir: $ModelDir" -ForegroundColor Green
        Write-Host "  Safetensors: $($stFiles.Count) dosya ($totalGB GB)" -ForegroundColor Green
        $modelReady = $true
    }
}

# Alternatif: zip dosyasindan cikar
if (-not $modelReady -and (Test-Path $ModelZip)) {
    Write-Host "  Zip dosyasindan cikariliyor: $ModelZip" -ForegroundColor Yellow
    $extractDir = "$env:USERPROFILE\Downloads\klipperos-ai-3b-extracted"
    if (-not (Test-Path $extractDir)) {
        New-Item -ItemType Directory -Path $extractDir -Force | Out-Null
    }
    Expand-Archive -Path $ModelZip -DestinationPath $extractDir -Force
    $ModelDir = $extractDir
    Write-Host "  Cikarildi: $extractDir" -ForegroundColor Green
    $modelReady = $true
}

if (-not $modelReady) {
    Write-Host "  HATA: Model dosyalari bulunamadi!" -ForegroundColor Red
    Write-Host "  Beklenen: $ModelDir veya $ModelZip" -ForegroundColor Red
    exit 1
}

# Gerekli dosyalarin kontrolu
$requiredFiles = @("config.json", "tokenizer.json", "tokenizer_config.json")
foreach ($f in $requiredFiles) {
    if (-not (Test-Path "$ModelDir\$f")) {
        Write-Host "  UYARI: Eksik dosya: $f" -ForegroundColor Yellow
    }
}

# ---- 2. Gereksiz dosyalari temizle ----
Write-Host ""
Write-Host "[2/4] Gereksiz dosyalar temizleniyor..." -ForegroundColor Green

# .cache dizinini sil (gdown metadata, gerekli degil)
if (Test-Path "$ModelDir\.cache") {
    Remove-Item "$ModelDir\.cache" -Recurse -Force
    Write-Host "  .cache dizini silindi" -ForegroundColor Yellow
}

# .part dosyalarini sil (eksik indirmeler)
Get-ChildItem "$ModelDir\*.part" -ErrorAction SilentlyContinue | ForEach-Object {
    Remove-Item $_.FullName -Force
    Write-Host "  Silindi: $($_.Name)" -ForegroundColor Yellow
}

# ---- 3. Transfer boyutunu goster ----
Write-Host ""
Write-Host "[3/4] Transfer ozeti:" -ForegroundColor Green

$allFiles = Get-ChildItem $ModelDir -Recurse -File
$totalSize = ($allFiles | Measure-Object -Property Length -Sum).Sum
$totalGB = [math]::Round($totalSize / 1GB, 2)

Write-Host "  Model dosyalari: $($allFiles.Count) dosya, $totalGB GB" -ForegroundColor Cyan
foreach ($f in $allFiles | Sort-Object Length -Descending) {
    $sizeMB = [math]::Round($f.Length / 1MB, 1)
    Write-Host "    $($f.Name): $sizeMB MB"
}

Write-Host ""
Write-Host "  Proje dosyalari:" -ForegroundColor Cyan
Write-Host "    ai-chat/server.py"
Write-Host "    ai-chat/static/widget.js"
Write-Host "    ai-chat/static/index.html"
Write-Host "    ai-chat/models/Modelfile"
Write-Host "    scripts/deploy-i7.sh"
Write-Host "    config/mainsail/nginx.conf"

# ---- 4. Transfer ----
if ([string]::IsNullOrEmpty($TargetIP)) {
    Write-Host ""
    Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Yellow
    Write-Host "  Transfer icin -TargetIP parametresi gerekli." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Manuel transfer komutlari:" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  # 1. Proje dosyalarini kopyala" -ForegroundColor White
    Write-Host "  scp -r $ProjectDir\ai-chat root@I7_IP:/opt/klipperos-ai/ai-chat" -ForegroundColor White
    Write-Host "  scp -r $ProjectDir\scripts root@I7_IP:/opt/klipperos-ai/scripts" -ForegroundColor White
    Write-Host "  scp -r $ProjectDir\config root@I7_IP:/opt/klipperos-ai/config" -ForegroundColor White
    Write-Host ""
    Write-Host "  # 2. Model dosyalarini kopyala (~6GB, yavas olabilir)" -ForegroundColor White
    Write-Host "  scp -r $ModelDir root@I7_IP:/opt/klipperos-ai/models/klipperos-ai-3b" -ForegroundColor White
    Write-Host ""
    Write-Host "  # 3. Deploy scripti calistir" -ForegroundColor White
    Write-Host "  ssh root@I7_IP 'bash /opt/klipperos-ai/scripts/deploy-i7.sh'" -ForegroundColor White
    Write-Host ""
    Write-Host "  ALTERNATIF: USB ile transfer (daha hizli)" -ForegroundColor Cyan
    Write-Host "  1. USB diske kopyala: model + proje dosyalari" -ForegroundColor White
    Write-Host "  2. i7'de USB mount et: sudo mount /dev/sdX1 /mnt/usb" -ForegroundColor White
    Write-Host "  3. Kopyala: cp -r /mnt/usb/klipperos-ai-3b /opt/klipperos-ai/models/" -ForegroundColor White
    Write-Host "═══════════════════════════════════════════════════" -ForegroundColor Yellow
    exit 0
}

Write-Host ""
Write-Host "[4/4] i7'ye transfer ediliyor ($TargetUser@$TargetIP)..." -ForegroundColor Green

# SSH ile hedef dizin olustur
Write-Host "  Hedef dizinler olusturuluyor..."
ssh "${TargetUser}@${TargetIP}" "mkdir -p /opt/klipperos-ai/{ai-chat/models,ai-chat/static,models/klipperos-ai-3b,scripts,config/mainsail}"

# Proje dosyalari (kucuk, hizli)
Write-Host "  Proje dosyalari kopyalaniyor..."
scp "$ProjectDir\ai-chat\server.py" "${TargetUser}@${TargetIP}:/opt/klipperos-ai/ai-chat/"
scp "$ProjectDir\ai-chat\static\widget.js" "${TargetUser}@${TargetIP}:/opt/klipperos-ai/ai-chat/static/"
scp "$ProjectDir\ai-chat\static\index.html" "${TargetUser}@${TargetIP}:/opt/klipperos-ai/ai-chat/static/"
scp "$ProjectDir\ai-chat\models\Modelfile" "${TargetUser}@${TargetIP}:/opt/klipperos-ai/ai-chat/models/"
scp "$ProjectDir\scripts\deploy-i7.sh" "${TargetUser}@${TargetIP}:/opt/klipperos-ai/scripts/"
scp "$ProjectDir\config\mainsail\nginx.conf" "${TargetUser}@${TargetIP}:/opt/klipperos-ai/config/mainsail/"

# Model dosyalari (buyuk, yavas)
Write-Host "  Model dosyalari kopyalaniyor (~$totalGB GB, biraz sure alacak)..."
scp "$ModelDir\config.json" "${TargetUser}@${TargetIP}:/opt/klipperos-ai/models/klipperos-ai-3b/"
scp "$ModelDir\tokenizer.json" "${TargetUser}@${TargetIP}:/opt/klipperos-ai/models/klipperos-ai-3b/"
scp "$ModelDir\tokenizer_config.json" "${TargetUser}@${TargetIP}:/opt/klipperos-ai/models/klipperos-ai-3b/"
scp "$ModelDir\chat_template.jinja" "${TargetUser}@${TargetIP}:/opt/klipperos-ai/models/klipperos-ai-3b/"

# Safetensors dosyalari (en buyuk)
Get-ChildItem "$ModelDir\*.safetensors" | ForEach-Object {
    $sizeMB = [math]::Round($_.Length / 1MB, 0)
    Write-Host "  Kopyalaniyor: $($_.Name) ($sizeMB MB)..."
    scp $_.FullName "${TargetUser}@${TargetIP}:/opt/klipperos-ai/models/klipperos-ai-3b/"
}

# model.safetensors.index.json (varsa)
if (Test-Path "$ModelDir\model.safetensors.index.json") {
    scp "$ModelDir\model.safetensors.index.json" "${TargetUser}@${TargetIP}:/opt/klipperos-ai/models/klipperos-ai-3b/"
}

Write-Host ""
Write-Host "  Transfer tamamlandi!" -ForegroundColor Green
Write-Host ""
Write-Host "  Simdi i7'de deploy scriptini calistirin:" -ForegroundColor Cyan
Write-Host "    ssh ${TargetUser}@${TargetIP} 'bash /opt/klipperos-ai/scripts/deploy-i7.sh'" -ForegroundColor White
Write-Host ""
