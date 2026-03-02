#!/usr/bin/env python3
"""
KlipperOS-AI — System Recovery
================================
Yazici yapilandirma yedekleme, geri yukleme ve onarim araci.
Snapshot/restore, emergency repair mode.

Kullanim:
    kos-recovery snapshot           # Yapilandirma snapshot'i olustur
    kos-recovery restore <dosya>    # Snapshot'tan geri yukle
    kos-recovery repair             # Sistem sorunlarini onar
    kos-recovery reset-ai           # AI bilesenlerini sifirla
    kos-recovery list               # Mevcut snapshotlari listele
"""

import argparse
import glob
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
from datetime import datetime
from pathlib import Path

# --- Constants ---

KOS_CONFIG_DIR = "/etc/klipperos-ai"
KLIPPER_HOME = Path(os.environ.get("KLIPPER_HOME", "/home/klipper"))
PRINTER_DATA = KLIPPER_HOME / "printer_data"
SNAPSHOT_DIR = "/var/backups/klipperos-ai/snapshots"
MAX_SNAPSHOTS = 5
MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")

# Snapshot'a dahil edilecek dosya kaliplari
SNAPSHOT_PATHS = [
    f"{KOS_CONFIG_DIR}/*.yml",
    f"{KOS_CONFIG_DIR}/*.json",
    f"{KOS_CONFIG_DIR}/profile",
    str(PRINTER_DATA / "config" / "*.cfg"),
    str(PRINTER_DATA / "config" / "*.conf"),
    str(PRINTER_DATA / "database" / "*"),
]

# Geri yukleme icin izin verilen prefiksler (path traversal korunmasi)
_ALLOWED_RESTORE_PREFIXES = (
    "home/klipper/printer_data/",
    "etc/klipperos-ai/",
)

# KlipperOS servisleri
KOS_SERVICES = [
    "klipper.service",
    "moonraker.service",
    "klipperos-ai-monitor.service",
    "KlipperScreen.service",
    "crowsnest.service",
    "ollama.service",
]

# Varsayilan yapilandirma (reset-ai icin)
DEFAULT_PROFILE_YML = {
    "profile": "STANDARD",
    "auto_optimize": True,
    "polling_interval": 10,
    "log_level": "info",
}

DEFAULT_MONITOR_CONFIG = {
    "check_interval": 10,
    "flowguard_enabled": True,
    "spaghetti_detection": True,
    "auto_pause": True,
}


# --- Helpers ---

def require_root():
    if os.geteuid() != 0:
        print("Hata: Bu islem root yetkisi gerektirir.")
        print("  sudo kos-recovery ... seklinde calistirin.")
        sys.exit(1)


def run_cmd(cmd, timeout=60):
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        print(f"Uyari: Komut zaman asimina ugradi: {' '.join(cmd)}")
        return None
    except FileNotFoundError:
        print(f"Hata: Komut bulunamadi: {cmd[0]}")
        return None


