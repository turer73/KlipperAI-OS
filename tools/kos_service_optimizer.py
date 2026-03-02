#!/usr/bin/env python3
"""
KlipperOS-AI — Service Optimizer
=================================
Profil bazli gereksiz servisleri devre disi birakir, gerekli olanlari aktif eder.
Raspberry Pi / SBC uzerinde RAM ve CPU tasarrufu saglar.

Kullanim:
    kos-service-optimizer scan              # Mevcut durumu tara
    kos-service-optimizer scan --profile LIGHT
    kos-service-optimizer apply STANDARD    # Profil uygula
    kos-service-optimizer apply LIGHT --dry-run
    kos-service-optimizer list              # Tum profilleri listele
"""

import argparse
import subprocess
from pathlib import Path

# --- Constants ---

PROFILE_FILE = Path("/etc/klipperos-ai/profile")
PROFILE_CHOICES = ["LIGHT", "STANDARD", "FULL"]

# Profil bazli servis matrisi
# "enable" = baslatilacak, "disable" = durdurulacak
SERVICE_MATRIX = {
    "LIGHT": {
        "disable": [
            "KlipperScreen.service",
            "crowsnest.service",
            "klipperos-ai-monitor.service",
            "bluetooth.service",
            "snapd.service",
            "snapd.socket",
            "snapd.seeded.service",
            "ModemManager.service",
        ],
        "enable": [
            "klipper.service",
            "moonraker.service",
            "nginx.service",
            "earlyoom.service",
            "ssh.service",
            "avahi-daemon.service",
        ],
        "optional": [
            "tailscaled.service",
            "ollama.service",
        ],
    },
    "STANDARD": {
        "disable": [
            "bluetooth.service",
            "snapd.service",
            "snapd.socket",
            "snapd.seeded.service",
            "ModemManager.service",
        ],
        "enable": [
            "klipper.service",
            "moonraker.service",
            "nginx.service",
            "KlipperScreen.service",
            "crowsnest.service",
            "klipperos-ai-monitor.service",
            "avahi-daemon.service",
            "earlyoom.service",
            "ssh.service",
        ],
        "optional": [
            "tailscaled.service",
            "ollama.service",
        ],
    },
    "FULL": {
        "disable": [
            "snapd.service",
            "snapd.socket",
            "snapd.seeded.service",
        ],
        "enable": [
            "klipper.service",
            "moonraker.service",
            "nginx.service",
            "KlipperScreen.service",
            "crowsnest.service",
            "klipperos-ai-monitor.service",
            "avahi-daemon.service",
            "earlyoom.service",
            "ssh.service",
            "ollama.service",
        ],
        "optional": [
            "tailscaled.service",
            "klipper-2.service",
            "moonraker-2.service",
            "klipper-3.service",
            "moonraker-3.service",
        ],
    },
}


# --- systemctl helpers ---

