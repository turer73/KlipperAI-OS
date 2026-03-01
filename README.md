# KlipperOS-AI

Klipper 3D printer firmware icin ozellestirilmis, AI destekli baski izleme iceren hafif Linux distrosu.

## Ozellikler

- **Klipper Ekosistemi**: Klipper + Moonraker + Mainsail + KlipperScreen + Crowsnest
- **AI Baski Izleme**: TFLite tabanli spaghetti/hata tespiti, otomatik duraklama
- **3 Katmanli Profil Sistemi**: Donanima gore otomatik profil onerisi
- **MCU Otomatik Algilama**: USB seri port tarama, bilinen kart tanimlama
- **Multi-printer Desteği**: Tek host'ta 3 yaziciya kadar (FULL profil)
- **Tailscale VPN**: Uzaktan erisim, port forwarding gereksiz
- **SBC + x86**: RPi 3/4/5, Orange Pi, eski PC/laptop desteği
- **Power Loss Recovery (PLR)**: Guc kesintisinde baskiyi katman bazli kurtarma
- **FlowGuard 4-Katman Tespit**: Filament sensor + Heater duty + TMC StallGuard + AI kamera ile akis kontrolu
- **Smart Rewind**: G-code koordinat geri sarma, belirli katmandan yeniden baslatma
- **TMC Kalibrasyon**: StallGuard tabanli akis kalibrasyonu
- **jschuh/klipper-macros**: Gelismis makro alt yapisi entegrasyonu

## Profiller

| Profil | RAM | Bilesenler |
|--------|-----|------------|
| **LIGHT** | 512MB-1GB | Klipper + Moonraker + Mainsail + PLR + Rewind |
| **STANDARD** | 2GB+ | + KlipperScreen + Crowsnest + AI Monitor + FlowGuard |
| **FULL** | 4GB+ | + Multi-printer + Timelapse + Gelismis AI |

## Kurulum

### Mevcut Debian/Ubuntu Sistemine

```bash
git clone https://github.com/klipperos-ai/klipperos-ai.git
cd klipperos-ai
sudo ./scripts/install-klipper-os.sh
```

Profil secenekleri:
```bash
sudo ./scripts/install-klipper-os.sh --light
sudo ./scripts/install-klipper-os.sh --standard
sudo ./scripts/install-klipper-os.sh --full
```

### Otomatik (Non-Interactive)

```bash
sudo ./scripts/install-klipper-os.sh --standard --non-interactive
```

## Yonetim Araclari

| Komut | Aciklama |
|-------|----------|
| `kos_profile status` | Mevcut profil durumu |
| `kos_profile list` | Profilleri listele |
| `kos_profile switch STANDARD` | Profil degistir |
| `kos_update check` | Guncellemeleri kontrol et |
| `kos_update all` | Tum bilesenleri guncelle |
| `kos_update download-models` | AI modellerini indir |
| `kos_backup create` | Config yedegi olustur |
| `kos_backup restore <isim>` | Yedekten geri yukle |
| `kos_backup list` | Yedekleri listele |
| `kos_mcu scan` | MCU kartlarini tara |
| `kos_mcu info` | MCU bilgisi |
| `kos_mcu flash --board creality` | Firmware flash |
| `kos-plr status` | PLR durumunu goster |
| `kos-plr resume` | Kayitli baskiyi devam ettir |
| `kos-plr clear` | PLR verisini temizle |
| `kos-rewind status` | Mevcut baski durumu |
| `kos-rewind goto --layer 50` | 50. katmandan yeniden baslat |
| `kos-rewind auto` | FlowGuard son OK katmanindan devam et |
| `kos-calibrate flow-status` | TMC kalibrasyon durumu |
| `kos-calibrate flow-test` | Yeni kalibrasyon testi |
| `kos_mcu list-boards` | Desteklenen kartlari listele |

## AI Baski Izleme

- **Model**: MobileNetV2 quantized (TFLite, ~5-10MB)
- **RAM**: ~80MB inference sirasinda
- **Aralik**: Her 5-10 saniye (yapilandirilabilir)
- **Tespit**: Spaghetti, ekstruzyon kaybi, stringing, baski tamamlanma
- **Aksiyon**: Otomatik duraklama, Moonraker bildirimi
- **False-positive korunma**: 3 ardisik alert gerekliligi

## Power Loss Recovery (PLR)

Guc kesintisinde baskiyi otomatik kurtarma:

```bash
kos-plr status    # PLR durumunu goster
kos-plr resume    # Kayitli baskiyi devam ettir
kos-plr clear     # PLR verisini temizle
kos-plr test      # PLR kayit testini calistir
```

PLR ozellikleri:
- Katman bazli durum kaydi (`[save_variables]` ile)
- Sicaklik, fan hizi, Z yukseklik otomatik geri yukleme
- jschuh/klipper-macros `BEFORE_LAYER_CHANGE` hook entegrasyonu
- Z homing guvenligi: SET_KINEMATIC_POSITION ile resume

## FlowGuard 4-Katman Akis Tespiti

4 bagimsiz kaynak ile filament akis kontrolu:

| Katman | Kaynak | Guven |
|--------|--------|-------|
| L1 | Filament motion sensor | 0.95 |
| L2 | Heater duty cycle analizi | 0.70 |
| L3 | TMC2209 StallGuard (SG_RESULT) | 0.85 |
| L4 | AI kamera (spaghetti/no_extrusion) | 0.60 |

Oylama mantigi:
- 0/4 anomali: OK
- 1/4 anomali: NOTICE (log)
- 2/4 anomali: WARNING (3 ardisik → CRITICAL)
- 3-4/4 anomali: CRITICAL (otomatik duraklama)

