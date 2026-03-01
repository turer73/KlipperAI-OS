#!/usr/bin/env python3
"""
KlipperOS-AI — Profile Manager
================================
Profil yonetimi: mevcut profili goster, profil degistir, bilesen listesi.

Kullanim:
    kos_profile status          # Mevcut profil bilgisi
    kos_profile list            # Profilleri listele
    kos_profile switch STANDARD # Profil degistir
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROFILE_FILE = Path("/etc/klipperos-ai/profile")
INSTALL_DIR = Path("/opt/klipperos-ai")

PROFILES = {
    "LIGHT": {
        "description": "Temel kurulum — Klipper + Moonraker + Mainsail",
        "min_ram_mb": 512,
        "services": ["klipper", "moonraker", "nginx", "avahi-daemon"],
        "components": ["Klipper", "Moonraker", "Mainsail"],
    },
    "STANDARD": {
        "description": "Standart — + KlipperScreen + Crowsnest + AI Monitor",
        "min_ram_mb": 2048,
        "services": [
            "klipper", "moonraker", "nginx", "avahi-daemon",
            "KlipperScreen", "crowsnest", "klipperos-ai-monitor",
        ],
        "components": [
            "Klipper", "Moonraker", "Mainsail",
            "KlipperScreen", "Crowsnest", "AI Print Monitor",
        ],
    },
    "FULL": {
        "description": "Tam — + Multi-printer + Timelapse + Gelismis AI",
        "min_ram_mb": 4096,
        "services": [
            "klipper", "moonraker", "nginx", "avahi-daemon",
            "KlipperScreen", "crowsnest", "klipperos-ai-monitor",
            "klipper-2", "moonraker-2", "klipper-3", "moonraker-3",
        ],
        "components": [
            "Klipper", "Moonraker", "Mainsail",
            "KlipperScreen", "Crowsnest", "AI Print Monitor",
            "Multi-printer (3x)", "Timelapse", "Gelismis AI",
        ],
    },
}


def get_current_profile() -> str:
    """Mevcut profili oku."""
    if PROFILE_FILE.exists():
        return PROFILE_FILE.read_text().strip()

    # Servislerden tahmin et
    for profile in ["FULL", "STANDARD", "LIGHT"]:
        services = PROFILES[profile]["services"]
        all_active = True
        for svc in services:
            result = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True, text=True,
            )
            if result.stdout.strip() != "active":
                all_active = False
                break
        if all_active:
            return profile

    return "UNKNOWN"


def get_ram_mb() -> int:
    """Toplam RAM (MB)."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) // 1024
    except Exception:
        pass
    return 0


def cmd_status(_args):
    """Mevcut profil durumunu goster."""
    profile = get_current_profile()
    ram = get_ram_mb()
    info = PROFILES.get(profile, {})

    print(f"KlipperOS-AI Profil Durumu")
    print(f"{'='*40}")
    print(f"Profil:     {profile}")
    print(f"RAM:        {ram} MB")
    print(f"Aciklama:   {info.get('description', '-')}")
    print()

    # Servis durumlari
    services = info.get("services", [])
    if services:
        print("Servisler:")
        for svc in services:
            result = subprocess.run(
                ["systemctl", "is-active", svc],
                capture_output=True, text=True,
            )
            state = result.stdout.strip()
            icon = "✓" if state == "active" else "✗"
            print(f"  {icon} {svc}: {state}")

    # Bilesenler
    components = info.get("components", [])
    if components:
        print(f"\nBilesenler: {', '.join(components)}")


def cmd_list(_args):
    """Tum profilleri listele."""
    current = get_current_profile()
    ram = get_ram_mb()

    print("KlipperOS-AI Profiller")
    print(f"{'='*60}")

    for name, info in PROFILES.items():
        marker = " <-- mevcut" if name == current else ""
        ram_ok = "✓" if ram >= info["min_ram_mb"] else "✗"

        print(f"\n{name}{marker}")
        print(f"  {info['description']}")
        print(f"  Min RAM: {info['min_ram_mb']} MB [{ram_ok}]")
        print(f"  Bilesenler: {', '.join(info['components'])}")


def cmd_switch(args):
    """Profil degistir."""
    target = args.profile.upper()

    if target not in PROFILES:
        print(f"Hata: Gecersiz profil '{target}'. Secenekler: {', '.join(PROFILES.keys())}")
        sys.exit(1)

    current = get_current_profile()
    if target == current:
        print(f"Zaten {target} profilinde.")
        return

    ram = get_ram_mb()
    min_ram = PROFILES[target]["min_ram_mb"]
    if ram < min_ram:
        print(f"Uyari: {target} profili icin {min_ram} MB RAM gerekli ({ram} MB mevcut).")
        answer = input("Devam etmek istiyor musunuz? [e/H] ").strip().lower()
        if answer != "e":
            print("Iptal edildi.")
            return

    print(f"Profil degistiriliyor: {current} -> {target}")

    installer = INSTALL_DIR / "scripts" / f"install-{target.lower()}.sh"
    if not installer.exists():
        print(f"Hata: Installer bulunamadi: {installer}")
        sys.exit(1)

    # Profil dosyasini guncelle
    PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_FILE.write_text(target)

    print(f"Installer calistiriliyor: {installer}")
    result = subprocess.run(["bash", str(installer)], check=False)

    if result.returncode == 0:
        print(f"\nProfil basariyla degistirildi: {target}")
    else:
        print(f"\nHata: Installer basarisiz (kod: {result.returncode})")
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(
        description="KlipperOS-AI Profil Yoneticisi",
        prog="kos_profile",
    )
    subparsers = parser.add_subparsers(dest="command", help="Komut")

    subparsers.add_parser("status", help="Mevcut profil durumu")
    subparsers.add_parser("list", help="Profilleri listele")

    switch_parser = subparsers.add_parser("switch", help="Profil degistir")
    switch_parser.add_argument("profile", help="Hedef profil (LIGHT/STANDARD/FULL)")

    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "list": cmd_list,
        "switch": cmd_switch,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
