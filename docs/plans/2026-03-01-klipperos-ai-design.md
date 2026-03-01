# KlipperOS-AI — Design Document

> Date: 2026-03-01
> Version: 1.0.0
> Author: Zaman Huseyinli

## Goal

Klipper 3D printer firmware icin ozellestirilmis, AI destekli baski izleme
iceren hafif Linux distrosu. x86 ve SBC (RPi/Orange Pi) destekli.

## Architecture

### Base: Debian 12 (Bookworm)
- armhf/arm64: RPi 3/4/5, Orange Pi
- amd64: Eski PC/laptop

### Profile System (3-Tier)

| Profile | RAM | Hardware | Components |
|---------|-----|----------|------------|
| LIGHT | 512MB-1GB | RPi 3, old x86 | Klipper + Moonraker + Mainsail |
| STANDARD | 2GB+ | RPi 4 2GB, Orange Pi | + KlipperScreen + Crowsnest + AI Monitor |
| FULL | 4GB+ | RPi 4/5 4GB+, x86 | + Multi-printer + Advanced AI + Timelapse |

### Core Components

1. **Klipper** — 3D printer firmware host (Python, serial comm with MCU)
2. **Moonraker** — REST/WebSocket API server for Klipper
3. **Mainsail** — Modern web UI (served via nginx)
4. **KlipperScreen** — Mouse/touchscreen UI (pygame-based)
5. **Crowsnest** — USB/CSI camera streaming (MJPEG/RTSP)
6. **AI Print Monitor** — TFLite-based print failure detection

### AI Print Monitor
- Model: MobileNetV2 quantized (TFLite, ~5-10MB)
- RAM: ~80MB during inference
- Interval: Every 5-10 seconds (configurable)
- Detection: Spaghetti, layer shift, print completion
- Action: Moonraker API -> pause print, send notification
- Training data: open spaghetti detection datasets

### MCU Auto-Detection
- USB serial device scanning (/dev/ttyUSB*, /dev/ttyACM*)
- Known board identification (BTT SKR, Creality, MKS, etc.)
- Automatic Klipper MCU firmware flashing (optional)

### Project Structure

```
KlipperOS-AI/
├── scripts/
│   ├── hw-detect.sh              # Hardware detection
│   ├── mcu-detect.sh             # MCU/printer board detection
│   ├── install-klipper-os.sh     # Main unified installer
│   ├── install-light.sh          # Light profile
│   ├── install-standard.sh       # Standard profile
│   ├── install-full.sh           # Full profile
│   └── build-image.sh            # SD card image builder
├── config/
│   ├── klipper/                  # Printer config templates
│   │   ├── generic.cfg           # Generic printer config
│   │   ├── ender3.cfg            # Creality Ender 3
│   │   ├── ender3v2.cfg          # Creality Ender 3 V2
│   │   └── voron.cfg             # Voron 2.4
│   ├── moonraker/
│   │   └── moonraker.conf        # Moonraker config template
│   ├── mainsail/
│   │   └── nginx.conf            # Nginx for Mainsail
│   ├── klipperscreen/
│   │   └── KlipperScreen.conf    # KlipperScreen config
│   └── crowsnest/
│       └── crowsnest.conf        # Camera config
├── ai-monitor/
│   ├── print_monitor.py          # Main AI monitor daemon
│   ├── spaghetti_detect.py       # Spaghetti detection
│   ├── frame_capture.py          # Camera frame capture
│   └── models/                   # Pre-trained TFLite models
├── tools/
│   ├── kos_profile.py            # Profile manager
│   ├── kos_update.py             # OTA updater
│   ├── kos_backup.py             # Config backup/restore
│   └── kos_mcu.py                # MCU manager
├── pyproject.toml
├── README.md
└── docs/
```

### Network
- mDNS: klipperos.local (avahi)
- Mainsail web: port 80
- Moonraker API: port 7125
- Camera stream: port 8080
- Tailscale: uzaktan erisim (VPN mesh, port forwarding gereksiz)

### Remote Access (Tailscale)
- Otomatik kurulum tum profillerde
- Moonraker trusted_clients'a 100.64.0.0/10 (Tailscale CGNAT) eklenir
- Firewall'da tailscale0 arayuzune tam erisim
- `sudo tailscale up` ile baglanti, `tailscale status` ile durum
- MagicDNS ile: http://klipperos:80 (Tailscale ag uzerinden)

### SSH Hardening
- PermitRootLogin no
- PasswordAuthentication no (key-only)
- PermitEmptyPasswords no
- X11Forwarding no
- MaxAuthTries 3
- ClientAliveInterval 300, ClientAliveCountMax 2
- klipper kullanicisi icin ~/.ssh/authorized_keys otomatik olusturulur
- Tailscale SSH destegi: `sudo tailscale up --ssh`

### Security
- SSH: key-only auth, root login disabled
- klipper user for all services
- Firewall: only ports 22, 80, 7125, 8080 open (FULL profile)
- Tailscale: encrypted mesh VPN for remote access
