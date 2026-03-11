#!/bin/bash
# ============================================================================
# KlipperOS-AI — i7 Deployment Script
# ============================================================================
# Ubuntu 24.04 Server uzerinde KlipperOS-AI'yi tam kurulum yapar.
# Atom N455 testi gecmis, i7 8GB RAM icin optimize edilmis.
#
# Kullanim:
#   scp -r /opt/klipperos-ai deploy@i7-ip:/tmp/
#   ssh deploy@i7-ip
#   sudo bash /tmp/klipperos-ai/scripts/deploy-i7.sh
#
# Veya Windows'tan:
#   scp -r C:\linux_ai\KlipperOS-AI deploy@i7-ip:/tmp/KlipperOS-AI
#   ssh deploy@i7-ip 'sudo bash /tmp/KlipperOS-AI/scripts/deploy-i7.sh'
# ============================================================================

set -euo pipefail

# Renkler
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Yapilandirma
KLIPPER_USER="klipper"
INSTALL_DIR="/opt/klipperos-ai"
MODEL_DIR="${INSTALL_DIR}/models/klipperos-ai-3b"
AI_CHAT_DIR="${INSTALL_DIR}/ai-chat"
AI_MODEL_NAME="klipperos-ai"

log() { echo -e "${GREEN}[KOS-AI]${NC} $*"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $*"; }
err() { echo -e "${RED}[ERROR]${NC} $*"; }

# ============================================================================
# 1. Sistem kontrolleri
# ============================================================================

check_system() {
    log "Sistem kontrolleri..."

    if [ "$(id -u)" -ne 0 ]; then
        err "Root yetkisi gerekli: sudo bash $0"
        exit 1
    fi

    # Ubuntu 24.04 kontrol
    if [ -f /etc/os-release ]; then
        . /etc/os-release
        log "  OS: ${PRETTY_NAME}"
    fi

    # RAM kontrol
    total_ram_mb=$(free -m | awk '/^Mem:/{print $2}')
    log "  RAM: ${total_ram_mb} MB"
    if [ "$total_ram_mb" -lt 6000 ]; then
        warn "RAM ${total_ram_mb}MB — 3B model icin en az 8GB onerilir"
        warn "Devam ediyor ama OOM riski var..."
    fi

    # CPU kontrol
    cpu_cores=$(nproc)
    cpu_model=$(grep -m1 'model name' /proc/cpuinfo | cut -d: -f2 | xargs)
    log "  CPU: ${cpu_model} (${cpu_cores} core)"
}

# ============================================================================
# 2. Temel paketler
# ============================================================================

install_base_packages() {
    log "Temel paketler kuruluyor..."
    apt-get update -qq
    apt-get install -y -qq \
        curl wget git python3 python3-pip python3-venv \
        nginx jq unzip > /dev/null 2>&1
    log "  Temel paketler tamam."
}

# ============================================================================
# 3. Ollama kurulumu
# ============================================================================

install_ollama() {
    if command -v ollama &>/dev/null; then
        local ver
        ver=$(ollama --version 2>/dev/null | grep -oP '\d+\.\d+\.\d+' || echo "unknown")
        log "Ollama zaten kurulu: v${ver}"
        return 0
    fi

    log "Ollama kuruluyor..."
    curl -fsSL https://ollama.com/install.sh | sh

    # Ollama servisini baslat
    systemctl enable ollama
    systemctl start ollama
    sleep 3

    if command -v ollama &>/dev/null; then
        log "  Ollama kuruldu: $(ollama --version 2>/dev/null)"
    else
        err "Ollama kurulumu basarisiz!"
        exit 1
    fi
}

# ============================================================================
# 4. Model import
# ============================================================================

import_model() {
    log "Model import ediliyor..."

    # Model dosyalari kontrol
    if [ ! -d "${MODEL_DIR}" ]; then
        err "Model dizini bulunamadi: ${MODEL_DIR}"
        err "Model dosyalarini once kopyalayin:"
        err "  scp -r klipperos-ai-3b/ root@i7:${MODEL_DIR}/"
        exit 1
    fi

    # Gerekli dosyalar kontrol
    local missing=0
    for f in config.json tokenizer.json tokenizer_config.json; do
        if [ ! -f "${MODEL_DIR}/${f}" ]; then
            err "  Eksik dosya: ${MODEL_DIR}/${f}"
            missing=1
        fi
    done

    # Safetensors dosyalari kontrol
    local st_count
    st_count=$(find "${MODEL_DIR}" -name "*.safetensors" | wc -l)
    if [ "$st_count" -eq 0 ]; then
        # GGUF kontrol
        local gguf_count
        gguf_count=$(find "${MODEL_DIR}" -name "*.gguf" | wc -l)
        if [ "$gguf_count" -eq 0 ]; then
            err "  Model dosyasi bulunamadi (safetensors veya gguf)"
            missing=1
        else
            log "  GGUF model bulundu (${gguf_count} dosya)"
        fi
    else
        log "  Safetensors model bulundu (${st_count} dosya)"
    fi

    if [ "$missing" -eq 1 ]; then
        exit 1
    fi

    # Ollama bekle
    local retries=0
    while ! curl -sf http://127.0.0.1:11434/api/tags > /dev/null 2>&1; do
        retries=$((retries + 1))
        if [ "$retries" -gt 15 ]; then
            err "Ollama 15 saniye icinde baslamadi"
            exit 1
        fi
        sleep 1
    done

    # Model zaten var mi?
    if ollama list 2>/dev/null | grep -q "${AI_MODEL_NAME}"; then
        log "  Model '${AI_MODEL_NAME}' zaten mevcut."
        ollama list 2>/dev/null | grep "${AI_MODEL_NAME}"
        return 0
    fi

    # Modelfile kopyala
    local modelfile="${AI_CHAT_DIR}/models/Modelfile"
    if [ ! -f "$modelfile" ]; then
        err "Modelfile bulunamadi: $modelfile"
        exit 1
    fi

    # Import: safetensors dizininden
    log "  Ollama model olusturuluyor (bu islem 2-5 dakika surebilir)..."
    cd "${MODEL_DIR}"
    ollama create "${AI_MODEL_NAME}" -f "$modelfile" 2>&1 | tail -5

    # Dogrulama
    if ollama list 2>/dev/null | grep -q "${AI_MODEL_NAME}"; then
        log "  Model basariyla import edildi!"
        ollama list 2>/dev/null | grep "${AI_MODEL_NAME}"
    else
        err "  Model import basarisiz. Manuel deneyin:"
        err "    cd ${MODEL_DIR} && ollama create ${AI_MODEL_NAME} -f ${modelfile}"
        exit 1
    fi
}

# ============================================================================
# 5. AI Chat servisi
# ============================================================================

setup_ai_chat_service() {
    log "AI Chat servisi kuruluyor..."

    # Python bagimliliklari
    pip3 install requests > /dev/null 2>&1

    # RAG bagimliliklari (opsiyonel — yoksa server RAG olmadan calisir)
    log "  RAG bagimliliklari kuruluyor (chromadb + sentence-transformers)..."
    pip3 install chromadb sentence-transformers > /dev/null 2>&1 || {
        warn "  RAG bagimliliklari kurulamadi. RAG devre disi kalacak."
    }

    # Systemd service dosyasi
    cat > /etc/systemd/system/klipperos-ai-chat.service << 'EOF'
[Unit]
Description=KlipperOS-AI Chat Server
After=network.target ollama.service
Wants=ollama.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/klipperos-ai/ai-chat
Environment=AI_MODEL=klipperos-ai
Environment=AI_CHAT_PORT=8085
Environment=OLLAMA_URL=http://127.0.0.1:11434
Environment=MOONRAKER_URL=http://127.0.0.1:7125
ExecStart=/usr/bin/python3 /opt/klipperos-ai/ai-chat/server.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable klipperos-ai-chat
    log "  AI Chat servisi hazir."
}

# ============================================================================
# 5b. RAG Knowledge Base indexleme
# ============================================================================

setup_rag() {
    log "RAG Knowledge Base indexleniyor..."

    local jsonl="${AI_CHAT_DIR}/data/klipper_kb.jsonl"
    local chroma_dir="${AI_CHAT_DIR}/data/chroma_db"
    local index_script="${INSTALL_DIR}/scripts/index_knowledge_base.py"

    # JSONL kontrol
    if [ ! -f "$jsonl" ]; then
        warn "  JSONL bulunamadi: $jsonl"
        warn "  Once training/generate_knowledge_base.py calistirin."
        warn "  RAG devre disi kalacak."
        return 0
    fi

    # Indexleme scripti kontrol
    if [ ! -f "$index_script" ]; then
        warn "  Indexleme scripti bulunamadi: $index_script"
        return 0
    fi

    # chromadb + sentence-transformers kontrolu
    if ! python3 -c "import chromadb; import sentence_transformers" 2>/dev/null; then
        warn "  RAG bagimliliklari eksik, indexleme atlaniyor."
        return 0
    fi

    # Zaten indexlenmis mi?
    if [ -d "$chroma_dir" ] && [ "$(find "$chroma_dir" -name "*.bin" 2>/dev/null | wc -l)" -gt 0 ]; then
        log "  ChromaDB zaten indexlenmis."
        return 0
    fi

    # Indexle
    log "  Embedding model indiriliyor ve indexleme yapiliyor (ilk seferde 2-5dk)..."
    python3 "$index_script" 2>&1 | tail -10

    if [ -d "$chroma_dir" ]; then
        local db_size
        db_size=$(du -sh "$chroma_dir" 2>/dev/null | cut -f1)
        log "  RAG indexleme tamamlandi: ${db_size}"
    else
        warn "  RAG indexleme basarisiz olmus olabilir."
    fi
}

# ============================================================================
# 6. Nginx konfigurasyonu
# ============================================================================

setup_nginx() {
    log "Nginx konfigurasyonu..."

    # Mainsail nginx config'ine /ai-chat/ proxy ekle
    local nginx_conf="/etc/nginx/sites-available/mainsail"
    if [ -f "$nginx_conf" ]; then
        if grep -q "ai-chat" "$nginx_conf"; then
            log "  Nginx /ai-chat/ proxy zaten mevcut."
            return 0
        fi
    fi

    # Mevcut mainsail config yoksa, KlipperOS config'ini kopyala
    if [ -f "${INSTALL_DIR}/config/mainsail/nginx.conf" ]; then
        cp "${INSTALL_DIR}/config/mainsail/nginx.conf" "$nginx_conf"
        ln -sf "$nginx_conf" /etc/nginx/sites-enabled/mainsail
        log "  KlipperOS nginx config kopyalandi."
    else
        warn "  Mainsail nginx config bulunamadi. Manuel yapilandirin."
        warn "  /ai-chat/ proxy eklemeniz gerekli (port 8085)"
    fi

    # Test ve reload
    if nginx -t 2>/dev/null; then
        systemctl reload nginx
        log "  Nginx yeniden yuklendi."
    else
        warn "  Nginx config hatali! 'nginx -t' ile kontrol edin."
    fi
}

# ============================================================================
# 7. Widget enjeksiyonu (Mainsail)
# ============================================================================

inject_widget() {
    log "Mainsail widget kontrol ediliyor..."

    local mainsail_index="/home/${KLIPPER_USER}/mainsail/index.html"
    if [ ! -f "$mainsail_index" ]; then
        warn "  Mainsail index.html bulunamadi: $mainsail_index"
        warn "  Widget'i Mainsail kurulduktan sonra ekleyebilirsiniz."
        return 0
    fi

    if grep -q "widget.js" "$mainsail_index"; then
        log "  Widget zaten enjekte edilmis."
        return 0
    fi

    # Widget script tag ekle (</body> oncesine)
    sed -i 's|</body>|<script src="/ai-chat/static/widget.js"></script>\n</body>|' "$mainsail_index"
    log "  Widget Mainsail'e enjekte edildi."
}

# ============================================================================
# 8. Servisleri baslat
# ============================================================================

start_services() {
    log "Servisler baslatiliyor..."

    systemctl start ollama 2>/dev/null || true
    sleep 2
    systemctl start klipperos-ai-chat 2>/dev/null || true

    log "Servis durumlari:"
    for svc in ollama klipperos-ai-chat klipper moonraker nginx; do
        if systemctl is-active --quiet "$svc" 2>/dev/null; then
            echo -e "  ${GREEN}✓${NC} $svc"
        else
            echo -e "  ${RED}✗${NC} $svc"
        fi
    done
}

# ============================================================================
# 9. Dogrulama
# ============================================================================

verify() {
    log "Dogrulama..."
    local ok=true

    # Ollama model kontrol
    if ollama list 2>/dev/null | grep -q "${AI_MODEL_NAME}"; then
        echo -e "  ${GREEN}✓${NC} Model: ${AI_MODEL_NAME}"
    else
        echo -e "  ${RED}✗${NC} Model bulunamadi"
        ok=false
    fi

    # Quick test — model calistirma (opsiyonel, 3B model yuklemesi ~10s)
    log "  Model test (kisa cevap)..."
    local test_resp
    test_resp=$(curl -sf --max-time 120 http://127.0.0.1:11434/api/generate \
        -d "{\"model\":\"${AI_MODEL_NAME}\",\"prompt\":\"merhaba\",\"stream\":false,\"options\":{\"num_predict\":10,\"num_ctx\":512}}" \
        2>/dev/null | jq -r '.response // empty' 2>/dev/null || true)

    if [ -n "$test_resp" ]; then
        echo -e "  ${GREEN}✓${NC} Model cevap verdi: ${test_resp:0:60}..."
    else
        echo -e "  ${YELLOW}!${NC} Model cevap vermedi (ilk yuklemede normal, tekrar deneyin)"
    fi

    # AI Chat API
    local chat_status
    chat_status=$(curl -sf http://127.0.0.1:8085/api/status 2>/dev/null | jq -r '.ollama' 2>/dev/null || true)
    if [ "$chat_status" = "true" ]; then
        echo -e "  ${GREEN}✓${NC} AI Chat API calisiyor"
    else
        echo -e "  ${YELLOW}!${NC} AI Chat API henuz hazir degil"
    fi

    # Quick status
    local qs
    qs=$(curl -sf http://127.0.0.1:8085/api/quick-status 2>/dev/null | jq -r '.text' 2>/dev/null || true)
    if [ -n "$qs" ]; then
        echo -e "  ${GREEN}✓${NC} Quick-status calisiyor"
    else
        echo -e "  ${YELLOW}!${NC} Quick-status henuz hazir degil (Moonraker gerekli)"
    fi
}

# ============================================================================
# MAIN
# ============================================================================

main() {
    echo ""
    echo -e "${CYAN}╔═══════════════════════════════════════════════════╗${NC}"
    echo -e "${CYAN}║   KlipperOS-AI — i7 Deployment                  ║${NC}"
    echo -e "${CYAN}║   Fine-tuned Qwen2.5-3B + Ollama + AI Chat      ║${NC}"
    echo -e "${CYAN}╚═══════════════════════════════════════════════════╝${NC}"
    echo ""

    check_system
    install_base_packages
    install_ollama
    import_model
    setup_ai_chat_service
    setup_rag
    setup_nginx
    inject_widget
    start_services
    verify

    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
    echo -e "${GREEN}  Kurulum tamamlandi!${NC}"
    echo ""
    echo -e "  AI Chat:    http://$(hostname -I | awk '{print $1}'):8085"
    echo -e "  Mainsail:   http://$(hostname -I | awk '{print $1}')"
    echo -e "  Model:      ${AI_MODEL_NAME} (Qwen2.5-3B fine-tuned)"
    echo ""
    echo -e "  Test:"
    echo -e "    curl http://localhost:8085/api/quick-status"
    echo -e "    curl http://localhost:8085/api/status"
    echo ""
    echo -e "${GREEN}═══════════════════════════════════════════════════${NC}"
}

main "$@"
