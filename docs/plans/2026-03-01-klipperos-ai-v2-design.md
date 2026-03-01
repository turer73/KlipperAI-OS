# KlipperOS-AI v2.0 — Gelişmiş Özellikler Tasarım Belgesi

Tarih: 2026-03-01
Durum: Onaylandı

## Özet

KlipperOS-AI v1.0 temel Klipper dağıtımı üzerine bu doküman 4 yeni ana sistem
ve 8 bileşen iyileştirmesi tanımlar:

1. **Power Loss Recovery (PLR)** — Elektrik kesintisinde kaldığı yerden devam
2. **FlowGuard** — 4 katmanlı akış algılama (Sensör + Heater + TMC + AI)
3. **Smart Rewind** — Koordinat geri sarma, Z offset ile çarpışmasız devam
4. **TMC Akış Kalibrasyonu** — Extruder motor yükünden akış kalitesi ölçümü

Temel makro altyapısı olarak jschuh/klipper-macros kütüphanesi kullanılır.

---

## 1. Power Loss Recovery (PLR) Sistemi

### 1.1 Mimari

- **Mekanizma**: Klipper `[save_variables]` modülü
- **State dosyası**: `~/printer_data/config/variables.cfg`
- **Kayıt sıklığı**: Her katman değişiminde (BEFORE_LAYER_CHANGE hook)
- **Ek buffer**: `/tmp/plr_state.json` (RAM disk, her check cycle)
- **Persist**: Her 10 katmanda `variables.cfg`'ye yaz (SD kart koruma)

### 1.2 Kaydedilen State

```python
plr_active: bool           # PLR verisi var mı
plr_file_path: str         # G-code dosya yolu
plr_file_position: int     # Byte offset (virtual_sdcard)
plr_z_height: float        # Z yüksekliği (mm)
plr_layer: int             # Katman numarası
plr_extruder_temp: int     # Nozzle hedef sıcaklık
plr_bed_temp: int          # Bed hedef sıcaklık
plr_fan_speed: float       # Fan hızı (0-1)
plr_flow_rate: float       # Extrusion çarpanı
plr_speed_factor: float    # Hız çarpanı
plr_x_position: float      # X pozisyonu
plr_y_position: float      # Y pozisyonu
plr_retracted: bool        # Retract durumu
plr_timestamp: int         # Unix timestamp
```

### 1.3 Resume Sırası

1. Boot → `[delayed_gcode _KOS_CHECK_PLR]` çalışır (5 saniye gecikme)
2. `plr_active == True` ise M117 ile bildirim göster
3. Kullanıcı `kos-plr resume` veya Mainsail console'dan `KOS_PLR_RESUME`
4. İşlem:
   - Extruder + Bed ısıt (M104/M140 + M109/M190)
   - `SET_KINEMATIC_POSITION Z={plr_z_height}` (fake home)
   - Z +5mm kaldır
   - `G28 X Y` (sadece X/Y home, Z homing YAPILMAZ)
   - Fan ayarla, flow rate ayarla, speed factor ayarla
   - Filament purge (30mm @ 300mm/min)
   - `SDCARD_PRINT_FILE FILENAME={file_path}`
   - Virtual SD card file_position'a seek
   - `RESUME`

### 1.4 Klipper Makroları

- `kos_plr.cfg`:
  - `BEFORE_LAYER_CHANGE` override → PLR state kaydet
  - `_KOS_SAVE_PLR_STATE` → save_variables çağrısı
  - `_KOS_CHECK_PLR` → delayed_gcode, boot kontrolü
  - `KOS_PLR_RESUME` → resume sırası
  - `KOS_PLR_CLEAR` → PLR verisini temizle
  - `PRINT_END` override → PLR verisini temizle

### 1.5 CLI Aracı

- `tools/kos_plr.py`:
  - `status` → Kayıtlı PLR verisi var mı, detayları göster
  - `resume` → Kayıtlı state'den baskıya devam (makro çağırır)
  - `clear` → PLR verisini temizle
  - `test` → PLR simülasyonu (kaydet/yükle test)

