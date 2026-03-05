# G-Code Macro Improvements Design

## Goal

Klipper G-Code referansini kullanarak KlipperOS-AI makro ekosistemini 3 alanda gelistirmek:
otomatik kalibrasyon sekans, AI-tetikli bed mesh ve akilli PRINT_START/END makrolari.

## Architecture

Moduler yaklasim — her ozellik kendi `.cfg` dosyasinda (mevcut pattern: kos_plr.cfg,
kos_rewind.cfg, kos_flowguard.cfg). AI entegrasyonu Python tarafinda kalir,
makrolar standalone da calisir.

---

## Feature 1: KOS_AUTO_CALIBRATE — Otomatik Kalibrasyon Sekansi

### Dosya: `config/klipper/kos_auto_calibrate.cfg`

### Problem

Yeni yazici kurulumunda kullanici 4 ayri kalibrasyon komutunu sirasiyla calistirmali,
her SAVE_CONFIG firmware restart tetikler. Manuel surec 30+ dakika, hata yapilmaya acik.

### Cozum: State Machine + delayed_gcode

`save_variables` ile mevcut adimi kaydeder, her restart sonrasi `delayed_gcode`
kaldigi yerden devam eder.

### Sekans

```
Adim 0: Kullanici KOS_AUTO_CALIBRATE cagirir
  -> step=1 kaydet -> PID extruder -> SAVE_CONFIG (restart)

Adim 1: delayed_gcode step=1 algilar
  -> step=2 kaydet -> PID bed -> SAVE_CONFIG (restart)

Adim 2: delayed_gcode step=2 algilar
  -> Akselerometre var mi? Evet -> step=3, SHAPER_CALIBRATE -> SAVE_CONFIG
  -> Yok -> step=4'e atla

Adim 3: delayed_gcode step=3 -> step=4

Adim 4: G28 -> BED_MESH_CALIBRATE -> SAVE_CONFIG (son restart)
  -> step=0 kaydet -> "Kalibrasyon tamamlandi!" bildirimi
```

### Parametreler

| Parametre | Default | Aciklama |
|-----------|---------|----------|
| EXTRUDER_TEMP | 210 | PID hedef extruder sicakligi |
| BED_TEMP | 60 | PID hedef yatak sicakligi |
| SKIP_PID | 0 | PID zaten yapildiysa atla |
| SKIP_SHAPER | 0 | Input shaper atla |

### Kapsam Disi (v3.0)

- Pressure Advance: Otomatize edilemez (test baski gerektirir)
- PROBE_CALIBRATE: Interaktif (kullanici TESTZ ile ayarlar)

---

## Feature 2: AI-Tetikli Otomatik Bed Mesh

### Dosyalar: `ai-monitor/print_monitor.py` (degisiklik)

### Problem

Drift detector "recalibrate" veya "worsening" dediginde kullaniciya sadece bildirim
gonderiliyor. Kullanici bunu gormezden gelebilir, baski kalitesi duser.

### Cozum

`AUTO_RECALIBRATE` env var ile opt-in otomatik kalibrasyon.

### Mantik Akisi

```
Baski basliyor -> _bed_level_pre_print_check()
  -> drift "recalibrate" seviyesinde mi?
    -> AUTO_RECALIBRATE=1 mi?
      -> Evet: Baskiyi duraklat -> KOS_BED_LEVEL_CALIBRATE cagir -> Devam et
      -> Hayir: Sadece bildirim (mevcut davranis)

Baski bitti -> _bed_level_post_print()
  -> trend "worsening" mi?
    -> Yazici bosta mi?
      -> AUTO_RECALIBRATE=1 -> Otomatik kalibrasyon tetikle
      -> Degilse: Sadece bildirim (mevcut davranis)
```

### Guvenlik Kurallari

- Sadece yazici **idle** iken tetiklenir
- Pre-print: baskiyi duraklatir, kalibre eder, devam ettirir
- Post-print: baskidan sonra, kuyrukta baska baski yoksa
- Gunde max **1 kez** otomatik kalibrasyon (spam onleme)
- Her tetiklemede Moonraker notification gonderir

