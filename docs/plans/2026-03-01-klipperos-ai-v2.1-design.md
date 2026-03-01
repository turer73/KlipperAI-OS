# KlipperOS-AI v2.1 Design: System Management UI & AI Config Manager

## Goal

KlipperOS-AI'yi tam bir appliance OS'a donusturmek: KlipperScreen uzerinden tum sistem
yonetimi, AI'nin Klipper config dosyalarini otomatik duzenleme yetkisi, ve 2GB RAM'de
optimize calisma icin guncel sikistirma teknikleri.

## Mimari

KlipperScreen native GTK3 panel sistemi ile 11 yeni sistem yonetim paneli. AI Config
Manager modulu Moonraker File API uzerinden config okuma/yazma. zram+zstd ile bellek
sikistirma, cgroup limitleri ve lazy-load ile 2GB RAM optimizasyonu. VTE3 terminal
paneli ile klavye/mouse destekli tam shell erisimi.

## Karar Ozeti

| Karar | Secim | Sebep |
|-------|-------|-------|
| Panel tipi | KlipperScreen native (GTK3) | Hafif, tema uyumlu, dokunmatik optimize |
| AI CFG yetkisi | Tam otomatik | Kalibrasyon sonuclari, threshold ogrenmesi, hata duzeltme |
| API | Moonraker File API | Guvenli, yetkilendirilmis, restart koordinasyonu |
| Sikistirma | zram + zstd | 3:1 oran, RPi4'te dusuk CPU yukü |
| Terminal | VTE3 widget | GTK3 native, lazy-load, ~8MB RAM |
| Giris | Klavye + mouse + dokunmatik | Fiziksel + on-screen klavye destegi |
| RAM hedef | 2GB (STANDARD profil) | ~1156MB kullanim + ~794MB buffer |

---

## Bolum 1: Mimari Genel Bakis

```
+------------------------------------------------------+
|              KlipperScreen (GTK3)                    |
|  +----------+ +----------+ +----------+ +--------+  |
|  | Yazici   | | Sistem   | | AI       | |Terminal|  |
|  | Paneller | | Paneller | | Paneller | | VTE3   |  |
|  +----+-----+ +----+-----+ +----+-----+ +---+----+  |
|       |             |            |            |      |
|  +----v-------------v------------v------------v----+ |
|  |         KOS System API (Python modulu)          | |
|  |  WiFi/nmcli | systemctl | psutil | Moonraker   | |
|  +--------------------------+----------------------+ |
+-----------------------------+------------------------+
                              |
                  +-----------v-----------+
                  |   Moonraker API       |
                  |  /server/files/       | <-- AI Config Manager
                  |  /printer/restart     |     (print_monitor.py)
                  |  /machine/system_info |
                  +-----------------------+
```

### Temel Bilesenler

1. **KOS System API** (`kos_system_api.py`)
   - Tek Python modulu, tum sistem islemlerini soyutlar
   - WiFi: `nmcli` komutu ile SSID tarama, baglanti, sifre
   - Disk/CPU/RAM: `psutil` kutuphanesi
   - Servisler: `systemctl` komutu
   - Moonraker: HTTP istekleri (requests)

2. **Native Paneller** (her biri ayri `.py` dosyasi)
   - KlipperScreen `ScreenPanel` siniflarindan turenir
   - GTK3 widget'lari: Gtk.Box, Gtk.Label, Gtk.Button, Gtk.Switch, vb.
   - Tema uyumlu, dokunmatik optimize

3. **AI Config Manager** (`config_manager.py`)
   - Mevcut `print_monitor.py`'ye eklenen modul
   - Moonraker File API ile config okuma/yazma
   - Otomatik backup + bildirim

4. **VTE3 Terminal** (`kos_terminal.py`)
   - GTK terminal widget, klavye/mouse ile tam shell erisimi
   - Lazy-load: sadece panel acildiginda baslatilir

---

## Bolum 2: KlipperScreen Sistem Panelleri

