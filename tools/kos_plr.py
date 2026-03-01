#!/usr/bin/env python3
"""
KlipperOS-AI — PLR (Power Loss Recovery) Manager
=================================================
Guc kesintisi kurtarma yonetimi.

Kullanim:
    kos-plr status    # PLR durumunu goster
    kos-plr resume    # Kayitli baskiyi devam ettir
    kos-plr clear     # PLR verisini temizle
    kos-plr test      # PLR kayit testini calistir
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests

VARIABLES_FILE = Path.home() / "printer_data" / "config" / "variables.cfg"
MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")


def read_plr_state() -> Optional[dict]:
    """variables.cfg dosyasindan PLR durumunu oku."""
    if not VARIABLES_FILE.exists():
        return None

    state = {}
    try:
        with open(VARIABLES_FILE) as f:
            for line in f:
                line = line.strip()
                if line.startswith("plr_") and "=" in line:
                    # Format: plr_key = value  (or plr_key: value)
                    if " = " in line:
                        key, value = line.split(" = ", 1)
                    elif ": " in line:
                        key, value = line.split(": ", 1)
                    else:
                        continue
                    key = key.strip()
                    value = value.strip()
                    # Parse value types
                    if value.lower() in ("true", "false"):
                        state[key] = value.lower() == "true"
                    else:
                        try:
                            state[key] = float(value) if "." in value else int(value)
                        except ValueError:
                            state[key] = value.strip("'\"")
    except Exception as e:
        print(f"Hata: variables.cfg okunamadi: {e}")
        return None

    return state if state else None


def moonraker_post(endpoint: str, data: Optional[dict] = None) -> bool:
    """Moonraker API'ye POST gonder."""
    try:
        url = f"{MOONRAKER_URL}{endpoint}"
        if data:
            resp = requests.post(url, json=data, timeout=10)
        else:
            resp = requests.post(url, timeout=10)
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"Moonraker hatasi: {e}")
        return False


def moonraker_gcode(gcode: str) -> bool:
    """Moonraker uzerinden G-code komutu calistir."""
    return moonraker_post(
        "/printer/gcode/script",
        {"script": gcode},
    )


def cmd_status(_args):
    """PLR durumunu goster."""
    print("PLR Durumu")
    print(f"{'='*50}")

    state = read_plr_state()
    if not state:
        print("Kayitli PLR verisi bulunamadi.")
        print(f"\nDosya: {VARIABLES_FILE}")
        return

    active = state.get("plr_active", False)
    print(f"  Durum:        {'AKTIF - Kayitli baski var!' if active else 'Pasif'}")
    print(f"  Katman:       {state.get('plr_layer', '?')}")
    print(f"  Z Yukseklik:  {state.get('plr_z_height', '?')} mm")
    print(f"  Extruder:     {state.get('plr_extruder_temp', '?')} C")
    print(f"  Bed:          {state.get('plr_bed_temp', '?')} C")
    print(f"  Fan:          {state.get('plr_fan_speed', '?')}")

    ts = state.get("plr_timestamp", 0)
    if ts and ts > 0:
        print(f"  Zaman:        {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(ts))}")

    if active:
        print(f"\nDevam ettirmek icin: kos-plr resume")
        print(f"Temizlemek icin:     kos-plr clear")


def cmd_resume(_args):
    """Kayitli baskiyi devam ettir."""
    state = read_plr_state()
    if not state or not state.get("plr_active", False):
        print("Aktif PLR verisi bulunamadi.")
        return

    print("PLR Resume")
    print(f"{'='*50}")
    print(f"  Katman:   {state.get('plr_layer', '?')}")
    print(f"  Z:        {state.get('plr_z_height', '?')} mm")
    print(f"  Extruder: {state.get('plr_extruder_temp', '?')} C")
    print(f"  Bed:      {state.get('plr_bed_temp', '?')} C")

    answer = input("\nBaskiyi devam ettirmek istiyor musunuz? [e/H] ").strip().lower()
    if answer != "e":
        print("Iptal edildi.")
        return

    print("\nKOS_PLR_RESUME komutu gonderiliyor...")
    if moonraker_gcode("KOS_PLR_RESUME"):
        print("PLR resume komutu gonderildi.")
        print("  Yazici isitiyor ve konumlanacak.")
        print("  Hazir oldugunda RESUME ile devam edin.")
    else:
        print("Hata: PLR resume komutu gonderilemedi.")


def cmd_clear(_args):
    """PLR verisini temizle."""
    print("PLR verileri temizleniyor...")
    if moonraker_gcode("KOS_PLR_CLEAR"):
        print("PLR verileri temizlendi.")
    else:
        print("Hata: PLR temizleme komutu gonderilemedi.")


def cmd_test(_args):
    """PLR kayit testini calistir."""
    print("PLR Kayit Testi")
    print(f"{'='*50}")
    print("Test PLR state kaydediliyor (Layer=50, Z=10.0)...")

    if moonraker_gcode("_KOS_SAVE_PLR_STATE HEIGHT=10.0 LAYER=50"):
        print("Kayit komutu gonderildi.")
        time.sleep(2)  # Dosyanin yazilmasini bekle

        state = read_plr_state()
        if state and state.get("plr_active"):
            print("PLR verisi dogrulandi:")
            print(f"  plr_active:   {state.get('plr_active')}")
            print(f"  plr_layer:    {state.get('plr_layer')}")
            print(f"  plr_z_height: {state.get('plr_z_height')}")
        else:
            print("Uyari: PLR verisi okunamadi veya aktif degil.")
            print(f"  Dosya: {VARIABLES_FILE}")
    else:
        print("Hata: Test komutu gonderilemedi.")

    # Temizle
    moonraker_gcode("KOS_PLR_CLEAR")
    print("\nTest tamamlandi. PLR verisi temizlendi.")


def main():
    parser = argparse.ArgumentParser(
        description="KlipperOS-AI PLR (Power Loss Recovery) Yoneticisi",
        prog="kos-plr",
    )
    subparsers = parser.add_subparsers(dest="command", help="Komut")

    subparsers.add_parser("status", help="PLR durumunu goster")
    subparsers.add_parser("resume", help="Kayitli baskiyi devam ettir")
    subparsers.add_parser("clear", help="PLR verisini temizle")
    subparsers.add_parser("test", help="PLR kayit testini calistir")

    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "resume": cmd_resume,
        "clear": cmd_clear,
        "test": cmd_test,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
