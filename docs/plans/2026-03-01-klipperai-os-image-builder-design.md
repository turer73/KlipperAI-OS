# KlipperAI-OS Image Builder Design

## Goal

Debian Live Build ile x86/PC icin bootable USB imaji uretmek. Tek imaj, ilk
boot'ta donanim algilama ile otomatik profil onerisi (LIGHT/STANDARD/FULL),
kullanici onay/secimi, internet uzerinden kurulum.

## Mimari

```
image-builder/
+-- build-image.sh                  Ana build scripti
+-- config/
|   +-- package-lists/
|   |   +-- klipperos.list.chroot   Debian paketleri
|   +-- includes.chroot/            Imaja kopyalanacak dosyalar
|   |   +-- opt/klipperos-ai/       Proje dosyalari
|   |   +-- etc/systemd/system/     first-boot servisi
|   |   +-- usr/local/bin/          CLI araclar + wizard
|   +-- hooks/live/
|   |   +-- 0100-setup.hook.chroot  Build sirasinda calisir
|   +-- bootloaders/                GRUB config
+-- first-boot-wizard.sh            Ilk boot TUI wizard
```

## Karar Ozeti

| Karar | Secim | Sebep |
|-------|-------|-------|
| Hedef donanim | x86/PC | Kullanici tercihi |
| Build araci | Debian Live Build | Resmi, x86 icin ideal, ISO/IMG uretir |
| Profil secimi | Tek imaj + ilk boot wizard | Kullanici dostu, tek dosya |
| Wizard TUI | whiptail | Debian'da varsayilan, hafif, ncurses |
| Profil mantigi | Donanim algilama + oneri | Mevcut hw-detect + recommend_profile |
| Diske kurulum | Istege bagli (live'dan da calisabilir) | Esneklik |

---

## Bolum 1: Build Sureci

### build-image.sh

`lb config` + `lb build` ile Debian Bookworm tabanli live imaj uretir.

```bash
# Kullanim:
cd image-builder
sudo ./build-image.sh
# Cikti: klipperai-os-x86-v2.1.img (~2-3 GB)
```

### Adimlar

1. `lb config` — Debian Live Build yapilandirmasi
   - Distribution: bookworm
   - Architecture: amd64
   - Binary image: iso-hybrid (USB + CD boot)
   - Bootloader: grub-efi + syslinux (UEFI + Legacy BIOS)
   - No desktop environment (CLI only)

2. Paket listesi (`klipperos.list.chroot`)
   - Base: git, python3, python3-venv, python3-pip, build-essential
   - Network: network-manager, wpasupplicant, avahi-daemon, tailscale
   - Display: xserver-xorg, xinit, python3-gi, gir1.2-gtk-3.0, gir1.2-vte-2.91
   - Klipper deps: gcc-arm-none-eabi, stm32flash, dfu-util, avrdude
   - System: psutil, nginx, whiptail, sudo, openssh-server
   - Extras: matchbox-keyboard, earlyoom, zstd

3. `includes.chroot` — Dosya kopyalama
   - `/opt/klipperos-ai/` — Tum proje dosyalari (scripts, ai-monitor, ks-panels, tools, config)
   - `/etc/systemd/system/klipperai-first-boot.service` — Wizard servisi
   - `/usr/local/bin/klipperai-wizard` — Wizard scripti

4. `hooks/live/0100-setup.hook.chroot` — Build icinde kurulum
   - `klipper` kullanicisi olusturma
   - Dizin yapisi: printer_data/{config,logs,gcodes,database}
   - sudoers yapilandirmasi
   - Hostname: klipperos
   - Locale: tr_TR.UTF-8
   - Timezone: Europe/Istanbul (wizard'da degistirilebilir)

5. `lb build` — Imaj uretimi
   - Cikti: `live-image-amd64.hybrid.iso`
   - Rename: `klipperai-os-x86-v2.1.img`

---

## Bolum 2: Ilk Boot Wizard

### Akis

```
USB boot -> GRUB -> Live Debian yuklenir
    |
    v
klipperai-first-boot.service baslar (oneshot, After=network-online.target)
    |
    v
1. Hosgeldin ekrani (ASCII banner + versiyon)
    |
    v
2. Dil secimi (Turkce / English)
    |
    v
3. Donanim algilama + sonuclari gosterme
   - RAM: 8192 MB
   - CPU: 4 cekirdek (x86_64)
   - Disk: 120 GB SSD
   - Ag: eth0 (bagli), wlan0 (mevcut)
    |
    v
4. Profil onerisi + secim
   +----------------------------------------+
   | Donanim: 8GB RAM, 4 cekirdek           |
   | Onerilen profil: FULL                   |
   |                                         |
   | ( ) LIGHT    - Klipper + Moonraker      |
   | ( ) STANDARD - + KlipperScreen + AI     |
   | (*) FULL     - + Multi-printer + Timelapse |
   +----------------------------------------+
    |
    v
5. Ag ayarlari
   - WiFi SSID/sifre (wireless varsa)
   - Hostname degistirme
    |
    v
6. Kullanici ayarlari
   - klipper kullanici sifresi
   - SSH erisimi (acik/kapali)
    |
    v
7. Diske kurulum secimi
   - "Live olarak devam et" (RAM'de calis)
   - "Diske kur" -> disk secimi -> partitioning -> rsync
    |
    v
8. Profil installer calistirilir
   - internet uzerinden git clone (klipper, moonraker, vb.)
   - pip install
   - servis yapilandirmasi
    |
    v
9. Ozet + reboot onerisi
```

### Donanim Algilama -> Profil Mantigi

| RAM | CPU | Otomatik Oneri | Degistirilebilir? |
|-----|-----|----------------|-------------------|
| < 1.5 GB | herhangi | LIGHT (zorunlu) | Hayir |
| 1.5 - 3.5 GB | herhangi | STANDARD | Evet — LIGHT'a dusur |
| >= 4 GB | >= 4 | FULL | Evet — herhangi |
| >= 4 GB | < 4 | STANDARD | Evet — LIGHT veya FULL |

### Wizard Servisi

```ini
# /etc/systemd/system/klipperai-first-boot.service
[Unit]
Description=KlipperAI-OS First Boot Wizard
After=network-online.target
Wants=network-online.target
ConditionPathExists=/opt/klipperos-ai/.first-boot

[Service]
Type=oneshot
ExecStart=/usr/local/bin/klipperai-wizard
ExecStartPost=/bin/rm -f /opt/klipperos-ai/.first-boot
StandardInput=tty
StandardOutput=tty
TTYPath=/dev/tty1
RemainAfterExit=no

[Install]
WantedBy=multi-user.target
```

Sentinel dosyasi `.first-boot` wizard tamamlaninca silinir, tekrar calismaz.

---

## Bolum 3: Imaj Icerigi

### Pre-installed (imajda)

- Debian Bookworm minimal (systemd, apt, bash)
- Python 3.11+, pip, venv
- Git, build-essential, cmake
- X11, GTK3, VTE3, matchbox-keyboard
- Network Manager, avahi, ssh
- nginx (config hazir ama aktif degil)
- whiptail (wizard icin)
- earlyoom, zstd
- KlipperAI-OS proje dosyalari (/opt/klipperos-ai)
- Klipper build deps (gcc-arm-none-eabi, stm32flash, dfu-util)

### Ilk Boot'ta Kurulacak (internet gerekli)

- Klipper (git clone + venv + pip)
- Moonraker (git clone + venv + pip)
- Mainsail (wget release)
- KlipperScreen (STANDARD+: git clone + venv + pip)
- Crowsnest (STANDARD+: git clone + install)
- AI Monitor venv + pip (STANDARD+: tflite, opencv, numpy)
- Timelapse (FULL: git clone)
- Python venv'ler ve pip bagimliliklari

### Boyut Tahmini

| Bilesen | Boyut |
|---------|-------|
| Debian base | ~600 MB |
| Python + pip | ~200 MB |
| X11 + GTK3 | ~150 MB |
| Build tools | ~300 MB |
| KlipperAI-OS dosyalari | ~50 MB |
| Klipper deps | ~200 MB |
| Nginx + system tools | ~100 MB |
| **Toplam (sikistirilmis)** | **~1.5-2 GB** |

---

## Bolum 4: USB'den Boot Akisi

```
1. Kullanici: klipperai-os-x86-v2.1.img dosyasini indirir
2. Balena Etcher / dd / Rufus ile USB'ye yazar
3. PC'yi USB'den boot eder (BIOS/UEFI)
4. GRUB menu: "KlipperAI-OS" secilir
5. Live Debian boot eder (~30 saniye)
6. Wizard otomatik baslar (tty1)
7. Donanim algilama + profil secimi
8. Internet baglantisi (WiFi/Ethernet)
9. Profil kurulumu (~10-20 dakika, internet hizina bagli)
10. Reboot -> KlipperAI-OS hazir!
```

---

## Bolum 5: Dosya Yapisi

```
KlipperOS-AI/
+-- image-builder/                      YENI
|   +-- build-image.sh                  YENI  Ana build scripti
|   +-- config/
|   |   +-- package-lists/
|   |   |   +-- klipperos.list.chroot   YENI  Paket listesi
|   |   +-- includes.chroot/
|   |   |   +-- opt/klipperos-ai/       LINK  Proje dosyalari
|   |   |   +-- etc/
|   |   |   |   +-- systemd/system/
|   |   |   |       +-- klipperai-first-boot.service  YENI
|   |   |   +-- usr/local/bin/
|   |   |       +-- klipperai-wizard    YENI  Wizard script
|   |   +-- hooks/live/
|   |   |   +-- 0100-setup.hook.chroot  YENI  Build hook
|   |   +-- bootloaders/
|   |       +-- grub/
|   |           +-- grub.cfg            YENI  GRUB menu config
|   +-- first-boot-wizard.sh            YENI  Wizard ana scripti
+-- (mevcut proje dosyalari)

Toplam: 7 yeni dosya
```

---

## Referanslar

- Debian Live Build: https://live-team.pages.debian.net/live-manual/
- lb config/build: https://manpages.debian.org/bookworm/live-build/
- whiptail: ncurses dialog replacement
- MainsailOS (benzer proje): https://github.com/mainsail-crew/MainsailOS