def run_systemctl(action, service):
    try:
        result = subprocess.run(
            ["systemctl", action, service],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _safe_extractall(tar, dest):
    """CVE-2007-4559 korumali tarfile extract (kos_backup.py deseni)."""
    dest_path = Path(dest).resolve()
    for member in tar.getmembers():
        member_path = (dest_path / member.name).resolve()
        if not str(member_path).startswith(str(dest_path)):
            raise tarfile.TarError(
                f"Guvenlik hatasi: yol traversal tespit edildi: {member.name}"
            )
        if not any(member.name.startswith(p) for p in _ALLOWED_RESTORE_PREFIXES):
            # Meta dosyalarina izin ver
            if member.name not in ("snapshot-meta.json", "package-selections.txt",
                                   "enabled-services.txt"):
                raise tarfile.TarError(
                    f"Guvenlik hatasi: izin verilmeyen yol: {member.name}"
                )
    tar.extractall(path=dest, filter="data")


# --- Snapshot ---

def ensure_snapshot_dir():
    os.makedirs(SNAPSHOT_DIR, mode=0o750, exist_ok=True)


def rotate_snapshots():
    snapshots = sorted(glob.glob(os.path.join(SNAPSHOT_DIR, "snapshot-*.tar.gz")))
    while len(snapshots) >= MAX_SNAPSHOTS:
        oldest = snapshots.pop(0)
        try:
            os.remove(oldest)
            print(f"  Eski snapshot silindi: {os.path.basename(oldest)}")
        except OSError as e:
            print(f"  Uyari: Silinemedi {oldest}: {e}")


def collect_snapshot_files():
    files = []
    for pattern in SNAPSHOT_PATHS:
        files.extend(glob.glob(pattern))
    return [f for f in files if os.path.isfile(f)]


def cmd_snapshot(_args):
    """Yazici yapilandirma snapshot'i olustur."""
    require_root()
    ensure_snapshot_dir()
    rotate_snapshots()

    timestamp = datetime.now().strftime("%Y-%m-%d-%H%M%S")
    snapshot_name = f"snapshot-{timestamp}.tar.gz"
    snapshot_path = os.path.join(SNAPSHOT_DIR, snapshot_name)

    print(f"Snapshot olusturuluyor: {snapshot_name}")

    with tempfile.TemporaryDirectory(prefix="kos-recovery-") as tmpdir:
        meta = {"timestamp": timestamp, "version": "2.0", "files": []}

        config_files = collect_snapshot_files()
        for filepath in config_files:
            rel = filepath.lstrip("/")
            dest = os.path.join(tmpdir, rel)
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            shutil.copy2(filepath, dest)
            meta["files"].append(rel)
            print(f"  [+] {filepath}")

        # Paket listesi
        print("  [+] Paket listesi kaydediliyor ...")
        result = run_cmd(["dpkg", "--get-selections"], timeout=30)
        if result and result.returncode == 0:
            pkg_path = os.path.join(tmpdir, "package-selections.txt")
            with open(pkg_path, "w") as f:
                f.write(result.stdout)
            meta["files"].append("package-selections.txt")

        # Etkin servis listesi
        print("  [+] Servis durumu kaydediliyor ...")
        result = run_cmd(
            ["systemctl", "list-unit-files", "--state=enabled",
             "--no-pager", "--no-legend"], timeout=15,
        )
        if result and result.returncode == 0:
            svc_path = os.path.join(tmpdir, "enabled-services.txt")
            with open(svc_path, "w") as f:
                f.write(result.stdout)
            meta["files"].append("enabled-services.txt")

        # Meta
        meta_path = os.path.join(tmpdir, "snapshot-meta.json")
        with open(meta_path, "w") as f:
            json.dump(meta, f, indent=2)

        # Tarball
        with tarfile.open(snapshot_path, "w:gz") as tar:
            for item in os.listdir(tmpdir):
                tar.add(os.path.join(tmpdir, item), arcname=item)

    size_kb = os.path.getsize(snapshot_path) // 1024
    print(f"\nSnapshot olusturuldu: {snapshot_path}")
    print(f"  Boyut: {size_kb} KB | Dosya: {len(meta['files'])} adet")


def cmd_restore(args):
    """Snapshot'tan geri yukle."""
    require_root()

    snapshot_path = args.snapshot
    if not os.path.isabs(snapshot_path):
        candidate = os.path.join(SNAPSHOT_DIR, snapshot_path)
        if os.path.exists(candidate):
            snapshot_path = candidate

    if not os.path.isfile(snapshot_path):
        print(f"Hata: Snapshot bulunamadi: {snapshot_path}")
        sys.exit(1)

    print(f"Geri yukleniyor: {os.path.basename(snapshot_path)}")

    with tempfile.TemporaryDirectory(prefix="kos-restore-") as tmpdir:
        try:
            with tarfile.open(snapshot_path, "r:gz") as tar:
                _safe_extractall(tar, tmpdir)
        except (tarfile.TarError, OSError) as e:
            print(f"Hata: Arsiv acilamadi: {e}")
            sys.exit(1)

        # Meta oku
        meta_path = os.path.join(tmpdir, "snapshot-meta.json")
        meta = {}
        if os.path.exists(meta_path):
            with open(meta_path) as f:
                meta = json.load(f)
            print(f"  Snapshot tarihi: {meta.get('timestamp', 'bilinmiyor')}")

        # Config dosyalarini geri yukle
        restored = 0
        for rel_path in meta.get("files", []):
            src = os.path.join(tmpdir, rel_path)
            if not os.path.isfile(src):
                continue
            if rel_path in ("package-selections.txt", "enabled-services.txt",
                            "snapshot-meta.json"):
                continue

            dest = os.path.join("/", rel_path)
            dest_dir = os.path.dirname(dest)
            if not os.path.isdir(dest_dir):
                os.makedirs(dest_dir, mode=0o755, exist_ok=True)

            if os.path.exists(dest):
                with open(src) as a, open(dest) as b:
                    if a.read() == b.read():
                        continue

            shutil.copy2(src, dest)
            print(f"  [*] Geri yuklendi: {dest}")
            restored += 1

        print(f"\nGeri yukleme tamamlandi: {restored} dosya guncellendi.")


# --- Repair ---

def cmd_repair(_args):
    """Sistem sorunlarini onar (kirik paketler, izinler, servisler)."""
    require_root()

    print("Sistem onarimi baslatiliyor ...\n")
    issues_fixed = 0

    # 1. Kirik paketler
    print("[1/5] Kirik paketler kontrol ediliyor ...")
    result = run_cmd(["dpkg", "--configure", "-a"], timeout=120)
    if result and result.returncode == 0:
        print("  dpkg --configure -a: Tamam")
    result = run_cmd(["apt-get", "install", "-f", "-y"], timeout=180)
    if result and result.returncode == 0:
        print("  apt-get install -f: Tamam")
        issues_fixed += 1

    # 2. Dizin izinleri
    print("\n[2/5] Dizin izinleri kontrol ediliyor ...")
    for check_dir in [KOS_CONFIG_DIR, str(PRINTER_DATA / "config"),
                      str(PRINTER_DATA / "logs")]:
        if os.path.isdir(check_dir):
            try:
                os.chmod(check_dir, 0o755)
                print(f"  {check_dir} izinleri duzeltildi.")
                issues_fixed += 1
            except OSError as e:
                print(f"  Uyari: {check_dir} izin ayarlanamadi: {e}")
        else:
            os.makedirs(check_dir, mode=0o755, exist_ok=True)
            print(f"  {check_dir} olusturuldu.")
            issues_fixed += 1

    # 3. Basarisiz servisleri yeniden baslat
    print("\n[3/5] KlipperOS servisleri kontrol ediliyor ...")
    for svc in KOS_SERVICES:
        result = run_cmd(["systemctl", "is-failed", svc], timeout=10)
        if result and result.stdout.strip() == "failed":
            print(f"  {svc}: basarisiz durumda, yeniden baslatiliyor ...")
            run_systemctl("restart", svc)
            if run_systemctl("is-active", svc):
                print(f"  {svc}: basariyla yeniden baslatildi.")
                issues_fixed += 1
            else:
                print(f"  Uyari: {svc} yeniden baslatma basarisiz.")
        elif result and result.stdout.strip() == "active":
            print(f"  {svc}: calisiyor.")
        else:
            print(f"  {svc}: yuklu degil veya devre disi.")

    # 4. systemd daemon-reload
    print("\n[4/5] systemd daemon-reload calistiriliyor ...")
    result = run_cmd(["systemctl", "daemon-reload"], timeout=30)
    if result and result.returncode == 0:
        print("  daemon-reload: Tamam")
        issues_fixed += 1

    # 5. Moonraker erisim dogrulamasi
    print("\n[5/5] Moonraker erisimi kontrol ediliyor ...")
    try:
        import requests
        resp = requests.get(f"{MOONRAKER_URL}/server/info", timeout=5)
        if resp.status_code == 200:
            info = resp.json().get("result", {})
            print(f"  Moonraker: {info.get('state', 'bilinmiyor')}")
            print(f"  Klipper:   {info.get('klipper_state', 'bilinmiyor')}")
            issues_fixed += 1
        else:
            print(f"  Uyari: Moonraker HTTP {resp.status_code}")
    except Exception:
        print(f"  Uyari: Moonraker erisilemedi ({MOONRAKER_URL})")

    print(f"\nOnarim tamamlandi: {issues_fixed} sorun giderildi.")


# --- Reset AI ---

def cmd_reset_ai(_args):
    """AI bilesenlerini varsayilana sifirla."""
    require_root()

    print("AI bilesenleri sifirlanacak!")
    print("  - Ollama modelleri silinecek")
    print("  - AI yapilandirma dosyalari varsayilana donecek")
    print("  - AI servisleri yeniden baslatilacak\n")

    try:
        confirm = input("Devam etmek istiyor musunuz? [e/H]: ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        confirm = ""

    if confirm not in ("e", "evet"):
        print("Islem iptal edildi.")
        return

    print()

    # 1. Ollama modellerini sil
    print("[1/3] Ollama modelleri kaldiriliyor ...")
    result = run_cmd(["ollama", "list"], timeout=15)
    if result and result.returncode == 0 and result.stdout.strip():
        lines = result.stdout.strip().split("\n")
        for line in lines[1:]:
            parts = line.split()
            if parts:
                model_name = parts[0]
                print(f"  Siliniyor: {model_name} ...")
                run_cmd(["ollama", "rm", model_name], timeout=30)
        print("  Ollama modelleri kaldirildi.")
    else:
        print("  Ollama yuklu degil veya model bulunamadi.")

    # 2. Config sifirla
    print("\n[2/3] Yapilandirma dosyalari sifirlaniyor ...")
    try:
        import yaml
        yaml_dump = yaml.dump
    except ImportError:
        def yaml_dump(data, stream=None, **_kwargs):
            content = json.dumps(data, indent=2)
            if stream:
                stream.write(content)
            return content

    profile_path = os.path.join(KOS_CONFIG_DIR, "profile.yml")
    try:
        os.makedirs(KOS_CONFIG_DIR, mode=0o755, exist_ok=True)
        with open(profile_path, "w") as f:
            yaml_dump(DEFAULT_PROFILE_YML, f, default_flow_style=False)
        print(f"  [*] {profile_path} sifirlandi.")
    except OSError as e:
        print(f"  Uyari: {profile_path} yazilamadi: {e}")

    monitor_path = os.path.join(KOS_CONFIG_DIR, "monitor-config.yml")
    try:
        with open(monitor_path, "w") as f:
            yaml_dump(DEFAULT_MONITOR_CONFIG, f, default_flow_style=False)
        print(f"  [*] {monitor_path} sifirlandi.")
    except OSError as e:
        print(f"  Uyari: {monitor_path} yazilamadi: {e}")

    # 3. AI servisleri yeniden baslat
    print("\n[3/3] AI servisleri yeniden baslatiliyor ...")
    ai_services = ["klipperos-ai-monitor.service", "ollama.service"]
    for svc in ai_services:
        result = run_cmd(["systemctl", "is-enabled", svc], timeout=10)
        if result and result.returncode == 0:
            run_systemctl("restart", svc)
            if run_systemctl("is-active", svc):
                print(f"  {svc}: yeniden baslatildi.")
            else:
                print(f"  Uyari: {svc} baslatilamadi.")
        else:
            print(f"  {svc}: etkin degil, atlaniyor.")

    print("\nAI bilesenleri sifirlandi.")


# --- List ---

def cmd_list(_args):
    if not os.path.isdir(SNAPSHOT_DIR):
        print(f"Snapshot dizini bulunamadi: {SNAPSHOT_DIR}")
        return

    snapshots = sorted(glob.glob(os.path.join(SNAPSHOT_DIR, "snapshot-*.tar.gz")))
    if not snapshots:
        print("Kayitli snapshot bulunamadi.")
        return

    print(f"Mevcut snapshotlar ({len(snapshots)}/{MAX_SNAPSHOTS}):\n")
    for i, snap in enumerate(snapshots, 1):
        name = os.path.basename(snap)
        size_kb = os.path.getsize(snap) // 1024
        mtime = datetime.fromtimestamp(os.path.getmtime(snap))
        date_str = mtime.strftime("%Y-%m-%d %H:%M:%S")
        print(f"  {i}. {name}")
        print(f"     Tarih: {date_str} | Boyut: {size_kb} KB")

    print("\nGeri yuklemek icin: kos-recovery restore <snapshot-dosyasi>")


# --- CLI ---

def main():
    parser = argparse.ArgumentParser(
        prog="kos-recovery",
        description="KlipperOS-AI System Recovery — Yedekleme, geri yukleme ve onarim",
    )
    sub = parser.add_subparsers(dest="command", help="Komut")

    sub.add_parser("snapshot", help="Yapilandirma snapshot'i olustur")
    restore_p = sub.add_parser("restore", help="Snapshot'tan geri yukle")
    restore_p.add_argument("snapshot", help="Snapshot dosya yolu veya adi")
    sub.add_parser("repair", help="Sistem sorunlarini onar")
    sub.add_parser("reset-ai", help="AI bilesenlerini varsayilana sifirla")
    sub.add_parser("list", help="Mevcut snapshotlari listele")

    args = parser.parse_args()

    if args.command == "snapshot":
        cmd_snapshot(args)
    elif args.command == "restore":
        cmd_restore(args)
    elif args.command == "repair":
        cmd_repair(args)
    elif args.command == "reset-ai":
        cmd_reset_ai(args)
    elif args.command == "list":
        cmd_list(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
