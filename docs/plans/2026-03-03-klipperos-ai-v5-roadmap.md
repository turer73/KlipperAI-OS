# KlipperOS-AI v5.0 Yol Haritasi — Tasarim Dokumani

**Tarih**: 2026-03-03
**Mevcut Versiyon**: v2.0.0
**Hedef**: v3.0 → v4.0 → v5.0 kademeli ilerleme
**Yaklasim**: Parallel Tracks — her versiyonda AI + API + UI paralel ilerler
**Vizyon**: Otonom yazici → Farm yonetimi → Acik ekosistem
**Platform**: ARM SBC + x86 mini PC + Cloud hybrid
**Web Stack**: Next.js (React) + FastAPI backend
**Zaman**: Ozellik bazli release — deadline yok, kalite oncelikli

---

## Mevcut Durum (v2.0.0)

| Metrik | Deger |
|--------|-------|
| CLI tools | 13 |
| AI monitor modulleri | 6 |
| KlipperScreen panelleri | 11 |
| Test dosyalari | 18 |
| Shell scriptleri | 7 |
| Toplam Python satiri | ~12,000 |
| Desteklenen MCU | 100+ |
| ISO builder | Ubuntu Server 24.04 repackaging |
| CI/CD | GitHub Actions |
| AI inference | TFLite (spaghetti) + Ollama (agent) |
| Profil sistemi | LIGHT / STANDARD / FULL |
| Uzak erisim | Tailscale mesh VPN |

---

## v3.0 — Otonom Yazici + API Temeli

### Track 1: Self-Healing AI Motoru