### Yeni Env Var

- `AUTO_RECALIBRATE` (default: 0 — kapali, opt-in)

### Makro Degisikligi

Yeni makro yok — mevcut `KOS_BED_LEVEL_CALIBRATE` Moonraker API uzerinden cagirilir.

---

## Feature 3: Akilli PRINT_START / PRINT_END

### Dosya: `config/klipper/kos_smart_print.cfg`

### Problem

Kullanicilar slicer'da uzun start/end G-code bloklari yazmak zorunda.
Mesh profil secimi, yatak isitma sirasi, purge line hepsi manuel.

### Cozum: Parametrik PRINT_START / PRINT_END

Slicer'dan tek satirla cagrilir, tum hazirligi makro yapar.

### PRINT_START Akisi

```
Slicer'dan cagri:
  PRINT_START EXTRUDER_TEMP=210 BED_TEMP=60 FILAMENT=pla SURFACE=pei

1. Yatak isitma baslat (M190) + termal soak (SOAK_TIME ms)
2. G28 — Home all
3. Mesh profil yukle (FILAMENT + SURFACE combo ile KOS_MESH_PROFILE_LOAD)
   -> Profil yoksa: KOS_ADAPTIVE_MESH calistir (probe varsa)
   -> Probe yoksa: KOS_BED_LEVEL_CHECK ile mevcut mesh kontrol
4. KOS_BED_LEVEL_CHECK — yas kontrolu
5. Extruder isit (M109) — homing sonrasi, ooze onlenir
6. Purge line ciz (on kenarda PURGE_LENGTH mm hat)
7. RESPOND ile "Baski hazir" bildirimi
```

### PRINT_END Akisi

```
1. Retract filament (G1 E-2 F1800)
2. Z hop (G91, G1 Z10)
3. Parca sunumu (G90, G1 X0 Y{max_y} — yatak one)
4. Isiticilar kapat (TURN_OFF_HEATERS)
5. KOS_PLR_CLEAR — guc kesintisi durumunu temizle
6. Stepperlari devre disi birak (M84)
7. RESPOND ile "Baski tamamlandi" bildirimi
```

### Parametreler (PRINT_START)

| Parametre | Default | Aciklama |
|-----------|---------|----------|
| EXTRUDER_TEMP | 210 | Extruder sicakligi |
| BED_TEMP | 60 | Yatak sicakligi |
| FILAMENT | pla | Filament tipi (mesh profil secimi) |
| SURFACE | pei | Yatak yuzeyi (mesh profil secimi) |
| SOAK_TIME | 60000 | Termal soak ms (0=atla) |
| PURGE_LENGTH | 60 | Purge hatti uzunlugu mm |
| ADAPTIVE_MESH | 0 | 1=her zaman adaptif mesh calistir |

### Slicer Entegrasyonu

```gcode
; Start G-code (Cura/PrusaSlicer/OrcaSlicer):
PRINT_START EXTRUDER_TEMP={material_print_temperature_layer_0} BED_TEMP={material_bed_temperature_layer_0} FILAMENT={material_type}

; End G-code:
PRINT_END
```

### Mevcut Makrolarla Iliski

- PAUSE/RESUME/CANCEL_PRINT generic.cfg'de kalir — dokunulmaz
- PRINT_START/PRINT_END yeni kos_smart_print.cfg'de tanimlanir
- generic.cfg'ye `[include kos_smart_print.cfg]` eklenir

---

## Installer Entegrasyonu

`packages/installer/steps/bed_level.py` generate_config()'a ekleme:
- Kullanicinin yazici modeline gore kos_auto_calibrate.cfg ve kos_smart_print.cfg
  installer tarafindan hedef diske kopyalanir
- generic.cfg template'ine include satirlari eklenir

## Test Stratejisi

- Jinja2 makro testleri: Klipper config parser ile syntax dogrulama
- AI monitor testleri: pytest ile _bed_level_pre_print_check auto-recalibrate dallanmasi
- Entegrasyon: Manuel test (gercek yazici veya Klipper simülatörü)
