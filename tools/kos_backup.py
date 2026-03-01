#!/usr/bin/env python3
"""
KlipperOS-AI — Config Backup/Restore Manager
==============================================
Klipper yapilandirma dosyalarini yedekle ve geri yukle.

Kullanim:
    kos_backup create [isim]           # Yedek olustur
    kos_backup restore <yedek_adi>     # Yedekten geri yukle
    kos_backup list                    # Yedekleri listele
    kos_backup delete <yedek_adi>      # Yedek sil
"""

import argparse
import os
import shutil
import sys
import tarfile
from datetime import datetime
from pathlib import Path

KLIPPER_HOME = Path(os.environ.get("KLIPPER_HOME", "/home/klipper"))
BACKUP_DIR = Path("/var/backups/klipperos-ai")
MAX_BACKUPS = 10

# Yedeklenecek dizinler
BACKUP_SOURCES = [
    KLIPPER_HOME / "printer_data" / "config",
    KLIPPER_HOME / "printer_data" / "database",
    Path("/etc/klipperos-ai"),
]

# Ek dosyalar
BACKUP_FILES = [
    KLIPPER_HOME / "printer_data" / "config" / "printer.cfg",
    KLIPPER_HOME / "printer_data" / "config" / "moonraker.conf",
    KLIPPER_HOME / "printer_data" / "config" / "KlipperScreen.conf",
    KLIPPER_HOME / "printer_data" / "config" / "crowsnest.conf",
]


def cmd_create(args):
    """Yedek olustur."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)

    name = args.name or datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"klipperos-backup-{name}.tar.gz"

    if backup_file.exists():
        print(f"Hata: Yedek zaten mevcut: {backup_file.name}")
        sys.exit(1)

    print(f"Yedek olusturuluyor: {backup_file.name}")

    with tarfile.open(str(backup_file), "w:gz") as tar:
        files_added = 0

        # Dizinleri ekle
        for source_dir in BACKUP_SOURCES:
            if source_dir.exists():
                tar.add(str(source_dir), arcname=str(source_dir.relative_to("/")))
                count = sum(1 for _ in source_dir.rglob("*") if _.is_file())
                print(f"  + {source_dir}: {count} dosya")
                files_added += count

        if files_added == 0:
            print("Uyari: Yedeklenecek dosya bulunamadi.")
            backup_file.unlink(missing_ok=True)
            return

    size_kb = backup_file.stat().st_size // 1024
    print(f"\n✓ Yedek olusturuldu: {backup_file.name} ({size_kb} KB, {files_added} dosya)")

    # Eski yedekleri temizle
    _cleanup_old_backups()


def cmd_restore(args):
    """Yedekten geri yukle."""
    backup_name = args.backup_name

    # Tam yol veya isim ile bul
    backup_file = BACKUP_DIR / backup_name
    if not backup_file.exists():
        backup_file = BACKUP_DIR / f"klipperos-backup-{backup_name}.tar.gz"
    if not backup_file.exists():
        # Parcali arama
        matches = list(BACKUP_DIR.glob(f"*{backup_name}*"))
        if len(matches) == 1:
            backup_file = matches[0]
        elif len(matches) > 1:
            print(f"Birden fazla eslesme: {[m.name for m in matches]}")
            sys.exit(1)
        else:
            print(f"Hata: Yedek bulunamadi: {backup_name}")
            sys.exit(1)

    print(f"Geri yukleniyor: {backup_file.name}")

    # Onay
    answer = input("Mevcut yapilandirma uzerine yazilacak. Devam? [e/H] ").strip().lower()
    if answer != "e":
        print("Iptal edildi.")
        return

    # Mevcut config'i yedekle
    auto_backup = BACKUP_DIR / f"klipperos-backup-pre-restore-{datetime.now():%Y%m%d_%H%M%S}.tar.gz"
    print(f"Mevcut config yedekleniyor: {auto_backup.name}")
    with tarfile.open(str(auto_backup), "w:gz") as tar:
        for source_dir in BACKUP_SOURCES:
            if source_dir.exists():
                tar.add(str(source_dir), arcname=str(source_dir.relative_to("/")))

    # Geri yukle
    with tarfile.open(str(backup_file), "r:gz") as tar:
        tar.extractall(path="/")

    print(f"✓ Geri yukleme tamamlandi: {backup_file.name}")
    print("  Servisleri yeniden baslatin: sudo systemctl restart klipper moonraker")


def cmd_list(_args):
    """Yedekleri listele."""
    if not BACKUP_DIR.exists():
        print("Hicbir yedek bulunamadi.")
        return

    backups = sorted(BACKUP_DIR.glob("klipperos-backup-*.tar.gz"), reverse=True)

    if not backups:
        print("Hicbir yedek bulunamadi.")
        return

    print("KlipperOS-AI Yedekleri")
    print(f"{'='*60}")
    print(f"{'Isim':<40} {'Boyut':>8} {'Tarih':>12}")
    print(f"{'-'*60}")

    for backup in backups:
        name = backup.name.replace("klipperos-backup-", "").replace(".tar.gz", "")
        size_kb = backup.stat().st_size // 1024
        mtime = datetime.fromtimestamp(backup.stat().st_mtime).strftime("%Y-%m-%d")
        print(f"  {name:<38} {size_kb:>6} KB {mtime:>12}")

    print(f"\nToplam: {len(backups)} yedek")
    print(f"Dizin:  {BACKUP_DIR}")


def cmd_delete(args):
    """Yedek sil."""
    backup_name = args.backup_name
    backup_file = BACKUP_DIR / backup_name
    if not backup_file.exists():
        backup_file = BACKUP_DIR / f"klipperos-backup-{backup_name}.tar.gz"

    if not backup_file.exists():
        print(f"Hata: Yedek bulunamadi: {backup_name}")
        sys.exit(1)

    answer = input(f"Silinecek: {backup_file.name}. Emin misiniz? [e/H] ").strip().lower()
    if answer != "e":
        print("Iptal edildi.")
        return

    backup_file.unlink()
    print(f"✓ Silindi: {backup_file.name}")


def _cleanup_old_backups():
    """Eski yedekleri temizle (MAX_BACKUPS'dan fazlaysa)."""
    backups = sorted(BACKUP_DIR.glob("klipperos-backup-*.tar.gz"))
    # pre-restore yedeklerini sayma
    regular = [b for b in backups if "pre-restore" not in b.name]

    while len(regular) > MAX_BACKUPS:
        oldest = regular.pop(0)
        oldest.unlink()
        print(f"  Eski yedek silindi: {oldest.name}")


def main():
    parser = argparse.ArgumentParser(
        description="KlipperOS-AI Yedekleme Yoneticisi",
        prog="kos_backup",
    )
    subparsers = parser.add_subparsers(dest="command", help="Komut")

    create_parser = subparsers.add_parser("create", help="Yedek olustur")
    create_parser.add_argument("name", nargs="?", default=None, help="Yedek adi (opsiyonel)")

    restore_parser = subparsers.add_parser("restore", help="Yedekten geri yukle")
    restore_parser.add_argument("backup_name", help="Yedek adi veya dosya adi")

    subparsers.add_parser("list", help="Yedekleri listele")

    delete_parser = subparsers.add_parser("delete", help="Yedek sil")
    delete_parser.add_argument("backup_name", help="Silinecek yedek adi")

    args = parser.parse_args()

    commands = {
        "create": cmd_create,
        "restore": cmd_restore,
        "list": cmd_list,
        "delete": cmd_delete,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