| Ozellik | Aciklama |
|---------|----------|
| ONNX Runtime gecisi | TFLite → ONNX. Daha genis model destegi, x86+ARM uyumu, GPU hizlandirma (iGPU/NPU destekli mini PC'ler icin) |
| Gelismis FlowGuard v2 | Mevcut 4 katmana ek: termal kamera katmani (opsiyonel), akustik analiz katmani (opsiyonel mikrofon), zaman serisi trend analizi (son 30 dakika pattern) |
| Auto-Kalibrasyon | PID tune → Input Shaper → Pressure Advance → Flow rate — hepsini sirayla calistiran orkestrator. Sonuclari otomatik config'e yazar |
| Self-Healing Aksiyonlar | Nozul tikanma → otomatik purge G-code. Yatak leveling kayma → otomatik BED_MESH_CALIBRATE. Termal kacak → guvenli durdurma + bildirim |
| Akilli Bildirim | Moonraker notification + Telegram/Discord webhook + Tailscale push. Ciddiyet: INFO→log, WARNING→push, CRITICAL→durdur+alarm |

### Track 2: FastAPI Backend + REST API

| Ozellik | Aciklama |
|---------|----------|
| FastAPI backend | `/api/v1/` — yazici durumu, sicakliklar, baski ilerlemesi, AI alertleri, servis kontrolu. Moonraker proxy + kendi endpoint'ler |
| WebSocket stream | Gercek zamanli sicaklik, baski ilerlemesi, FlowGuard durumu — dashboard icin SSE/WS |
| JWT auth | Kullanici kimlik dogrulama — local + Tailscale token destegi |
| OpenAPI spec | Otomatik Swagger/ReDoc — 3rd-party entegrasyon kolayligi (v4-v5 plugin sistemi icin temel) |
| SQLite veri katmani | Baski gecmisi, istatistikler, AI alert log, kalibrasyon sonuclari |

### Track 3: Temel Web Dashboard (Next.js)

| Ozellik | Aciklama |
|---------|----------|
| Yazici izleme | Gercek zamanli sicaklik grafikleri, baski ilerlemesi, kamera stream embed |
| AI durumu | FlowGuard status, son alertler, model durumu |
| Sistem sagligi | CPU/RAM/Disk, servis durumlari, Ollama/Tailscale |
| Basit kontrol | Baski duraklat/devam/iptal, sicaklik ayarla, home |
| Responsive | Mobil tarayicida calisir (v5'te PWA'ya donusur) |

### Teknik Altyapi Degisiklikleri (v3.0)

- Python 3.11+ minimum (3.9 destegi sona erer)
- ONNX Runtime yerine TFLite (optional dep)
- FastAPI + uvicorn web backend
- SQLite + SQLAlchemy veri katmani
- Next.js 14+ web frontend (ayri repo veya monorepo `web/`)
- Docker opsiyonel — x86/cloud deployment icin

---

## v4.0 — Yazici Ciftligi + Tam Dashboard

**On kosul**: v3.0'daki FastAPI, WebSocket, SQLite ve Next.js dashboard hazir.

### Track 1: Multi-Printer Orkestrasyon

| Ozellik | Aciklama |
|---------|----------|
| Printer Registry | Her yazici: isim, IP, Moonraker port, profil, durum, yetenekler. SQLite + auto-discovery (Tailscale/mDNS) |
| Is Kuyrugu (Job Queue) | G-code dosyalari kuyruga eklenir → uygun yaziciya atanir. Oncelik: acil/normal/dusuk. Retry: basarisiz is baska yaziciya yonlendirilir |
| Load Balancer | Yazici secimi: nozul boyutu uyumu, filament tipi, tahmini sure, mevcut yuk, guvenilirlik skoru (gecmis basari orani) |
| Toplu Eylemler | Tum yazicilari duraklat/devam, toplu firmware guncelleme, toplu kalibrasyon, toplu profil degisikligi |
| Farm Istatistikleri | Toplam baski saati, basari orani, yazici bazli verimlilik, filament tuketimi, maliyet hesabi, uptime |

### Track 2: Fleet Dashboard (Next.js genisleme)

| Ozellik | Aciklama |
|---------|----------|
| Fleet Overview | Grid/liste gorunum — her yazici: mini thumbnail (kamera), sicaklik, ilerleme %, durum renk kodu |
| Detay drilldown | Yaziciya tikla → v3 single-printer dashboard acilir |
| Job Queue UI | Surukle-birak kuyruk yonetimi, is atamasi, oncelik degistirme |
| Alarm Paneli | Tum yazicilardan gelen FlowGuard/AI alertleri — tek akista, filtrelenebilir |
| Analitik | Grafik: baski saati/gun, filament kullanimi, hata trendleri, yazici karsilastirma |
| Kullanici rolleri | Admin (tam kontrol), Operator (baski baslat/izle), Viewer (sadece izle) |

### Track 3: Cloud Hybrid Mimari

| Ozellik | Aciklama |
|---------|----------|
| Cloud Inference Hub | VPS/bulut uzerinde guclu Ollama instance — tum farm SBC'leri buraya sorgu gonderir. Tailscale uzerinden guvenli |
| Merkezi Veritabani | PostgreSQL (cloud) — tum farm istatistikleri, baski gecmisi, AI model metrikleri. SBC'ler SQLite sync |
| Remote Monitoring | Farm dashboard internet uzerinden erisilebilir (Tailscale Funnel veya reverse proxy) |
| Yedekleme | Printer config'leri otomatik buluta yedeklenir — felaket kurtarma |
| OTA Guncelleme (temel) | Farm controller uzerinden tum node'lara yazilim guncellemesi — v5'te tam OTA olacak |

### Teknik Altyapi Degisiklikleri (v4.0)

- Monorepo yapisi: `packages/api`, `packages/web`, `packages/agent`, `packages/farm-controller`
- PostgreSQL (cloud) + SQLite (edge/SBC) — sync mekanizmasi
- Redis/BullMQ is kuyrugu (veya SQLite-based lightweight alternatif SBC'de)
- gRPC veya MQTT yazicilar arasi haberlesme
- Tailscale ACL farm duzeyinde erisim kontrolu
- Docker Compose cloud bilesenleri icin

---

## v5.0 — Acik Ekosistem

**On kosul**: v3.0 otonom AI + API, v4.0 farm orkestrasyon + fleet dashboard + cloud hybrid hazir.

### Track 1: Plugin Sistemi + Marketplace

| Ozellik | Aciklama |
|---------|----------|
| Plugin SDK | Python paketi: hook'lar (before_print, on_alert, on_layer_change), API endpoint ekleme, dashboard widget ekleme. Standart pyproject.toml ile paketlenme |
| Plugin Registry | Merkezi plugin katalogu (GitHub-hosted veya self-hosted). Versiyonlama, bagimlilik cozumleme, uyumluluk matrisi |
| Marketplace UI | Dashboard'da plugin magazasi — arama, kurulum, guncelleme, degerlendirme |
| Sandbox | Plugin'ler izole calisir — dosya sistemi erisimi kisitli, API erisimi izinle, kaynak limiti |
| Ornek plugin'ler | Telegram bot, Discord bot, OctoPrint import, Timelapse render, maliyet hesaplama, filament stok takibi |

### Track 2: Mobil Uygulama

| Ozellik | Aciklama |
|---------|----------|
| PWA | Next.js dashboard → PWA manifest + service worker. iOS/Android ana ekrana eklenebilir, offline durum cache |
| Push Notification | FlowGuard CRITICAL alert → aninda telefona bildirim (Web Push API veya Firebase FCM) |
| Kamera Stream | Yazici kamerasini mobilde gercek zamanli izle (WebRTC veya HLS) |
| Hizli Aksiyonlar | Widget: duraklatma/devam, sicaklik, farm durumu — tek dokunusla |
| React Native (opsiyonel) | PWA yeterli olmazsa native app — kamera, bildirim, arka plan izleme icin daha iyi |

### Track 3: Topluluk + OTA + AI Model Paylasimi

| Ozellik | Aciklama |
|---------|----------|
| Topluluk Profilleri | Kullanicilar yazici profili paylasir: optimal config, PID degerleri, vb. Oylama + yorum sistemi |
| AI Model Paylasimi | Topluluk egitimli ONNX modelleri: farkli filament turleri, farkli hata tipleri. Model leaderboard |
| OTA Delta Update | Tam ISO yerine sadece degisen dosyalar — bsdiff/xdelta tabanli. Guvenli: imzali paketler (GPG), rollback destegi |
| Telemetri (opsiyonel) | Anonim kullanim istatistikleri — populer ozellikler, yaygin hatalar, model performansi. Opt-in, GDPR uyumlu |
| Dokumantasyon Portali | API referans, plugin gelistirme rehberi, topluluk wiki |

### Teknik Altyapi Degisiklikleri (v5.0)

- Plugin SDK Python paketi: `klipperos-ai-sdk` (PyPI'da yayinlanir)
- PWA: Next.js + next-pwa + service worker
- Push: Web Push API + FCM fallback
- OTA: bsdiff delta + GPG imza + rollback
- CDN: Plugin/model dagitimi icin (Cloudflare R2 veya GitHub Releases)
- Topluluk backend: Supabase veya self-hosted (PostgreSQL + S3)

---

## Versiyon Karsilastirma Tablosu

| Ozellik | v2.0 (simdi) | v3.0 | v4.0 | v5.0 |
|---------|:---:|:---:|:---:|:---:|
| CLI tools | 13 | 15+ | 18+ | 20+ |
| Spaghetti AI | TFLite | ONNX | ONNX+ | ONNX+ |
| FlowGuard | 4 katman | 6 katman | 6 katman | 6+ |
| Auto-kalibrasyon | yok | PID/PA/IS | + flow rate | + topluluk |
| Self-healing | yok | temel | gelismis | tam |
| Web dashboard | yok | temel | fleet | + plugin |
| API | yok | REST+WS | + gRPC/MQTT | + Plugin API |
| Multi-printer | 3 (elle) | 3 (elle) | 10+ (otomatik) | sinirsiz |
| Job queue | yok | yok | temel | gelismis |
| Cloud | Tailscale | + API | + DB sync | + CDN/OTA |
| Mobil | yok | responsive | responsive+ | PWA/native |
| Plugin sistemi | yok | yok | yok | tam |
| Topluluk | yok | yok | yok | profil+model |
| OTA guncelleme | git pull | git pull | temel | delta+GPG |

---

## Bagimlilik Grafigi

```
v2.0 (mevcut)
  │
  ├── v2.x patch'ler (autoinstall fix, lint, vb.)
  │
  v
v3.0 — Otonom Yazici + API Temeli
  │
  ├── Track 1: Self-Healing AI (ONNX, auto-kalibrasyon, gelismis FlowGuard)
  ├── Track 2: FastAPI + REST/WS API + SQLite
  └── Track 3: Temel Next.js dashboard
  │
  v
v4.0 — Yazici Ciftligi + Tam Dashboard
  │
  ├── Track 1: Multi-printer orkestrasyon + job queue (← v3 API'ye bagimli)
  ├── Track 2: Fleet dashboard + analitik (← v3 dashboard'a bagimli)
  └── Track 3: Cloud hybrid + PostgreSQL sync (← v3 SQLite'a bagimli)
  │
  v
v5.0 — Acik Ekosistem
  │
  ├── Track 1: Plugin sistemi + marketplace (← v4 API + dashboard'a bagimli)
  ├── Track 2: Mobil app PWA/native (← v4 fleet dashboard'a bagimli)
  └── Track 3: Topluluk + OTA + model paylasimi (← v4 cloud'a bagimli)
```

---

## Risk Matrisi

| Risk | Olasilik | Etki | Azaltma |
|------|----------|------|---------|
| SBC RAM yetersizligi (FastAPI + Next.js) | Yuksek | Orta | Cloud hybrid: SBC sadece agent, API cloud'da |
| ONNX model boyutu (ARM) | Orta | Orta | Quantization (INT8), model pruning |
| Next.js build suresi (SBC) | Yuksek | Dusuk | Statik export, CI'da build, SBC'ye deploy |
| Multi-printer sync kaybi | Orta | Yuksek | Event sourcing, idempotent islemler, retry |
| Plugin guvenlik acigi | Orta | Yuksek | Sandbox (seccomp/AppArmor), izin sistemi |
| Topluluk benimseme | Orta | Orta | Ornek plugin'ler, dokumantasyon, Discord |
| Breaking API degisiklikleri | Dusuk | Yuksek | Semantic versioning, deprecation policy |

---

## Sonraki Adim

Bu tasarim dokumani onaylandi. Siradaki: v3.0 icin detayli uygulama plani
(writing-plans skill ile hazirlanacak).
