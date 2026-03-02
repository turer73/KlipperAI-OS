#!/usr/bin/env python3
"""
KlipperOS-AI — First-Run Wizard
=================================
Kurulum sonrasi ilk calisma sihirbazi.
Donanim tespit, profil secimi, model indirme, servis optimizasyonu, zram.

Kullanim:
    kos-firstrun run                     # Interaktif sihirbaz
    kos-firstrun run --non-interactive   # Otomatik (bash wizard'dan cagrilir)
    kos-firstrun run --skip-models       # Model indirme adimini atla
    kos-firstrun status                  # Durumu goster
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime

try:
    import yaml
except ImportError:
    yaml = None  # fallback to json

# --- Constants ---

VERSION = "2.0.0"
TAG = "[kos-firstrun]"
TOTAL_STEPS = 8

GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
BOLD = "\033[1m"
DIM = "\033[2m"
NC = "\033[0m"

KOS_CONFIG_DIR = "/etc/klipperos-ai"
PROFILE_FILE = os.path.join(KOS_CONFIG_DIR, "profile")
PROFILE_YML = os.path.join(KOS_CONFIG_DIR, "profile.yml")
FIRSTRUN_MARKER = os.path.join(KOS_CONFIG_DIR, ".firstrun-done")
MOONRAKER_URL = "http://127.0.0.1:7125"

MODEL_MATRIX = {
    "LIGHT": [],
    "STANDARD": ["qwen3:1.7b"],
    "FULL": ["qwen3:4b", "qwen3:1.7b"],
}

PROFILE_DESC = {
    "LIGHT": "Temel — Klipper + Moonraker + Mainsail, yerel model yok",
    "STANDARD": "Dengeli — + KlipperScreen + Crowsnest + AI (qwen3:1.7b)",
    "FULL": "Tam — + Multi-printer + Timelapse + Gelismis AI (qwen3:4b)",
}


# --- Output helpers ---

def info(msg):
    print(f"{GREEN}{TAG}{NC} {msg}")

def warn(msg):
    print(f"{YELLOW}{TAG}{NC} {msg}")

def error(msg):
    print(f"{RED}{TAG}{NC} {msg}")

def step_header(num, text):
    print(f"\n{BOLD}{CYAN}>>> [{num}/{TOTAL_STEPS}] {text}{NC}\n")


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    try:
        answer = input(f"  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        return default or ""
    return answer if answer else (default or "")


def ask_yesno(prompt, default=True):
    hint = "E/h" if default else "e/H"
    try:
        answer = input(f"  {prompt} [{hint}]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return default
    if answer in ("e", "evet", "y", "yes"):
        return True
    if answer in ("h", "hayir", "n", "no"):
        return False
    return default


# --- YAML helpers ---

def load_yaml(path):
    if not os.path.isfile(path):
        return {}
    with open(path) as f:
        return (yaml.safe_load(f) or {}) if yaml else json.loads(f.read())


def save_yaml(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        if yaml:
            yaml.safe_dump(data, f, default_flow_style=False, allow_unicode=True)
        else:
            json.dump(data, f, indent=2, ensure_ascii=False)
            f.write("\n")


# --- Utility ---

def _check_command(cmd):
    try:
        return subprocess.run(
            ["which", cmd], capture_output=True, timeout=5
        ).returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def _run_optimizer(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if r.stdout:
            for line in r.stdout.strip().splitlines():
                print(f"    {DIM}{line}{NC}")
        return r.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError):
        return False


# =============================================================================
# Step 1 — Welcome
# =============================================================================

def step_welcome():
    w = 56
    print(f"\n{BOLD}{'=' * w}{NC}")
    print(f"{BOLD}  KlipperOS-AI v2 — Ilk Calisma Sihirbazi{NC}")
    print(f"{BOLD}{'=' * w}{NC}\n")
    info(f"Surum: {VERSION}  |  Tarih: {datetime.now():%Y-%m-%d %H:%M}")
    print("  Bu sihirbaz sisteminizi KlipperOS-AI icin yapilandiracak:")
    print("  donanim tespit, profil secimi, model kurulumu,")
    print("  servis optimizasyonu ve yazici ag ayarlari.\n")


# =============================================================================
# Step 2 — Hardware Detection (+ MCU & Camera)
# =============================================================================

def step_hardware_detect():
    info("Donanim algilama baslatiliyor...")
    hw_data = _minimal_hw_detect()

    hw = hw_data.get("hardware", hw_data)
    cpu = hw.get("cpu", {})
    print(f"  {CYAN}RAM:{NC}       {hw.get('ram_mb', 0)} MB")
    print(f"  {CYAN}CPU:{NC}       {cpu.get('model', 'bilinmiyor')}")
    print(f"  {CYAN}Cekirdek:{NC}  {cpu.get('cores', '?')}C / {cpu.get('threads', '?')}T")

    # MCU detection
    mcu_devices = _detect_mcu()
    hw_data["mcu_devices"] = mcu_devices
    if mcu_devices:
        info(f"MCU algilandi: {len(mcu_devices)} adet")
        for dev in mcu_devices:
            print(f"    {dev}")
    else:
        warn("MCU algilanamadi. printer.cfg'de manual MCU yolu belirtin.")

    # Camera detection
    cameras = _detect_cameras()
    hw_data["cameras"] = cameras
    if cameras:
        info(f"Kamera algilandi: {len(cameras)} adet")
        for cam in cameras:
            print(f"    {cam}")
    else:
        info("Kamera bulunamadi (Crowsnest icin gerekli degil).")

    return hw_data


def _minimal_hw_detect():
    ram_mb = 1024
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal"):
                    ram_mb = int(line.split()[1]) // 1024
                    break
    except (OSError, ValueError):
        pass

    cpu_model, cpu_cores, cpu_threads = "unknown", 1, 1
    try:
        with open("/proc/cpuinfo") as f:
            content = f.read()
        for line in content.splitlines():
            if line.startswith("model name") and cpu_model == "unknown":
                cpu_model = line.split(":", 1)[1].strip()
            if line.startswith("cpu cores"):
                cpu_cores = int(line.split(":", 1)[1].strip())
        cpu_threads = max(content.count("processor\t:"), 1)
    except (OSError, ValueError):
        pass

    return {
        "hardware": {
            "ram_mb": ram_mb,
            "cpu": {"model": cpu_model, "cores": cpu_cores, "threads": cpu_threads},
        },
    }


def _detect_mcu():
    """Detect serial MCU devices (typical Klipper MCUs)."""
    devices = []
    for pattern in ("/dev/serial/by-id/*", "/dev/ttyACM*", "/dev/ttyUSB*"):
        try:
            import glob as _glob
            devices.extend(_glob.glob(pattern))
        except Exception:
            pass
    return devices


def _detect_cameras():
    """Detect video devices for Crowsnest."""
    devices = []
    try:
        import glob as _glob
        devices = _glob.glob("/dev/video*")
    except Exception:
        pass
    return devices


# =============================================================================
# Step 3 — Profile Selection
# =============================================================================

def step_profile_select(hw_data, interactive=True):
    ram_mb = hw_data.get("hardware", hw_data).get("ram_mb", 1024)

    if ram_mb <= 768:
        recommended = "LIGHT"
    elif ram_mb <= 2048:
        recommended = "STANDARD"
    else:
        recommended = "FULL"

    info(f"Onerilen profil: {BOLD}{recommended}{NC}")
    for key, desc in PROFILE_DESC.items():
        marker = " >>>" if key == recommended else "    "
        print(f"  {marker} {BOLD}{key:10s}{NC} — {desc}")

    if not interactive:
        info(f"Non-interactive mod: '{recommended}' secildi.")
        return recommended

    choice = ask("Profil seciniz (LIGHT/STANDARD/FULL)", default=recommended).upper()
    if choice not in PROFILE_DESC:
        warn(f"Gecersiz secim: '{choice}', onerilen kullaniliyor: {recommended}")
        choice = recommended
    info(f"Secilen profil: {BOLD}{choice}{NC}")
    return choice


# =============================================================================
# Step 4 — Model Download
# =============================================================================

def step_model_download(profile, skip=False):
    models = MODEL_MATRIX.get(profile, [])
    if skip:
        info("Model indirme adimi atlanildi (--skip-models).")
        return True
    if not models:
        info("LIGHT profil: yerel model gerekmez, uzak AI kullanilacak.")
        return True
    if not _check_command("ollama"):
        warn("Ollama bulunamadi! Model indirilemez.")
        warn("Kurulum: curl -fsSL https://ollama.com/install.sh | sh")
        return False

    success = True
    for i, model in enumerate(models, 1):
        info(f"Model indiriliyor ({i}/{len(models)}): {BOLD}{model}{NC}")
        try:
            r = subprocess.run(["ollama", "pull", model], timeout=1800)
            if r.returncode == 0:
                info(f"  {model} — basariyla indirildi.")
            else:
                error(f"  {model} — indirme basarisiz (kod: {r.returncode}).")
                success = False
        except subprocess.TimeoutExpired:
            error(f"  {model} — zaman asimi (30 dk).")
            success = False
        except FileNotFoundError:
            error("  ollama komutu bulunamadi.")
            return False
    return success


# =============================================================================
# Step 5 — Tailscale Setup
# =============================================================================

def step_tailscale_setup(interactive=True):
    if not interactive:
        info("Non-interactive mod: Tailscale kurulumu atlanildi.")
        return False
    if not ask_yesno("Tailscale VPN agini yapilandirmak ister misiniz?", default=False):
        info("Tailscale kurulumu atlanildi.")
        return False
    if not _check_command("tailscale"):
        warn("Tailscale bulunamadi!")
        print("  Kurmak icin: curl -fsSL https://tailscale.com/install.sh | sh")
        return False

    info("Tailscale baslatiliyor...")
    try:
        r = subprocess.run(["tailscale", "up"], timeout=60)
        if r.returncode == 0:
            info("Tailscale basariyla baglandi.")
            subprocess.run(
                ["systemctl", "enable", "tailscaled.service"],
                capture_output=True, timeout=10,
            )
            return True
        warn("Tailscale baglanti hatasi. Daha sonra 'tailscale up' ile deneyin.")
    except subprocess.TimeoutExpired:
        warn("Tailscale baglantisi zaman asimi.")
    except FileNotFoundError:
        error("tailscale komutu bulunamadi.")
    return False


# =============================================================================
# Step 6 — Remote AI Server
# =============================================================================

def step_remote_ai_config(profile, interactive=True):
    config = {}

    if profile != "LIGHT":
        if not interactive:
            return config
        if not ask_yesno("Uzak AI sunucusu yapilandirmak ister misiniz? (yedek)", default=False):
            return config
    else:
        info("LIGHT profil: uzak AI sunucu adresi oneriliyor.")
        if not interactive:
            info("Non-interactive mod: uzak sunucu yapilandirmasi atlanildi.")
            return config

    url = ask("Uzak Ollama sunucu adresi (orn: http://192.168.1.100:11434)", default="")
    if not url:
        if profile == "LIGHT":
            warn("Adres girilmedi. Tailscale uzerinden otomatik kesfedilecek.")
        return config

    config["remote_server"] = url
    info(f"Uzak sunucu: {url}")
    info("Baglanti kontrol ediliyor...")
    try:
        import urllib.request
        import urllib.error
        req = urllib.request.Request(url.rstrip("/") + "/api/tags", method="GET")
        resp = urllib.request.urlopen(req, timeout=5)
        config["remote_verified"] = resp.status == 200
    except (OSError, ValueError):
        config["remote_verified"] = False

    if config.get("remote_verified"):
        info("Uzak sunucu erisilebilir.")
    else:
        warn("Uzak sunucuya erisilemedi. Adres dogrulugunu kontrol edin.")
    return config


# =============================================================================
# Step 7 — System Tuning (service optimizer + zram + memory limits)
# =============================================================================

def step_system_tuning(profile):
    info("Sistem optimizasyonu baslatiliyor...")

    # Service optimizer
    info(f"  Servis optimizasyonu uygulaniyor (profil: {profile})...")
    svc_ok = _run_optimizer(
        [sys.executable, "-m", "tools.kos_service_optimizer", "apply", profile]
    )
    if not svc_ok:
        # Fallback: entry point
        svc_ok = _run_optimizer(["kos-service-optimizer", "apply", profile])
    info("  Servis: tamamlandi." if svc_ok else "  Servis: basarisiz/bulunamadi.")

    # zram setup
    info("  Zram swap ayarlaniyor...")
    zram_ok = _setup_zram()
    info("  Zram: tamamlandi." if zram_ok else "  Zram: basarisiz/atlanildi.")

    # Memory limits for Klipper ecosystem
    info("  Bellek limitleri ayarlaniyor...")
    mem_ok = _setup_memory_limits(profile)
    info("  Bellek: tamamlandi." if mem_ok else "  Bellek: basarisiz/atlanildi.")

    return svc_ok or zram_ok or mem_ok


def _setup_zram():
    """Enable zram swap (critical for low-RAM SBCs)."""
    try:
        # Check if zram module available
        r = subprocess.run(
            ["modprobe", "zram"], capture_output=True, timeout=10,
        )
        if r.returncode != 0:
            return False

        # Get RAM size for zram calculation
        ram_mb = 1024
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        ram_mb = int(line.split()[1]) // 1024
                        break
        except (OSError, ValueError):
            pass

        # zram size = min(RAM/2, 2GB)
        zram_mb = min(ram_mb // 2, 2048)

        # Write systemd-zram-generator config
        zram_conf = "/etc/systemd/zram-generator.conf"
        conf_content = (
            "[zram0]\n"
            f"zram-size = {zram_mb}\n"
            "compression-algorithm = zstd\n"
            "swap-priority = 100\n"
        )
        os.makedirs(os.path.dirname(zram_conf), exist_ok=True)
        with open(zram_conf, "w") as f:
            f.write(conf_content)

        # Set vm.swappiness for SBC
        subprocess.run(
            ["sysctl", "-w", "vm.swappiness=60"],
            capture_output=True, timeout=5,
        )
        return True
    except (OSError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _setup_memory_limits(profile):
    """Set systemd memory limits per profile."""
    limits = {
        "LIGHT": {
            "klipper.service": "200M",
            "moonraker.service": "200M",
        },
        "STANDARD": {
            "klipper.service": "300M",
            "moonraker.service": "300M",
            "KlipperScreen.service": "200M",
            "crowsnest.service": "200M",
            "klipperos-ai-monitor.service": "300M",
        },
        "FULL": {
            "klipper.service": "400M",
            "moonraker.service": "400M",
            "KlipperScreen.service": "300M",
            "crowsnest.service": "300M",
            "klipperos-ai-monitor.service": "500M",
            "ollama.service": "4G",
        },
    }

    svc_limits = limits.get(profile, {})
    if not svc_limits:
        return False

    ok = True
    for svc, limit in svc_limits.items():
        override_dir = f"/etc/systemd/system/{svc}.d"
        override_file = os.path.join(override_dir, "memory-limit.conf")
        try:
            os.makedirs(override_dir, exist_ok=True)
            with open(override_file, "w") as f:
                f.write(f"[Service]\nMemoryMax={limit}\n")
        except OSError:
            ok = False

    # Reload systemd
    subprocess.run(
        ["systemctl", "daemon-reload"],
        capture_output=True, timeout=15,
    )
    return ok


# =============================================================================
# Step 8 — Summary & Marker
# =============================================================================

def step_summary(profile, hw_data, models_ok, ts_ok, remote_cfg, tuning_ok):
    hw = hw_data.get("hardware", hw_data)
    ram_mb = hw.get("ram_mb", 0)
    models = MODEL_MATRIX.get(profile, [])

    print(f"\n{BOLD}{'=' * 56}{NC}")
    print(f"{BOLD}  KlipperOS-AI — Kurulum Ozeti{NC}")
    print(f"{BOLD}{'=' * 56}{NC}\n")
    print(f"  {CYAN}Profil:{NC}      {BOLD}{profile}{NC}")
    print(f"  {CYAN}RAM:{NC}         {ram_mb} MB")
    print(f"  {CYAN}Modeller:{NC}    {', '.join(models) or 'yok (uzak AI)'}")
    print(f"  {CYAN}Model:{NC}       {'Basarili' if models_ok else 'Basarisiz/Atlanildi'}")
    print(f"  {CYAN}Tailscale:{NC}   {'Aktif' if ts_ok else 'Kapali/Atlanildi'}")

    mcu = hw_data.get("mcu_devices", [])
    cams = hw_data.get("cameras", [])
    print(f"  {CYAN}MCU:{NC}         {len(mcu)} adet algilandi")
    print(f"  {CYAN}Kamera:{NC}      {len(cams)} adet algilandi")

    if remote_cfg.get("remote_server"):
        st = "Dogrulandi" if remote_cfg.get("remote_verified") else "Dogrulanamadi"
        print(f"  {CYAN}Uzak AI:{NC}     {remote_cfg['remote_server']} ({st})")
    print(f"  {CYAN}Sistem:{NC}      {'Uygulandi' if tuning_ok else 'Atlanildi'}")

    # Save profile file
    try:
        os.makedirs(KOS_CONFIG_DIR, exist_ok=True)
        with open(PROFILE_FILE, "w") as f:
            f.write(profile)
        info(f"Profil dosyasi kaydedildi: {PROFILE_FILE}")
    except PermissionError:
        error(f"Profil dosyasi kaydedilemedi: {PROFILE_FILE}")

    # Save profile.yml
    data = {
        "version": VERSION,
        "profile": profile,
        "timestamp": datetime.now().isoformat(),
        "hardware": {"ram_mb": ram_mb, "cpu": hw.get("cpu", {})},
        "models": models,
        "tailscale": ts_ok,
        "mcu_devices": mcu,
        "cameras": cams,
    }
    if remote_cfg.get("remote_server"):
        data["remote_server"] = remote_cfg["remote_server"]
    try:
        save_yaml(PROFILE_YML, data)
        info(f"Profil YAML kaydedildi: {PROFILE_YML}")
    except PermissionError:
        error(f"Profil YAML kaydedilemedi: {PROFILE_YML}")

    # Create marker
    try:
        with open(FIRSTRUN_MARKER, "w") as f:
            f.write(f"completed={datetime.now().isoformat()}\n")
            f.write(f"profile={profile}\nversion={VERSION}\n")
        info(f"Isaret dosyasi olusturuldu: {FIRSTRUN_MARKER}")
    except PermissionError:
        error(f"Isaret dosyasi olusturulamadi: {FIRSTRUN_MARKER}")

    print()
    info(f"{BOLD}Ilk calisma sihirbazi tamamlandi!{NC}\n")


# =============================================================================
# Status
# =============================================================================

def show_status():
    print()
    if os.path.isfile(FIRSTRUN_MARKER):
        info("Ilk calisma sihirbazi: TAMAMLANDI")
        try:
            with open(FIRSTRUN_MARKER) as f:
                for line in f:
                    k, _, v = line.strip().partition("=")
                    if k and v:
                        print(f"  {CYAN}{k}:{NC} {v}")
        except OSError:
            pass
        if os.path.isfile(PROFILE_YML):
            try:
                cfg = load_yaml(PROFILE_YML)
                print(f"  {CYAN}Profil:{NC} {cfg.get('profile', '?')}")
                print(f"  {CYAN}MCU:{NC} {len(cfg.get('mcu_devices', []))} adet")
                print(f"  {CYAN}Kamera:{NC} {len(cfg.get('cameras', []))} adet")
            except (OSError, json.JSONDecodeError):
                pass
    else:
        warn("Ilk calisma sihirbazi: HENUZ CALISTIRILMADI")
        print(f"  Calistirmak icin: {BOLD}sudo kos-firstrun run{NC}")
    print()


# =============================================================================
# Wizard Runner
# =============================================================================

def run_wizard(skip_models=False, non_interactive=False):
    interactive = not non_interactive

    # Root check
    if not (hasattr(os, "geteuid") and os.geteuid() == 0):
        error("Bu sihirbaz root yetkisi gerektirir.")
        error("Lutfen 'sudo kos-firstrun run' ile calistirin.")
        sys.exit(1)

    # Already completed?
    if os.path.isfile(FIRSTRUN_MARKER):
        warn("Ilk calisma sihirbazi daha once tamamlanmis.")
        if interactive:
            if not ask_yesno("Tekrar calistirmak istiyor musunuz?", default=False):
                info("Iptal edildi.")
                return
        else:
            info("Non-interactive mod: tekrar calistiriliyor.")

    step_header(1, "Hosgeldiniz")
    step_welcome()

    step_header(2, "Donanim Algilama")
    hw_data = step_hardware_detect()

    step_header(3, "Profil Secimi")
    profile = step_profile_select(hw_data, interactive=interactive)

    step_header(4, "Model Kurulumu")
    models_ok = step_model_download(profile, skip=skip_models)

    step_header(5, "Tailscale VPN Ayari")
    ts_ok = step_tailscale_setup(interactive=interactive)

    step_header(6, "Uzak AI Sunucu Ayari")
    remote_cfg = step_remote_ai_config(profile, interactive=interactive)

    step_header(7, "Sistem Optimizasyonu")
    tuning_ok = step_system_tuning(profile)

    step_header(8, "Ozet Rapor")
    step_summary(profile, hw_data, models_ok, ts_ok, remote_cfg, tuning_ok)


# =============================================================================
# CLI Entry Point
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="KlipperOS-AI v2 — Ilk Calisma Sihirbazi",
        prog="kos-firstrun",
    )
    parser.add_argument("--skip-models", action="store_true",
                        help="Model indirme adimini atla")
    parser.add_argument("--non-interactive", action="store_true",
                        help="Otomatik varsayilanlarla calistir (soru sorma)")
    parser.add_argument("command", nargs="?", default="run",
                        choices=["run", "status"],
                        help="Komut: run (varsayilan) veya status")

    args = parser.parse_args()

    if args.command == "status":
        show_status()
    else:
        run_wizard(skip_models=args.skip_models, non_interactive=args.non_interactive)


if __name__ == "__main__":
    main()