## Smart Rewind

Akis durmasinda baskiyi belirli bir katmandan yeniden baslatma:

```bash
kos-rewind status               # Mevcut baski durumu
kos-rewind goto --layer 50      # 50. katmandan baslat
kos-rewind goto --layer 50 --z-offset 1.0  # Z offset ile
kos-rewind auto                 # FlowGuard son OK katmanindan
kos-rewind auto --z-offset 1.0  # Z offset ile otomatik
```

Ozellikler:
- PrusaSlicer/OrcaSlicer/Cura G-code formatlari destegi
- Z offset ile kopru benzeri yapisma
- FlowGuard `last_ok_layer` entegrasyonu
- Otomatik nozzle isitma, purge ve retract

## TMC Akis Kalibrasyonu

TMC2209 StallGuard ile filament akis kalibrasyonu:

```bash
kos-calibrate flow-status    # Kalibrasyon durumu
kos-calibrate flow-test      # Yeni kalibrasyon testi (30sn)
kos-calibrate flow-reset     # Kalibrasyon verisini sil
```

## Ag Erisimi

| Servis | Yerel | Tailscale |
|--------|-------|-----------|
| Web UI (Mainsail) | `http://klipperos.local` | `http://klipperos:80` |
| Moonraker API | `http://klipperos.local:7125` | `http://klipperos:7125` |
| Kamera | `http://klipperos.local:8080` | `http://klipperos:8080` |
| Yazici 2 (FULL) | `http://klipperos.local:81` | `http://klipperos:81` |
| Yazici 3 (FULL) | `http://klipperos.local:82` | `http://klipperos:82` |

### Tailscale Uzaktan Erisim

Tum profillerde Tailscale otomatik kurulur. Baglanti:
```bash
sudo tailscale up        # Ilk baglanti (tarayicida onay)
tailscale status         # Durum kontrolu
tailscale ip -4          # Tailscale IP adresi
```

Tailscale MagicDNS ile yaziciya `http://klipperos` adresiyle erisebilirsiniz.
Port forwarding veya VPN yapilandirmasi gerekmez.

## Proje Yapisi

```
KlipperOS-AI/
├── scripts/
│   ├── hw-detect.sh              # Donanim algilama
│   ├── mcu-detect.sh             # MCU kart algilama
│   ├── install-klipper-os.sh     # Ana installer
│   ├── install-light.sh          # LIGHT profil
│   ├── install-standard.sh       # STANDARD profil
│   └── install-full.sh           # FULL profil
├── data/
│   └── boards.json                # MCU board veritabani
├── ai-monitor/
│   ├── print_monitor.py          # AI monitor daemon
│   ├── spaghetti_detect.py       # TFLite tespit modulu (5 sinif)
│   ├── flow_guard.py             # FlowGuard oylama motoru
│   ├── heater_analyzer.py        # Heater duty analizi
│   ├── extruder_monitor.py       # TMC StallGuard izleme
│   ├── frame_capture.py          # Kamera frame yakalama
│   └── models/                   # TFLite model dosyalari
├── tools/
│   ├── kos_profile.py            # Profil yoneticisi
│   ├── kos_update.py             # Guncelleme yoneticisi
│   ├── kos_backup.py             # Yedekleme yoneticisi
│   ├── kos_mcu.py                # MCU yoneticisi
│   ├── kos_plr.py                # PLR yoneticisi
│   ├── kos_rewind.py             # Smart Rewind araci
│   └── kos_calibrate.py          # TMC kalibrasyon araci
├── config/
│   ├── klipper/                  # Yazici config + KOS makrolar
│   │   ├── kos_plr.cfg           # PLR makrolari
│   │   ├── kos_flowguard.cfg     # FlowGuard makrolari
│   │   └── kos_rewind.cfg        # Rewind makrolari
│   ├── moonraker/                # Moonraker config
│   ├── mainsail/                 # Nginx config
│   ├── klipperscreen/            # KlipperScreen config
│   └── crowsnest/                # Kamera config
├── pyproject.toml
└── docs/
    └── plans/
```

## Desteklenen Kartlar

- **Creality**: Ender 3, Ender 3 V2, Ender 3 S1, CR-10
- **BTT**: SKR Mini E3 V3, SKR 3, Octopus V1.1, Manta M4P/M5P/M8P, EBB36/42 CAN
- **RP2040**: SKR Pico, Raspberry Pi Pico
- **Arduino**: Mega 2560
- **MKS**: Robin Nano V3
- **Fysetc**: Spider V2

## SSH Erisimi

SSH varsayilan olarak **sadece key auth** ile calisir (sifre ile giris kapali).

```bash
# SSH key kopyalama (yerel agdan)
ssh-copy-id klipper@klipperos.local

# Veya Tailscale SSH (key gerektirmez)
sudo tailscale up --ssh
ssh klipper@klipperos    # Tailscale ag uzerinden
```

SSH hardening ayarlari:
- Root login devre disi
- Sadece public key authentication
- MaxAuthTries: 3
- X11 forwarding kapali
- ClientAlive keepalive: 300s

## Guvenlik

- SSH: key-only auth, root login kapali, MaxAuthTries 3
- `klipper` kullanicisi ile servis calistirma
- Firewall: sadece 22, 80, 7125, 8080 portlari acik (FULL profil)
- Tailscale: sifrelenmis mesh VPN ile uzaktan erisim
- mDNS: `klipperos.local`

## Lisans

GPL-3.0
