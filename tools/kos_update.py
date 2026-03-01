#!/usr/bin/env python3
"""
KlipperOS-AI — Update Manager
================================
Sistem ve bilesen guncellemeleri.

Kullanim:
    kos_update check              # Guncellemeleri kontrol et
    kos_update system             # Sistem paketlerini guncelle
    kos_update klipper            # Klipper'i guncelle
    kos_update all                # Tum bilesenleri guncelle
    kos_update download-models    # AI modellerini indir
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

KLIPPER_HOME = Path(os.environ.get("KLIPPER_HOME", "/home/klipper"))
INSTALL_DIR = Path("/opt/klipperos-ai")
MODEL_DIR = INSTALL_DIR / "ai-monitor" / "models"

# AI model URL'leri (placeholder — gercek URL'ler projeye gore ayarlanir)
MODEL_URLS = {
    "spaghetti_detect.tflite": "https://github.com/klipperos-ai/models/releases/latest/download/spaghetti_detect.tflite",
}

REPOS = {
    "klipper": KLIPPER_HOME / "klipper",
    "moonraker": KLIPPER_HOME / "moonraker",
    "mainsail": KLIPPER_HOME / "mainsail",
    "KlipperScreen": KLIPPER_HOME / "KlipperScreen",
    "crowsnest": KLIPPER_HOME / "crowsnest",
    "klipperos-ai": INSTALL_DIR,
}


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess:
    """Komut calistir."""
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def git_check_updates(repo_path: Path) -> tuple[bool, str]:
    """Git reposunda guncelleme var mi kontrol et."""
    if not (repo_path / ".git").exists():
        return False, "Git repo degil"

    run(["git", "-C", str(repo_path), "fetch", "--quiet"])
    result = run(["git", "-C", str(repo_path), "rev-list", "--count", "HEAD..@{u}"])

    if result.returncode != 0:
        return False, "Kontrol edilemedi"

    count = result.stdout.strip()
    if count == "0":
        return False, "Guncel"
    return True, f"{count} yeni commit"


def git_update(repo_path: Path) -> bool:
    """Git reposunu guncelle."""
    if not (repo_path / ".git").exists():
        return False

    result = run(["git", "-C", str(repo_path), "pull", "--ff-only"])
    return result.returncode == 0


def cmd_check(_args):
    """Guncellemeleri kontrol et."""
    print("KlipperOS-AI Guncelleme Kontrolu")
    print(f"{'='*50}")

    for name, path in REPOS.items():
        if not path.exists():
            continue
        has_update, msg = git_check_updates(path)
        icon = "↑" if has_update else "✓"
        print(f"  {icon} {name}: {msg}")

    # Sistem paketleri
    result = run(["apt", "list", "--upgradable"])
    pkg_count = len(result.stdout.strip().split("\n")) - 1
    if pkg_count > 0:
        print(f"  ↑ Sistem: {pkg_count} paket guncellenebilir")
    else:
        print(f"  ✓ Sistem: Guncel")


def cmd_system(_args):
    """Sistem paketlerini guncelle."""
    print("Sistem paketleri guncelleniyor...")

    subprocess.run(["apt-get", "update", "-qq"], check=False)
    subprocess.run(["apt-get", "upgrade", "-y"], check=False)
    subprocess.run(["apt-get", "autoremove", "-y", "--purge"], check=False)

    print("Sistem guncellendi.")


def cmd_klipper(_args):
    """Klipper ve Moonraker'i guncelle."""
    for name in ["klipper", "moonraker"]:
        path = REPOS.get(name)
        if path and path.exists():
            print(f"{name} guncelleniyor...")
            if git_update(path):
                print(f"  ✓ {name} guncellendi")
                # Servisi yeniden baslat
                subprocess.run(["systemctl", "restart", name], check=False)
                print(f"  ✓ {name} servisi yeniden baslatildi")
            else:
                print(f"  ✗ {name} guncellenemedi")


def cmd_all(_args):
    """Tum bilesenleri guncelle."""
    print("Tum bilesenler guncelleniyor...")
    print()

    for name, path in REPOS.items():
        if not path.exists():
            continue
        print(f"{name} guncelleniyor...")
        if git_update(path):
            print(f"  ✓ {name} guncellendi")
        else:
            print(f"  - {name}: degisiklik yok veya hata")

    # Mainsail (web release)
    mainsail_dir = KLIPPER_HOME / "mainsail"
    if mainsail_dir.exists():
        print("Mainsail web UI guncelleniyor...")
        try:
            import requests
            resp = requests.get(
                "https://api.github.com/repos/mainsail-crew/mainsail/releases/latest",
                timeout=10,
            )
            release_url = None
            for asset in resp.json().get("assets", []):
                if asset["name"] == "mainsail.zip":
                    release_url = asset["browser_download_url"]
                    break

            if release_url:
                subprocess.run([
                    "wget", "-q", release_url, "-O", "/tmp/mainsail.zip",
                ], check=True)
                subprocess.run([
                    "unzip", "-qo", "/tmp/mainsail.zip", "-d", str(mainsail_dir),
                ], check=True)
                os.remove("/tmp/mainsail.zip")
                print("  ✓ Mainsail guncellendi")
        except Exception as e:
            print(f"  ✗ Mainsail guncellenemedi: {e}")

    # Servisleri yeniden baslat
    print("\nServisler yeniden baslatiliyor...")
    for svc in ["klipper", "moonraker", "nginx"]:
        subprocess.run(["systemctl", "restart", svc], check=False)
    print("✓ Guncelleme tamamlandi.")


def cmd_download_models(_args):
    """AI modellerini indir."""
    print("AI modelleri indiriliyor...")
    MODEL_DIR.mkdir(parents=True, exist_ok=True)

    for filename, url in MODEL_URLS.items():
        target = MODEL_DIR / filename
        if target.exists():
            print(f"  - {filename}: zaten mevcut (uzerine yazmak icin sil)")
            continue

        print(f"  ↓ {filename} indiriliyor...")
        result = run(["wget", "-q", url, "-O", str(target)])
        if result.returncode == 0 and target.exists() and target.stat().st_size > 0:
            size_mb = target.stat().st_size / (1024 * 1024)
            print(f"  ✓ {filename} indirildi ({size_mb:.1f} MB)")
        else:
            target.unlink(missing_ok=True)
            print(f"  ✗ {filename} indirilemedi")
            print(f"    URL: {url}")


def main():
    parser = argparse.ArgumentParser(
        description="KlipperOS-AI Guncelleme Yoneticisi",
        prog="kos_update",
    )
    subparsers = parser.add_subparsers(dest="command", help="Komut")

    subparsers.add_parser("check", help="Guncellemeleri kontrol et")
    subparsers.add_parser("system", help="Sistem paketlerini guncelle")
    subparsers.add_parser("klipper", help="Klipper/Moonraker guncelle")
    subparsers.add_parser("all", help="Tum bilesenleri guncelle")
    subparsers.add_parser("download-models", help="AI modellerini indir")

    args = parser.parse_args()

    commands = {
        "check": cmd_check,
        "system": cmd_system,
        "klipper": cmd_klipper,
        "all": cmd_all,
        "download-models": cmd_download_models,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