---

## 2. FlowGuard — 4 Katmanlı Akış Algılama

### 2.1 Mimari

```
FlowGuard Engine (print_monitor.py genişletmesi)
│
├── L1: FilamentSensorBridge     [~3s latency]
│   ├── Kaynak: Klipper filament_motion_sensor durumu
│   ├── Moonraker API: /printer/objects/query?filament_motion_sensor
│   ├── Tetikleme: filament_detected == False + extruder aktif
│   └── Confidence: 0.95
│
├── L2: HeaterDutyAnalyzer       [~15s latency]
│   ├── Kaynak: Extruder heater PWM duty cycle
│   ├── Moonraker API: /printer/objects/query?extruder (power alanı)
│   ├── Baseline: İlk 3 dakika otomatik kalibrasyon
│   ├── Sliding window: 30 örneklem ortalaması
│   ├── Tetikleme: duty_cycle düşüşü > %15
│   └── Confidence: 0.70
│
├── L3: ExtruderLoadMonitor      [~5s latency]
│   ├── Kaynak: TMC2209 SG_RESULT (StallGuard)
│   ├── Moonraker API: /printer/objects/query?tmc2209+extruder
│   ├── Normal aralık: SG_RESULT 60-120
│   ├── Clog tespiti: SG_RESULT < 30 (yüksek yük)
│   ├── Filament yok: SG_RESULT > 180 (düşük yük)
│   └── Confidence: 0.85
│
├── L4: AIFlowAnalyzer           [~30s latency]
│   ├── Kaynak: Kamera frame analizi (mevcut spaghetti_detect genişletmesi)
│   ├── Sınıflar: normal, spaghetti, no_extrusion, stringing, completed
│   ├── "no_extrusion": Nozzle hareket ediyor ama malzeme çıkmıyor
│   └── Confidence: değişken (model çıktısı)
│
└── Voting Engine
    ├── 4/4 veya 3/4 → CRITICAL → Anında PAUSE + alarm
    ├── 2/4 → WARNING → 3 cycle bekle, devam ederse PAUSE
    ├── 1/4 → NOTICE → Log + bildirim
    ├── 0/4 → OK → Normal
    └── Ağırlıklı sıralama: Sensör > Motor > Heater > AI
```

### 2.2 Dosyalar

- `ai-monitor/flow_guard.py` — FlowGuard ana sınıfı + Voting Engine
- `ai-monitor/heater_analyzer.py` — HeaterDutyAnalyzer sınıfı
- `ai-monitor/extruder_monitor.py` — ExtruderLoadMonitor (TMC SG_RESULT)
- `ai-monitor/print_monitor.py` — Mevcut daemon genişletmesi
- `ai-monitor/spaghetti_detect.py` — 5 sınıfa genişletme (+ no_extrusion)
- `config/klipper/kos_flowguard.cfg` — Sensör tanımları ve FlowGuard makroları

### 2.3 FlowGuard Makroları

```ini
# kos_flowguard.cfg

[filament_motion_sensor btt_sfs]
detection_length: 10
extruder: extruder
switch_pin: ^PG12         # Kullanıcı düzenler
pause_on_runout: False    # FlowGuard yönetir
event_delay: 3.0
runout_gcode:
    _KOS_FLOWGUARD_SENSOR_TRIGGER

[gcode_macro _KOS_FLOWGUARD_SENSOR_TRIGGER]
gcode:
    {action_respond_info("FlowGuard: Filament sensörü tetiklendi!")}
    # Daemon bu mesajı Moonraker üzerinden izler
```

### 2.4 "Akış Nerede Durdu?" Tespiti

FlowGuard tetiklendiğinde PLR state history'den son `FLOW_OK` katmanı bulunur.
Bu bilgi `kos-rewind status` çıktısında gösterilir:

