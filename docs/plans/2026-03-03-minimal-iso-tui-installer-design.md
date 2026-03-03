# KlipperOS-AI Minimal ISO + Python TUI Installer Tasarimi

**Tarih:** 2026-03-03
**Durum:** Onaylandi
**Yaklasim:** Yaklasim A — Minimal ISO + Python TUI Installer

---

## 1. Problem

Mevcut sistem ~3GB monolitik ISO uretir. Tum paketler (gcc, xorg, klipper, moonraker, vs.) ISO icinde gomer. First-boot wizard'da 60+ ek paket daha indirir. Sonuc: buyuk ISO, internet zaten gerekli, guncelligin garantisi yok.

## 2. Cozum

ISO'yu ~500MB'a kucult: sadece boot + WiFi + Python TUI installer. Tum yazilim bilesenleri internet uzerinden indirilir. Bu sayede:
- ISO boyutu dramatik duser
- Her kurulum guncel paketlerle yapilir
- Bakim kolaylasirir (ISO degil installer guncellenir)

## 3. Kararlar

| Karar | Secim |
|-------|-------|
| Hedef donanim | x86 oncelikli, ARM sonra |
| Arayuz | Terminal TUI (whiptail/dialog) |
| Base kurulum | Minimal ISO (autoinstall) |
| Bilesen secimi | Profil bazli (LIGHT/STANDARD/FULL) |
| Mevcut kodla iliski | Sifirdan Python ile yaz |
| Donanim tespiti | Otomatik (mevcut hw-detect mantigi Python'a tasinir) |

## 4. Mimari

```
Minimal ISO (~500MB)
  Ubuntu Server 24.04 minimal
  + linux-firmware (WiFi/Ethernet)
  + NetworkManager + wpasupplicant
  + Python 3 + whiptail
  + kos-installer (Python TUI)
  + systemd first-boot service

    |  USB boot -> autoinstall -> reboot
    v

First Boot: Python TUI Installer
  1. WiFi Baglan
  2. Profil Sec
  3. Internet Indirme + Kurulum
```

## 5. Minimal ISO Icerigi

### ISO'da kalan paketler (~500MB)

```
linux-firmware           # WiFi/Ethernet suruculeri
NetworkManager           # WiFi baglantisi
wpasupplicant            # WPA2/WPA3
avahi-daemon             # mDNS (.local)
python3, python3-venv    # TUI installer icin
whiptail                 # Terminal dialog kutulari
curl, wget, git          # Indirme araclari
ca-certificates          # HTTPS destegi
sudo, nano, htop         # Temel yonetim
```

### ISO'dan cikarilan paketler (internet'ten indirilecek)

- gcc, cmake, build-essential
- gcc-arm-none-eabi, stm32flash, dfu-util
- xserver-xorg, GTK3, matchbox-keyboard
- nginx, ffmpeg, v4l-utils
- Klipper/Moonraker/Mainsail kaynak kodu
- KlipperOS-AI tools

## 6. TUI Installer Akisi

```
kos-installer baslatilir (systemd first-boot)

  1. HOSGELDIN EKRANI
     ASCII banner + "Kurulum basliyor" mesaji

  2. DONANIM TESPITI
     CPU model/cekirdek, RAM, Disk, Ag
     Profil onerisi hesapla

  3. AG BAGLANTISI
     Ethernet bagli mi? -> atla
     WiFi var mi?
       SSID listesi (sinyal gucu ile)
       Sifre girisi
       nmcli ile baglan
     Baglanti testi (ping 1.1.1.1)

  4. PROFIL SECIMI
     Donanim onerisi goster
     RAM < 1.5GB -> LIGHT zorla
     Kullanici secer: LIGHT / STANDARD / FULL

  5. KULLANICI AYARLARI
     Hostname (varsayilan: klipperos)
     Sifre degistir (varsayilan: klipper)

  6. KURULUM (internet uzerinden)
     apt update
     Profil paketlerini indir+kur
       LIGHT:  build-essential, nginx
       STD:    + xorg, gtk3, ffmpeg
       FULL:   + tum paketler
     Klipper    -> git clone + venv
     Moonraker  -> git clone + venv
     Mainsail   -> wget release zip
     [STD+] KlipperScreen -> git clone
     [STD+] Crowsnest -> git clone
     [STD+] AI Monitor -> pip install
     Progress bar goster (% tamamlandi)

  7. SERVIS YAPILANDIRMA
     systemd servisleri olustur+etkinlestir
     nginx yapilandir
     printer_data/ dizin yapisi

  8. TAMAMLANDI
     IP adresi + Web UI URL
     SSH bilgileri
     Otomatik reboot
```

## 7. Profil Tanimlari

| Profil | Min RAM | Bilesenler |
|--------|---------|-----------|
| LIGHT | 512MB | Klipper + Moonraker + Mainsail + Nginx |
| STANDARD | 2GB | + KlipperScreen + Crowsnest + AI Monitor |
| FULL | 4GB | + Multi-printer + Timelapse + Tam AI |

Otomatik tespit:
- RAM < 1.5GB -> LIGHT (zorla)
- RAM >= 1.5GB -> STANDARD (onerilen)
- RAM >= 4GB + 4 cekirdek -> FULL (onerilen)

## 8. Dosya Yapisi

```
packages/installer/
  __init__.py
  __main__.py          # Entry point: python -m packages.installer
  tui.py               # Whiptail wrapper sinifi
  hw_detect.py         # Donanim tespiti (Python)
  network.py           # WiFi baglanti yonetimi
  profiles.py          # Profil tanimlari + paket listeleri
  steps/
    __init__.py
    welcome.py         # Adim 1
    hardware.py        # Adim 2
    network.py         # Adim 3
    profile.py         # Adim 4
    user_setup.py      # Adim 5
    install.py         # Adim 6
    services.py        # Adim 7
    complete.py        # Adim 8
  installers/
    __init__.py
    base.py            # Ortak kurulum mantigi
    klipper.py         # Klipper git clone + venv
    moonraker.py       # Moonraker git clone + venv
    mainsail.py        # Mainsail web release
    klipperscreen.py   # KlipperScreen (STANDARD+)
    crowsnest.py       # Crowsnest (STANDARD+)
    ai_monitor.py      # AI Monitor (STANDARD+)
  utils/
    __init__.py
    logger.py          # Loglama
    runner.py          # subprocess wrapper
    sentinel.py        # Idempotent kontrol dosyalari

image-builder/
  build-minimal-image.sh   # Yeni minimal ISO builder
  autoinstall/
    user-data              # Sadelestirilmis autoinstall
    meta-data
  config/
    includes.chroot/
      etc/systemd/system/
        kos-installer.service  # First-boot service
```

## 9. Tasarim Kararlari

### Idempotent Kurulum
Her bilesen kurucu sentinel dosyasi kontrol eder:
- `/opt/klipperos-ai/.installed-klipper`
- `/opt/klipperos-ai/.installed-moonraker`
- vb.
Yanm kesilirse tekrar calistirmada sadece eksik bilesenler kurulur.

### Progress Bar
`whiptail --gauge` ile toplam ilerleme gosterilir. Her bilesen kurulumu ayri fonksiyon, tamamlaninca yuzde guncellenir.

### Hata Yonetimi
Kritik bilesenlerde (Klipper, Moonraker) hata varsa durur ve kullaniciya sorar. Opsiyonel bilesenlerde (Crowsnest, Timelapse) hata varsa atlar, log'a yazar, devam eder.

### Loglama
Tum kurulum ciktisi `/var/log/kos-installer.log` dosyasina yazilir. TUI'da sadece ozet gosterilir.

### pyproject.toml Entry Point
```toml
kos-install = "packages.installer.__main__:main"
```

## 10. build-minimal-image.sh Degisiklikleri

Mevcut `build-image.sh`'den farklar:
1. Paket listesi ~15 pakete duser (sadece boot + wifi + python + whiptail)
2. KlipperOS-AI dosyalari ISO'ya gommek yerine sadece `packages/installer/` kopyalanir
3. `late-commands` sadelerir: installer kopyala + systemd service etkinlestir
4. ISO boyutu ~500MB hedefi
5. GitHub Actions split islemi gereksiz olabilir (2GB limiti altinda)

## 11. Kapsam Disi (v2'de)

- ARM/SBC destegi (ayri image gerekir)
- Web UI installer (TUI yeterli)
- Offline kurulum modu
- OTA (Over-The-Air) guncelleme sistemi