def run_systemctl(action, service):
    """systemctl komutunu calistir."""
    try:
        result = subprocess.run(
            ["systemctl", action, service],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def is_service_active(service):
    return run_systemctl("is-active", service)


def is_service_enabled(service):
    return run_systemctl("is-enabled", service)


def service_exists(service):
    try:
        result = subprocess.run(
            ["systemctl", "cat", service],
            capture_output=True, text=True, timeout=10,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def get_service_memory_kb(service):
    """Servisin bellek kullanimini dondur (KB)."""
    try:
        result = subprocess.run(
            ["systemctl", "show", service, "--property=MemoryCurrent"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            val = result.stdout.strip().split("=")[1]
            if val != "[not set]" and val.isdigit():
                return int(val) // 1024
    except (subprocess.TimeoutExpired, FileNotFoundError, IndexError, ValueError):
        pass
    return 0


# --- Profile detection ---

def get_current_profile():
    """Profil dosyasindan mevcut profili oku."""
    try:
        return PROFILE_FILE.read_text().strip().upper()
    except OSError:
        return "STANDARD"


# --- Scan / Apply / Status ---

def scan_services(profile_name):
    """Profil icin servis durumunu tara."""
    if profile_name not in SERVICE_MATRIX:
        print(f"Hata: Bilinmeyen profil: {profile_name}")
        return {}

    matrix = SERVICE_MATRIX[profile_name]
    report = {"to_disable": [], "to_enable": [], "already_ok": [], "not_found": []}

    for svc in matrix.get("disable", []):
        if not service_exists(svc):
            report["not_found"].append(svc)
        elif is_service_active(svc) or is_service_enabled(svc):
            mem = get_service_memory_kb(svc)
            report["to_disable"].append({"service": svc, "memory_kb": mem})
        else:
            report["already_ok"].append(svc)

    for svc in matrix.get("enable", []):
        if not service_exists(svc):
            report["not_found"].append(svc)
        elif not is_service_enabled(svc):
            report["to_enable"].append(svc)
        else:
            report["already_ok"].append(svc)

    return report


def apply_profile(profile_name, dry_run=False):
    """Profil bazli servis optimizasyonunu uygula."""
    if profile_name not in SERVICE_MATRIX:
        print(f"Hata: Bilinmeyen profil: {profile_name}")
        return False

    matrix = SERVICE_MATRIX[profile_name]
    prefix = "[DRY-RUN] " if dry_run else ""
    total_saved_kb = 0
    disabled_count = 0
    enabled_count = 0

    print(f"\n{prefix}Profil: {profile_name}")
    print("=" * 50)

    # Devre disi birak
    print(f"\n{prefix}Devre disi birakiliyor:")
    for svc in matrix.get("disable", []):
        if not service_exists(svc):
            continue
        if is_service_active(svc) or is_service_enabled(svc):
            mem = get_service_memory_kb(svc)
            total_saved_kb += mem
            mem_str = f" ({mem // 1024} MB)" if mem > 1024 else ""
            if dry_run:
                print(f"  [-] {svc}{mem_str}")
            else:
                run_systemctl("stop", svc)
                run_systemctl("disable", svc)
                print(f"  [-] {svc}{mem_str} — durduruldu")
            disabled_count += 1

    # Etkinlestir
    print(f"\n{prefix}Etkinlestiriliyor:")
    for svc in matrix.get("enable", []):
        if not service_exists(svc):
            continue
        if not is_service_enabled(svc):
            if dry_run:
                print(f"  [+] {svc}")
            else:
                run_systemctl("enable", svc)
                run_systemctl("start", svc)
                print(f"  [+] {svc} — baslatildi")
            enabled_count += 1

    print(f"\n{prefix}Sonuc:")
    print(f"  Devre disi: {disabled_count} servis")
    print(f"  Etkin:      {enabled_count} servis")
    if total_saved_kb > 0:
        print(f"  Tasarruf:   ~{total_saved_kb // 1024} MB RAM")

    return True


def show_status(profile_name=None):
    """Mevcut servis durumunu goster."""
    if profile_name is None:
        profile_name = get_current_profile()

    report = scan_services(profile_name)

    print(f"\nProfil: {profile_name}")
    print("=" * 50)

    if report.get("to_disable"):
        print(f"\nDevre disi birakilabilir ({len(report['to_disable'])}):")
        for item in report["to_disable"]:
            mem = item["memory_kb"]
            mem_str = f" ({mem // 1024} MB)" if mem > 1024 else ""
            print(f"  [!] {item['service']}{mem_str}")

    if report.get("to_enable"):
        print(f"\nEtkinlestirilmeli ({len(report['to_enable'])}):")
        for svc in report["to_enable"]:
            print(f"  [+] {svc}")

    ok_count = len(report.get("already_ok", []))
    nf_count = len(report.get("not_found", []))
    print(f"\nZaten dogru: {ok_count} | Bulunamadi: {nf_count}")


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(
        prog="kos-service-optimizer",
        description="KlipperOS-AI Service Optimizer — Profil bazli servis yonetimi",
    )
    sub = parser.add_subparsers(dest="command", help="Komut")

    scan_p = sub.add_parser("scan", help="Servis durumunu tara")
    scan_p.add_argument("--profile", choices=PROFILE_CHOICES, default=None)

    apply_p = sub.add_parser("apply", help="Profil optimizasyonunu uygula")
    apply_p.add_argument("profile", choices=PROFILE_CHOICES)
    apply_p.add_argument("--dry-run", action="store_true", help="Degisiklik yapmadan goster")

    sub.add_parser("list", help="Tum profillerdeki servisleri listele")

    args = parser.parse_args()

    if args.command == "scan" or args.command is None:
        show_status(getattr(args, "profile", None))
    elif args.command == "apply":
        apply_profile(args.profile, dry_run=args.dry_run)
    elif args.command == "list":
        for profile in PROFILE_CHOICES:
            matrix = SERVICE_MATRIX[profile]
            print(f"\n{'=' * 40}")
            print(f"  {profile}")
            print(f"{'=' * 40}")
            print(f"  Devre disi: {len(matrix.get('disable', []))}")
            print(f"  Etkin:      {len(matrix.get('enable', []))}")
            print(f"  Opsiyonel:  {len(matrix.get('optional', []))}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