```
FlowGuard Alert: CRITICAL (3/4 sinyal)
  Sensör: ANOMALY (filament hareketi yok)
  TMC: ANOMALY (SG_RESULT: 195, baseline: 85)
  Heater: OK (duty: 0.68, baseline: 0.72)
  AI: ANOMALY (no_extrusion, confidence: 0.82)

Akışın durduğu tahmini katman: 50 (Z: 10.0mm)
Mevcut katman: 70 (Z: 14.0mm)
```

---

## 3. Smart Rewind — Koordinat Geri Sarma

### 3.1 Konsept

Akış durduğunda (örn: katman 50'de clog), yazıcı boşa çalışmaya devam eder
(katman 70'e kadar). FlowGuard bunu algılayıp durdurur. Smart Rewind,
kullanıcının baskıyı akışın durduğu katmana geri sarıp devam etmesini sağlar.

### 3.2 Z Offset Stratejisi

```
Orijinal:  Katman 49 (Z=9.8mm) ✓, Katman 50 (Z=10.0mm) ✗ (akış durdu)
Rewind:    Katman 50 (Z=11.0mm) ← +1.0mm offset ile boşluğun üstünden

Z Offset önerileri:
  0.2mm — Riskli, çarpışma olabilir
  0.5mm — Güvenli ama yapışma zayıf
  1.0mm — Güvenli + purge ile köprüleme mümkün (varsayılan)
  2.0mm — Çok fazla hava, yapışma çok zayıf
```

### 3.3 CLI Aracı — kos-rewind

```bash
kos-rewind status              # Mevcut durum + FlowGuard bilgisi
kos-rewind goto --layer N      # Katman N'ye geri sar
    --z-offset 1.0             # Z offset (mm, varsayılan: 1.0)
    --purge 30                 # Purge miktarı (mm, varsayılan: 30)
    --dry-run                  # Simülasyon, uygulamadan göster
kos-rewind auto                # FlowGuard'dan son iyi katmana geri sar
    --z-offset 1.0
kos-rewind preview             # Kamera fotoğrafı göster (Moonraker)
```

### 3.4 Rewind Akışı

1. PAUSE durumunda başla (FlowGuard veya manuel)
2. `kos-rewind preview` → Kameradan fotoğraf çek, Moonraker'a kaydet
   - `/tmp/rewind_preview_{timestamp}.jpg`
   - Mainsail/Fluidd'den görüntülenebilir
3. Kullanıcı sorunu düzeltir (filament yükle, nozzle temizle)
4. `kos-rewind goto --layer 50 --z-offset 1.0`
5. G-code parser: Katman 50'nin file_position'ını bul
   - Slicer comment arama: `";LAYER:50"`, `"; layer 50"`, `";BEFORE_LAYER_CHANGE"`
   - PrusaSlicer: `";BEFORE_LAYER_CHANGE"`
   - Cura: `";LAYER:N"`
   - OrcaSlicer: `"; CHANGE_LAYER"`
   - Fallback: Z height eşleştirme (`G1 Z10.0`)
6. Preamble G-code oluştur:
   ```gcode
   M104 S{extruder_temp}       ; Nozzle ısıt
   M140 S{bed_temp}            ; Bed ısıt
   M109 S{extruder_temp}       ; Bekle
   M190 S{bed_temp}            ; Bekle
   G92 E0                      ; Extruder sıfırla
   G1 E{purge_length} F300     ; Purge
   G1 E-2 F1800                ; Retract
   G92 E0                      ; Extruder tekrar sıfırla
   M106 S{fan_speed}           ; Fan
   M220 S{speed_percent}       ; Hız çarpanı
   ```
7. `SET_KINEMATIC_POSITION Z={current_z}` (mevcut Z'yi fake set)
8. Z yüksekliğe kaldır: `G1 Z{target_z + 10} F600`
9. `G28 X Y` (X/Y home, Z homing YAPILMAZ)
10. Dosya kopyala: `{filename}_rewind_L{layer}.gcode`
    - Preamble + Katman N'den itibaren G-code birleştir
    - Tüm Z değerlerine +z_offset ekle
11. `SDCARD_PRINT_FILE FILENAME={rewind_file}`
12. Baskı devam eder

### 3.5 Kısıtlar

- Z homing yapılmaz (baskı bed üzerinde)
- Güç kesildiyse stepper pozisyonu kayıp → PLR state + SET_KINEMATIC_POSITION
- Nozzle temizliği otomatik yapılamaz (kullanıcı müdahalesi)
- İlk "rewind" katmanı bridge gibi davranır (%70-80 yapışma şansı)
- Rewind dosyası orijinali silmez, kopyasını oluşturur

### 3.6 Klipper Makroları

- `kos_rewind.cfg`:
  - `KOS_REWIND_PARK` → Nozzle'ı güvenli pozisyona taşı (jschuh park sistemi ile)
  - `KOS_REWIND_HOME` → Sadece X/Y home
  - `KOS_REWIND_PREPARE` → Isıt + purge + pozisyon ayarla

---

## 4. TMC Akış Kalibrasyonu

### 4.1 Seviye 1: Pasif Baseline Kalibrasyon

- İlk 3 dakika baskıda SG_RESULT ortalaması alınır
- Bu baseline olarak `variables.cfg`'ye kaydedilir
- `{filament_type}_{temp}` anahtarıyla saklanır (örn: `pla_210`)
- Baskı boyunca baseline'dan sapmalar FlowGuard'a sinyal gönderir

### 4.2 Seviye 2: Extrusion Multiplier Tuning

```bash
kos-calibrate flow-test
# İşlem:
# 1. Tek duvar küp yazdır (4 farklı flow rate bölgesi)
# 2. Her bölgede SG_RESULT ortalaması kaydet
#    Bölge 1: Flow 90% → SG: 120 (düşük yük, az malzeme)
#    Bölge 2: Flow 95% → SG: 100
#    Bölge 3: Flow 100% → SG: 85 (hedef aralık)
#    Bölge 4: Flow 105% → SG: 65 (yüksek yük, fazla malzeme)
# 3. Optimal flow rate önerisi: "Flow %98 önerilir"
```

### 4.3 Dosyalar

- `tools/kos_calibrate.py`:
  - `flow-test` → Kalibrasyon testi başlat
  - `flow-status` → Mevcut baseline ve kalibrasyon verilerini göster
  - `flow-reset` → Kalibrasyon verilerini sıfırla
- `ai-monitor/extruder_monitor.py` → ExtruderLoadMonitor sınıfı

### 4.4 Kısıtlar

- TMC2209/2226/5160 gerekli (TMC2208 StallGuard desteklemez)
- SG_RESULT hız bağımlı — sadece sabit hız bölgelerinde ölçüm
- Retraction sırasında okuma durdurulur
- İvmelenme/yavaşlama bölgelerinde sahte yük oluşabilir

---

## 5. jschuh/klipper-macros Entegrasyonu

### 5.1 Kurulum

```bash
git clone https://github.com/jschuh/klipper-macros.git \
    ~/printer_data/config/klipper-macros
```

### 5.2 Kullanılan Özellikler

| Makro Dosyası | Kullanım |
|---------------|----------|
| `start_end.cfg` | Phased PRINT_START/PRINT_END (5 faz) |
| `pause_resume_cancel.cfg` | PAUSE/RESUME + park |
| `layers.cfg` | Layer triggers (PLR hook noktası) |
| `bed_mesh_fast.cfg` | Baskı alanı bazlı bed mesh |
| `bed_surface.cfg` | Çoklu build plate Z offset |
| `park.cfg` | Nozzle park pozisyonu |
| `filament.cfg` | Filament yükleme/çıkarma |
| `state.cfg` | Printer state tracking |
| `globals.cfg` | Merkezi yapılandırma |

### 5.3 KOS Genişletme Noktaları

- `BEFORE_LAYER_CHANGE` → `rename_existing` ile PLR state hook eklenir
- `PRINT_START` → FlowGuard aktivasyonu `_PRINT_START_PHASE_EXTRUDER`'dan sonra
- `PRINT_END` → PLR state temizleme + FlowGuard deaktivasyon
- `PAUSE` → FlowGuard bilgisi console'a yazdırılır

### 5.4 Moonraker Update Manager

```ini
[update_manager klipper-macros]
type: git_repo
origin: https://github.com/jschuh/klipper-macros.git
path: ~/printer_data/config/klipper-macros
primary_branch: main
is_system_service: False
```

---

## 6. Bileşen İyileştirmeleri

### 6.1 Moonraker Yapılandırma

- `[history]` eklenir — baskı geçmişi takibi
- `[job_queue]` eklenir — baskı kuyruğu
- `temperature_store_size: 2400` — 40 dakika sıcaklık geçmişi
- `gcode_store_size: 2000` — genişletilmiş G-code store

### 6.2 Crowsnest

- Camera-streamer V4 backend desteği (RPi 3/4 için)
- Çözünürlük profilleri:
  - SD: 640x480@15fps (düşük güç cihazlar)
  - HD: 1280x720@15fps (standart)
  - FHD: 1920x1080@10fps (yüksek kalite AI analizi)
- Ustreamer fallback (Pi 5, non-Pi SBC'ler)

### 6.3 KlipperScreen

- Power control: Moonraker `[power]` cihaz entegrasyonu
- LED kontrol butonları: `POWER_ON_LED` / `POWER_OFF_LED` makroları
- Custom menü: FlowGuard durumu, PLR resume butonu

### 6.4 Klipper Config Şablonları

Tüm printer config'lere eklenir:
- `[exclude_object]` — Tek nesne iptal (PrusaSlicer 2.7+ native)
- `[firmware_retraction]` — Slicer bağımsız retraction
- `[input_shaper]` — Placeholder + kalibrasyon makrosu
- `[respond]` — Console mesajları (jschuh macros gereksinimi)
- `[virtual_sdcard]` — G-code dizini
- Auto-PID tuning makrosu:
  ```
  KOS_PID_CALIBRATE → PID_CALIBRATE HEATER=extruder TARGET=210
                    → PID_CALIBRATE HEATER=heater_bed TARGET=60
                    → SAVE_CONFIG
  ```

### 6.5 AI Monitor Genişletme

- 5 sınıf: `normal`, `spaghetti`, `no_extrusion`, `stringing`, `completed`
- `no_extrusion` sınıfı: Nozzle hareket ediyor, malzeme çıkmıyor
- FlowGuard L4 entegrasyonu
- Çerçeve yakalama çözünürlük profilleri (SD/HD/FHD Crowsnest ile uyumlu)

### 6.6 MCU Detect Genişletme

- CANbus arayüz tarama (`ip -details link show`)
- Genişletilmiş kart veritabanı: JSON formatında
  ```json
  {
    "boards": [
      {"name": "Creality V4.2.2", "vid": "1a86", "pid": "7523", "mcu": "STM32F103"},
      {"name": "BTT SKR 3", "vid": "1d50", "pid": "614e", "mcu": "STM32H743"},
      {"name": "BTT Manta M8P", "vid": "1d50", "pid": "614e", "mcu": "STM32G0B1"},
      ...
    ]
  }
  ```
- MKS Robin Nano, BTT SKR 3, BTT Manta M4P/M5P/M8P, Fysetc Spider eklenir

---

## 7. Dosya Yapısı (Yeni/Değişen)

```
KlipperOS-AI/
├── ai-monitor/
│   ├── flow_guard.py          ★ YENİ — FlowGuard ana sınıf + voting
│   ├── heater_analyzer.py     ★ YENİ — Heater duty cycle analizi
│   ├── extruder_monitor.py    ★ YENİ — TMC SG_RESULT izleme
│   ├── spaghetti_detect.py    ✏ DEĞİŞİK — 5 sınıfa genişletme
│   ├── print_monitor.py       ✏ DEĞİŞİK — FlowGuard entegrasyonu
│   └── frame_capture.py       (mevcut)
│
├── config/
│   ├── klipper/
│   │   ├── kos_plr.cfg        ★ YENİ — PLR makroları
│   │   ├── kos_flowguard.cfg  ★ YENİ — FlowGuard sensör makroları
│   │   ├── kos_rewind.cfg     ★ YENİ — Rewind yardımcı makroları
│   │   ├── generic.cfg        ✏ DEĞİŞİK — exclude_object, firmware_retraction
│   │   ├── ender3.cfg         ✏ DEĞİŞİK — aynı iyileştirmeler
│   │   ├── ender3v2.cfg       ✏ DEĞİŞİK — aynı iyileştirmeler
│   │   └── voron.cfg          ✏ DEĞİŞİK — aynı iyileştirmeler
│   ├── moonraker/
│   │   └── moonraker.conf     ✏ DEĞİŞİK — history, job_queue, update_manager
│   ├── crowsnest/
│   │   └── crowsnest.conf     ✏ DEĞİŞİK — camera-streamer, çözünürlük profilleri
│   └── klipperscreen/
│       └── KlipperScreen.conf ✏ DEĞİŞİK — power, LED, FlowGuard menü
│
├── tools/
│   ├── kos_plr.py             ★ YENİ — PLR CLI aracı
│   ├── kos_rewind.py          ★ YENİ — Rewind CLI aracı
│   ├── kos_calibrate.py       ★ YENİ — TMC kalibrasyon CLI
│   ├── kos_profile.py         (mevcut)
│   ├── kos_update.py          ✏ DEĞİŞİK — yeni repo'lar eklenir
│   ├── kos_backup.py          (mevcut)
│   └── kos_mcu.py             ✏ DEĞİŞİK — CANbus, genişletilmiş kart DB
│
├── data/
│   └── boards.json            ★ YENİ — MCU kart veritabanı
│
├── scripts/
│   ├── install-light.sh       ✏ DEĞİŞİK — jschuh macros kurulumu eklenir
│   ├── install-standard.sh    ✏ DEĞİŞİK — FlowGuard daemon servisi
│   ├── install-full.sh        (minimal değişiklik)
│   └── install-klipper-os.sh  (minimal değişiklik)
│
├── pyproject.toml             ✏ DEĞİŞİK — yeni CLI entry point'ler
└── README.md                  ✏ DEĞİŞİK — yeni özellikler dokümantasyonu
```

---

## 8. Profil Uyumu

| Özellik | LIGHT | STANDARD | FULL |
|---------|-------|----------|------|
| PLR State Saving | ✓ | ✓ | ✓ |
| PLR Resume | ✓ | ✓ | ✓ |
| jschuh/klipper-macros | ✓ | ✓ | ✓ |
| FlowGuard L1 (Sensör) | ✓* | ✓* | ✓* |
| FlowGuard L2 (Heater) | ✗ | ✓ | ✓ |
| FlowGuard L3 (TMC) | ✗ | ✓ | ✓ |
| FlowGuard L4 (AI) | ✗ | ✓ | ✓ |
| Smart Rewind | ✓ | ✓ | ✓ |
| TMC Kalibrasyon | ✗ | ✓ | ✓ |
| Kamera Önizleme | ✗ | ✓ | ✓ |

*L1 sensör: Donanım varsa tüm profillerde aktif

---

## 9. Riskler ve Azaltma

| Risk | Etki | Azaltma |
|------|------|---------|
| Heater duty cycle gürültülü | Yanlış pozitif | %15 eşik + 30 örneklem window |
| TMC SG_RESULT hız bağımlı | Yanlış kalibrasyon | Sabit hız bölgelerinde ölçüm |
| Rewind sonrası katman yapışması | Baskı kalitesi | Bridge benzeri ilk katman + purge |
| PLR Z pozisyon kaybı | Çarpışma | SET_KINEMATIC_POSITION + +5mm güvenlik |
| SD kart yıpranması (PLR yazma) | Donanım ömrü | RAM buffer + 10 katmanda bir persist |
| jschuh macros güncellemesi | Uyumsuzluk | rename_existing ile hook, kaynak değiştirilmez |