Ana menuye "Sistem" alt menusu eklenir:

```
Ana Menu
+-- Yazici (mevcut)
+-- Sicakliklar (mevcut)
+-- KlipperOS-AI (mevcut: FlowGuard, PLR, PID)
+-- Sistem (YENI)
|   +-- Ag Ayarlari        -> WiFi SSID secim/baglanti, IP, Ethernet
|   +-- Tailscale VPN      -> Durum, IP, baglanti yonetimi
|   +-- Guncelleme          -> kos_update entegrasyonu
|   +-- Yedekleme           -> kos_backup entegrasyonu
|   +-- MCU Yonetimi        -> kos_mcu entegrasyonu
|   +-- Sistem Bilgisi      -> CPU/RAM/Disk + MCU sicaklik/voltaj + CAN boards
|   +-- AI Ayarlari         -> AI Monitor on/off, interval, threshold
|   +-- Servis Yonetimi     -> start/stop/restart servisleri
|   +-- Log Goruntule       -> klippy/moonraker/crowsnest/AI loglari
|   +-- Terminal            -> VTE3 tam shell
|   +-- Guc                 -> Shutdown, Reboot, Restart Klipper
+-- Ayarlar (mevcut)
```

### Panel Detaylari

| Panel | Dosya | Veri Kaynagi | Giris Yontemi |
|-------|-------|-------------|---------------|
| Ag Ayarlari | `kos_network.py` | `nmcli` | Liste + dokunmatik/fiziksel klavye |
| Tailscale | `kos_tailscale.py` | `tailscale` CLI | Buton |
| Guncelleme | `kos_updates.py` | `kos_update` modul | Buton + progress bar |
| Yedekleme | `kos_backup_panel.py` | `kos_backup` modul | Liste + buton |
| MCU Yonetimi | `kos_mcu_panel.py` | `kos_mcu` modul | Liste + buton |
| Sistem Bilgisi | `kos_sysinfo.py` | `psutil` + Moonraker MCU query | Salt okunur |
| AI Ayarlari | `kos_ai_settings.py` | Moonraker File API | Slider + toggle |
| Servis Yonetimi | `kos_services.py` | `systemctl` | Toggle buton |
| Log Goruntule | `kos_logs.py` | Dosya okuma (tail) | Scroll + filtre |
| Terminal | `kos_terminal.py` | VTE3 widget | Klavye + mouse |
| Guc | `kos_power.py` | `systemctl` | Onay dialog + buton |

### Sistem Bilgisi Paneli (Genisletilmis)

```
Sistem Bilgisi
+-- Host (RPi/PC)
|   +-- CPU sicakligi, yuk, frekans
|   +-- RAM kullanimi (fiziksel + zram swap)
|   +-- Disk kullanimi + I/O
|   +-- Uptime, profil, OS versiyonu
+-- Yazici MCU (STM32/RP2040/ATmega)
|   +-- MCU sicakligi (Klipper mcu.temperature)
|   +-- MCU voltaj (mcu.adc_voltage)
|   +-- Son restart sebebi, firmware versiyonu
|   +-- Task yuku, buffer durumu
+-- Ek MCU'lar (CAN toolhead, EBB36/42)
|   +-- Her biri icin sicaklik/voltaj
|   +-- CAN bus durumu, hata sayaci
+-- Guc Durumu
    +-- PSU voltaj (varsa sensor ile)
    +-- UPS/battery durumu (varsa)
```

Veri kaynagi: Moonraker `/printer/objects/query?mcu&mcu toolhead` endpoint'i.

---

## Bolum 3: AI Config Manager

### Akis

```
1. Tetikleyici Olay (kalibrasyon tamamlandi, threshold ogrendi, hata tespit)
      |
2. Config Okuma (GET /server/files/config/printer.cfg)
      |
3. Config Parse (configparser ile section/key bulma)
      |
4. Yedek Alma (kos_backup ile otomatik pre-edit backup)
      |
5. Config Yazma (POST /server/files/upload ile guncelleme)
      |
6. Moonraker Bildirimi ("PID sonuclari printer.cfg'ye yazildi")
      |
7. Gerekirse Restart (POST /printer/restart veya FIRMWARE_RESTART)
```

