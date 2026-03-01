#!/usr/bin/env python3
"""
KlipperOS-AI — MCU Manager
============================
MCU (mikrodenetleyici) yonetimi: tarama, firmware build/flash.

Kullanim:
    kos_mcu scan                  # MCU kartlarini tara
    kos_mcu info                  # Bagli MCU bilgisi
    kos_mcu flash [--board TYPE]  # Klipper firmware flash
"""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

KLIPPER_HOME = Path(os.environ.get("KLIPPER_HOME", "/home/klipper"))
KLIPPER_DIR = KLIPPER_HOME / "klipper"
MCU_DETECT_SCRIPT = Path("/opt/klipperos-ai/scripts/mcu-detect.sh")

# Bilinen kart turleri ve menuconfig ayarlari
BOARD_CONFIGS = {
    "creality": {
        "description": "Creality 4.2.x (STM32F103)",
        "mcu": "stm32f103xe",
        "bootloader": "28KiB",
        "comm": "serial",
    },
    "btt-skr-mini": {
        "description": "BTT SKR Mini E3 V2/V3 (STM32G0B1)",
        "mcu": "stm32g0b1xx",
        "bootloader": "8KiB",
        "comm": "serial",
    },
    "btt-octopus": {
        "description": "BTT Octopus (STM32F446)",
        "mcu": "stm32f446xx",
        "bootloader": "32KiB",
        "comm": "serial",
    },
    "rp2040": {
        "description": "RP2040 (SKR Pico, Pico)",
        "mcu": "rp2040",
        "bootloader": "none",
        "comm": "usb",
    },
    "atmega2560": {
        "description": "Arduino Mega 2560 (ATmega2560)",
        "mcu": "atmega2560",
        "bootloader": "none",
        "comm": "serial",
    },
}


def run(cmd: list[str], cwd: str = None, **kwargs) -> subprocess.CompletedProcess:
    """Komut calistir."""
    return subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, **kwargs)


def find_serial_ports() -> list[dict]:
    """Bagli seri portlari bul."""
    ports = []

    # /dev/serial/by-id tercih edilir
    serial_dir = Path("/dev/serial/by-id")
    if serial_dir.exists():
        for dev in serial_dir.iterdir():
            if dev.is_symlink():
                real = dev.resolve()
                ports.append({
                    "path": str(dev),
                    "device": str(real),
                    "name": dev.name,
                })

    # ttyUSB ve ttyACM
    for prefix in ["/dev/ttyUSB", "/dev/ttyACM"]:
        for i in range(10):
            path = f"{prefix}{i}"
            if os.path.exists(path):
                # Zaten by-id'de varsa ekleme
                if not any(p["device"] == path for p in ports):
                    ports.append({
                        "path": path,
                        "device": path,
                        "name": os.path.basename(path),
                    })

    return ports


def cmd_scan(_args):
    """MCU kartlarini tara."""
    print("MCU Taramasi")
    print(f"{'='*50}")

    # mcu-detect.sh varsa kullan
    if MCU_DETECT_SCRIPT.exists():
        subprocess.run(["bash", str(MCU_DETECT_SCRIPT)], check=False)
        return

    # Fallback: kendi tarama
    ports = find_serial_ports()

    if not ports:
        print("Bagli seri cihaz bulunamadi.")
        print("\nYazici kartinizi USB ile baglayip tekrar deneyin.")
        return

    print(f"\n{len(ports)} seri cihaz bulundu:\n")
    for port in ports:
        print(f"  {port['name']}")
        print(f"    Yol:    {port['path']}")
        print(f"    Cihaz:  {port['device']}")
        print()

    # Klipper config onerisi
    print("Klipper printer.cfg icin onerilen:")
    best = ports[0]
    if any("/dev/serial/by-id/" in p["path"] for p in ports):
        best = next(p for p in ports if "/dev/serial/by-id/" in p["path"])
    print(f"  [mcu]")
    print(f"  serial: {best['path']}")


