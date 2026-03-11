# KlipperOS-AI — i7 Deployment Checklist

## Gereksinimler
- Ubuntu 24.04 Server (i7, 8GB+ RAM)
- Ethernet baglanti (SSH erisilebilir)
- Windows PC'de model dosyalari hazir

## Model Dosyalari (Windows)
```
C:\Users\sevdi\Downloads\klipperos-ai-3b-gguf\
├── config.json                          (1.8 KB)
├── tokenizer.json                       (11 MB)
├── tokenizer_config.json                (3 KB)
├── chat_template.jinja                  (2.5 KB)
├── model.safetensors.index.json         (35 KB)
├── model-00001-of-00002.safetensors     (3.7 GB)
└── model-00002-of-00002.safetensors     (2.1 GB)
                                    Toplam: ~5.8 GB
```

## Adimlar

### 1. i7'ye Ubuntu 24.04 Server kur
- KlipperOS netinstall ISO veya temiz Ubuntu Server
- SSH erisimini aktif et

### 2. Dosyalari transfer et (USB veya SCP)

**USB (onerilir, ~2 dk):**
```bash
# Windows'ta USB'ye kopyala, i7'de:
sudo mkdir -p /opt/klipperos-ai/models/klipperos-ai-3b
sudo mount /dev/sdX1 /mnt/usb
sudo cp -r /mnt/usb/klipperos-ai-3b-gguf/* /opt/klipperos-ai/models/klipperos-ai-3b/
sudo umount /mnt/usb
```

**SCP (LAN uzerinden, ~10-15 dk):**
```powershell
# Windows PowerShell'den:
.\scripts\prepare-i7-transfer.ps1 -TargetIP "192.168.1.XXX"
```

**Manuel SCP:**
```bash
# Proje dosyalari
scp -r C:\linux_ai\KlipperOS-AI\ai-chat root@I7_IP:/opt/klipperos-ai/ai-chat
scp -r C:\linux_ai\KlipperOS-AI\scripts root@I7_IP:/opt/klipperos-ai/scripts
scp -r C:\linux_ai\KlipperOS-AI\config root@I7_IP:/opt/klipperos-ai/config

# Model dosyalari
scp -r C:\Users\sevdi\Downloads\klipperos-ai-3b-gguf\* root@I7_IP:/opt/klipperos-ai/models/klipperos-ai-3b/
```

### 3. Deploy scriptini calistir
```bash
ssh root@I7_IP
sudo bash /opt/klipperos-ai/scripts/deploy-i7.sh
```

Script otomatik olarak:
- Ollama kurar
- Model import eder (safetensors -> Ollama)
- AI Chat servisini kurar
- nginx proxy yapilandirir
- Widget'i Mainsail'e enjekte eder

### 4. Dogrulama
```bash
# Model listesi
ollama list

# Quick status (anlik)
curl http://localhost:8085/api/quick-status

# AI Chat test
curl -X POST http://localhost:8085/api/chat \
  -H "Content-Type: application/json" \
  -d '{"messages":[{"role":"user","content":"merhaba"}]}'

# Servisler
systemctl status ollama klipperos-ai-chat klipper moonraker nginx
```

### 5. Tarayicidan test
- Mainsail: `http://I7_IP/`
- AI Chat: `http://I7_IP/ai-chat/`
- Widget: Mainsail sag altta AI butonu

## Beklenen Performans (i7 vs Atom)
| Metrik | Atom N455 (smollm2:135m) | i7 (klipperos-ai 3B) |
|--------|--------------------------|----------------------|
| Model yukleme | 4s | ~10s |
| Prompt isleme | 2.4s/token | ~0.05s/token |
| Token uretme | 2.7s/token | ~0.1s/token |
| "Merhaba" cevabi | ~90s | ~3-5s |
| Cevap kalitesi | Cok temel | Fine-tuned, uzman |

## Sorun Giderme

**Model import basarisiz:**
```bash
# Ollama versiyonu kontrol (0.5+ gerekli safetensors icin)
ollama --version

# Eski Ollama icin GGUF donusumu gerekir:
pip install transformers torch
git clone https://github.com/ggerganov/llama.cpp
cd llama.cpp
python convert_hf_to_gguf.py /opt/klipperos-ai/models/klipperos-ai-3b/ \
  --outfile /opt/klipperos-ai/models/klipperos-ai-3b/klipperos-ai-3b.Q4_K_M.gguf \
  --outtype q4_k_m
```

**OOM (bellek yetersiz):**
```bash
# num_ctx dusurun (server.py'de)
# Veya Q4_K_M yerine daha kucuk quantize:
#   Q2_K: ~1.1GB (kalite dusuk)
#   Q4_K_M: ~1.7GB (onerilir)
#   Q8_0: ~3.2GB (yuksek kalite)
```

**Ollama cevap vermiyor:**
```bash
systemctl restart ollama
journalctl -u ollama -f --no-pager -n 50
```
