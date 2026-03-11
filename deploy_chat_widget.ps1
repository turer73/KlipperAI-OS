# =============================================================================
# KlipperOS-AI — Chat Widget Deploy Script (PowerShell)
# =============================================================================
# Mainsail icine AI chat widget entegre eder.
#
# Kullanim:
#   .\deploy_chat_widget.ps1
#
# Parola soruldugunda: tur04520
# =============================================================================

$SERVER = "klipperos@192.168.1.118"
$LOCAL_BASE = "C:\linux_ai\KlipperOS-AI"

Write-Host "============================================" -ForegroundColor Cyan
Write-Host " KlipperOS-AI Widget Deploy" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Widget JS dosyasini yükle
Write-Host "[1/5] widget.js yukleniyor..." -ForegroundColor Yellow
scp "$LOCAL_BASE\ai-chat\static\widget.js" "${SERVER}:/home/klipperos/ai-chat/static/widget.js"

# 2. Guncel server.py yukle
Write-Host "[2/5] server.py yukleniyor..." -ForegroundColor Yellow
scp "$LOCAL_BASE\ai-chat\server.py" "${SERVER}:/home/klipperos/ai-chat/server.py"

# 3. Guncel index.html yukle
Write-Host "[3/5] index.html yukleniyor..." -ForegroundColor Yellow
scp "$LOCAL_BASE\ai-chat\static\index.html" "${SERVER}:/home/klipperos/ai-chat/static/index.html"

# 4. Nginx config yukle ve aktif et
Write-Host "[4/5] nginx.conf yukleniyor..." -ForegroundColor Yellow
scp "$LOCAL_BASE\config\mainsail\nginx.conf" "${SERVER}:/tmp/mainsail-nginx.conf"

# 5. Sunucuda nginx config'i kopyala ve servisleri yeniden baslat
Write-Host "[5/5] Sunucuda servisleri yeniden baslatiliyor..." -ForegroundColor Yellow
ssh $SERVER "sudo cp /tmp/mainsail-nginx.conf /etc/nginx/sites-available/mainsail && sudo nginx -t && sudo systemctl reload nginx && sudo systemctl restart klipperos-ai-chat && echo 'DEPLOY BASARILI!'"

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host " Deploy tamamlandi!" -ForegroundColor Green
Write-Host " Tarayicida: http://192.168.1.118" -ForegroundColor Green
Write-Host " Sag alt kosede 🤖 butonunu goreceksiniz" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