def cmd_info(_args):
    """Klipper MCU bilgisi."""
    print("MCU Bilgisi")
    print(f"{'='*50}")

    # Klipper loglarindan MCU bilgisi
    log_file = KLIPPER_HOME / "printer_data" / "logs" / "klippy.log"
    if log_file.exists():
        try:
            with open(log_file) as f:
                lines = f.readlines()

            for line in reversed(lines):
                if "MCU" in line and ("version" in line.lower() or "build" in line.lower()):
                    print(f"  {line.strip()}")
                    break

            for line in reversed(lines):
                if "mcu" in line.lower() and "serial" in line.lower():
                    print(f"  {line.strip()}")
                    break
        except Exception as e:
            print(f"Log okunamadi: {e}")
    else:
        print("Klipper logu bulunamadi.")

    # Bagli portlar
    ports = find_serial_ports()
    if ports:
        print(f"\nBagli seri portlar: {len(ports)}")
        for port in ports:
            print(f"  {port['path']}")


def cmd_flash(args):
    """Klipper firmware build ve flash."""
    board = args.board

    if not KLIPPER_DIR.exists():
        print(f"Hata: Klipper dizini bulunamadi: {KLIPPER_DIR}")
        sys.exit(1)

    if board and board not in BOARD_CONFIGS:
        print(f"Hata: Bilinmeyen kart tipi '{board}'.")
        print(f"Bilinen kartlar: {', '.join(BOARD_CONFIGS.keys())}")
        sys.exit(1)

    if board:
        config = BOARD_CONFIGS[board]
        print(f"Kart: {config['description']}")
        print(f"MCU:  {config['mcu']}")
    else:
        print("Kart tipi belirtilmedi. 'make menuconfig' ile ayarlayin.")

    # Seri port sec
    ports = find_serial_ports()
    flash_device = None

    if ports:
        print(f"\nBagli cihazlar:")
        for i, port in enumerate(ports):
            print(f"  {i+1}) {port['path']}")

        if len(ports) == 1:
            flash_device = ports[0]["path"]
            print(f"\nFlash cihazi: {flash_device}")
        else:
            choice = input(f"Flash cihazi secin [1-{len(ports)}]: ").strip()
            try:
                idx = int(choice) - 1
                flash_device = ports[idx]["path"]
            except (ValueError, IndexError):
                print("Gecersiz secim.")
                sys.exit(1)
    else:
        print("Uyari: Bagli cihaz bulunamadi.")

    # Onay
    answer = input("\nFirmware build ve flash yapilacak. Devam? [e/H] ").strip().lower()
    if answer != "e":
        print("Iptal edildi.")
        return

    # Build
    print("\nFirmware build ediliyor...")
    build_result = run(["make", "clean"], cwd=str(KLIPPER_DIR))
    build_result = run(["make", f"-j{os.cpu_count() or 2}"], cwd=str(KLIPPER_DIR))

    if build_result.returncode != 0:
        print(f"Hata: Build basarisiz.")
        print(build_result.stderr)
        sys.exit(1)

    print("✓ Build tamamlandi.")

    # Flash
    if flash_device:
        print(f"\nFlash yapiliyor: {flash_device}")

        flash_cmd = ["make", "flash", f"FLASH_DEVICE={flash_device}"]
        flash_result = run(flash_cmd, cwd=str(KLIPPER_DIR))

        if flash_result.returncode == 0:
            print("✓ Flash tamamlandi.")
            print("  Klipper'i yeniden baslatin: sudo systemctl restart klipper")
        else:
            print(f"Hata: Flash basarisiz.")
            print(flash_result.stderr)
            print("\nManuel flash icin:")
            print(f"  cd {KLIPPER_DIR}")
            print(f"  make flash FLASH_DEVICE={flash_device}")
    else:
        print("\nFlash cihazi bulunamadi. Manuel flash yapin:")
        print(f"  cd {KLIPPER_DIR}")
        print(f"  make flash FLASH_DEVICE=/dev/ttyACM0")


def main():
    parser = argparse.ArgumentParser(
        description="KlipperOS-AI MCU Yoneticisi",
        prog="kos_mcu",
    )
    subparsers = parser.add_subparsers(dest="command", help="Komut")

    subparsers.add_parser("scan", help="MCU kartlarini tara")
    subparsers.add_parser("info", help="MCU bilgisi")

    flash_parser = subparsers.add_parser("flash", help="Klipper firmware flash")
    flash_parser.add_argument(
        "--board", "-b",
        choices=list(BOARD_CONFIGS.keys()),
        help="Kart tipi",
    )

    args = parser.parse_args()

    commands = {
        "scan": cmd_scan,
        "info": cmd_info,
        "flash": cmd_flash,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