### Otomatik Yazilacak Parametreler

| Parametre | Tetikleyici | Config Bolumu |
|-----------|-------------|---------------|
| PID degerleri (Kp/Ki/Kd) | `PID_CALIBRATE` sonucu | `[extruder]`, `[heater_bed]` |
| Pressure advance | PA kalibrasyon testi | `[extruder]` |
| Input shaper (freq/type) | Accelerometer testi | `[input_shaper]` |
| FlowGuard threshold'lar | Ogrenilen normal araliklar | `[kos_flowguard]` custom section |
| TMC StallGuard baseline | `kos-calibrate flow-test` | `kos_calibration.json` |
| Rotation distance duzeltme | Extrusion kalibrasyon | `[extruder]` |

### Guvenlik Mekanizmalari

- Her edit oncesi **otomatik backup** (`kos_backup` modulu ile)
- Moonraker **bildirim** gonderimi (ne degistigini aciklar)
- **Sadece bilinen parametreleri** degistirir (whitelist yaklasimi)
- Config parse hatasi durumunda yazma **iptal**
- Degisiklik loglama (`/var/log/kos-config-changes.log`)

### API Kullanimi

```python
# Config okuma
GET /server/files/config/printer.cfg
-> Raw text content

# Config yazma
POST /server/files/upload
Content-Type: multipart/form-data
root=config&file=printer.cfg&content=...

# Klipper restart
POST /printer/restart

# Firmware restart (MCU degisiklikleri icin)
POST /printer/firmware_restart
```

---

## Bolum 4: Sikistirma & 2GB RAM Optimizasyonu

### Katman 1: Bellek Sikistirma (zram + zstd)

```bash
# /etc/systemd/system/kos-zram.service ile otomatik baslatma
zram boyutu: RAM'in %50'si (~1GB)
Algoritma: zstd (3:1 sikistirma orani)
Sonuc: 2GB fiziksel + ~3GB zram swap = ~5GB efektif bellek

# Kernel parametreleri
vm.swappiness=150         # zram icin yuksek
vm.page-cluster=0         # Kucuk chunk okuma
vm.dirty_expire_centisecs=1500
vm.dirty_writeback_centisecs=500
```

### Katman 2: Servis Bellek Limitleri (systemd cgroups)

```ini
# Her servisin systemd override dosyasina eklenir
# /etc/systemd/system/<service>.d/memory.conf

klipper.service        -> MemoryMax=256M
moonraker.service      -> MemoryMax=200M
KlipperScreen.service  -> MemoryMax=150M
klipperos-ai-monitor   -> MemoryMax=200M
crowsnest.service      -> MemoryMax=100M
nginx.service          -> MemoryMax=50M
```

### Katman 3: Dosya/Log Sikistirma

```bash
# Log rotation (logrotate + zstd)
/var/log/klipper/*.log {
    daily
    rotate 3
    compress
    compresscmd /usr/bin/zstd
    compressext .zst
    maxsize 10M
}

# Backup sikistirma
kos_backup: tar.zst formati (gzip yerine zstd)

# tmpfs: gecici dosyalar RAM'de
tmpfs /tmp tmpfs defaults,noatime,size=64M 0 0
```

### Katman 4: Uygulama Optimizasyonu

```
KlipperScreen: Paneller lazy-load (sadece acildiginda belleğe alinir)
AI Monitor: Model sadece baski sirasinda yuklenir, idle'da unload
Python: PYTHONOPTIMIZE=2 (docstring kaldirma, assert devre disi)
earlyoom: OOM oncesi dusuk oncelikli surecleri kurtarma
VTE Terminal: Sadece acildiginda baslatilir, kapatilinca bellek serbest
```

### RAM Butcesi (2GB hedef)

| Bilesen | Maks RAM |
|---------|----------|
| Linux kernel + OS | ~200MB |
| Klipper | ~256MB |
| Moonraker | ~200MB |
| KlipperScreen + Paneller | ~150MB |
| Crowsnest (kamera) | ~100MB |
| AI Monitor (baski sirasinda) | ~200MB |
| Nginx + diger | ~50MB |
| **Toplam** | **~1156MB** |
| zram overhead | ~50MB |
| **Kalan (buffer/cache)** | **~794MB** |

---

## Bolum 5: Terminal Paneli & Klavye/Mouse Destegi

### VTE3 Terminal

- **Widget**: `Vte.Terminal` (libvte-2.91, GTK3 native)
- **Shell**: Kullanicinin varsayilan shell'i (`/bin/bash`)
- **Guvenlik**: `klipper` kullanicisi olarak calisir (root degil)
- **RAM**: ~8MB (lazy-load)
- **Paket**: `gir1.2-vte-2.91`

### Klavye/Mouse Entegrasyonu

- KlipperScreen GTK3 tabanli -> fiziksel klavye/mouse otomatik calisir
- Dokunmatik ekran kullanicilari icin: `matchbox-keyboard` (on-screen klavye)
- `show_cursor: True` zaten config'de mevcut
- WiFi sifre girisi, terminal kullanimi, config duzenleme icin gerekli

---

## Bolum 6: Dosya Yapisi

```
KlipperOS-AI/
+-- ai-monitor/
|   +-- config_manager.py          YENI  AI Config Manager modulu
|   +-- print_monitor.py           EDIT  config_manager entegrasyonu
+-- ks-panels/                     YENI  KlipperScreen ozel panelleri
|   +-- kos_system_api.py          YENI  Sistem API
|   +-- kos_network.py             YENI  Ag Ayarlari paneli
|   +-- kos_tailscale.py           YENI  Tailscale VPN paneli
|   +-- kos_updates.py             YENI  Guncelleme paneli
|   +-- kos_backup_panel.py        YENI  Yedekleme paneli
|   +-- kos_mcu_panel.py           YENI  MCU Yonetimi paneli
|   +-- kos_sysinfo.py             YENI  Sistem+MCU Bilgisi paneli
|   +-- kos_ai_settings.py         YENI  AI Ayarlari paneli
|   +-- kos_services.py            YENI  Servis Yonetimi paneli
|   +-- kos_logs.py                YENI  Log Goruntule paneli
|   +-- kos_terminal.py            YENI  VTE3 Terminal paneli
|   +-- kos_power.py               YENI  Guc Yonetimi paneli
+-- scripts/
|   +-- install-light.sh           EDIT  zram + earlyoom kurulumu
|   +-- install-standard.sh        EDIT  panel kurulumu + VTE3 + cgroup
|   +-- setup-zram.sh              YENI  zram yapilandirma scripti
+-- config/
|   +-- klipperscreen/
|   |   +-- KlipperScreen.conf     EDIT  Sistem menusu ekleme
|   +-- systemd/
|   |   +-- kos-zram.service       YENI  zram systemd servisi
|   |   +-- memory-limits/         YENI  Servis cgroup override dosyalari
|   +-- logrotate/
|       +-- klipperos              YENI  Log rotation config (zstd)
+-- README.md                      EDIT  Yeni ozellikler dokumantasyonu

Toplam: 17 yeni dosya, 5 mevcut dosya duzenleme
```

---

## Referanslar

- zram + zstd: https://wiki.archlinux.org/title/Zram
- KlipperScreen panel sistemi: https://github.com/KlipperScreen/KlipperScreen
- Moonraker File API: https://moonraker.readthedocs.io/en/latest/web_api/
- VTE3: https://wiki.gnome.org/Apps/Terminal/VTE
- psutil: https://psutil.readthedocs.io/
