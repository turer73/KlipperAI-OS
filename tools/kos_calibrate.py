#!/usr/bin/env python3
"""
KlipperOS-AI — TMC Flow Calibration Tool
==========================================
TMC2209 StallGuard ile akis kalibrasyonu.

Kullanim:
    kos-calibrate flow-status    # Kalibrasyon durumu
    kos-calibrate flow-test      # Yeni kalibrasyon testi
    kos-calibrate flow-reset     # Kalibrasyon verisini sil
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Optional

import requests

CALIBRATION_FILE = Path.home() / "printer_data" / "config" / "kos_calibration.json"
MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")


def load_calibration() -> dict:
    """Kalibrasyon JSON dosyasini oku. Dosya yoksa bos dict dondur."""
    if not CALIBRATION_FILE.exists():
        return {}
    try:
        with open(CALIBRATION_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        print(f"Uyari: Kalibrasyon dosyasi okunamadi: {e}")
        return {}


def save_calibration(data: dict) -> None:
    """Kalibrasyon verisini JSON dosyasina yaz."""
    try:
        CALIBRATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CALIBRATION_FILE, "w") as f:
            json.dump(data, f, indent=2)
    except OSError as e:
        print(f"Hata: Kalibrasyon dosyasi yazilamadi: {e}")


def get_tmc_sg_result() -> Optional[int]:
    """Moonraker uzerinden TMC2209 extruder StallGuard degerini sorgula.

    /printer/objects/query?tmc2209 extruder endpoint'inden
    drv_status.sg_result degerini dondurur.
    TMC yapilandirilmamissa veya sorgu basarisiz olursa None dondurur.
    """
    try:
        url = f"{MOONRAKER_URL}/printer/objects/query"
        params = {"tmc2209 extruder": "drv_status"}
        resp = requests.get(url, params=params, timeout=5)
        resp.raise_for_status()
        data = resp.json()
        # Yanit yapisi: {"result": {"status": {"tmc2209 extruder": {"drv_status": {"sg_result": N}}}}}
        tmc_status = data["result"]["status"]["tmc2209 extruder"]
        sg_result = tmc_status["drv_status"]["sg_result"]
        return int(sg_result)
    except (requests.RequestException, KeyError, TypeError, ValueError):
        return None


def cmd_flow_status(_args):
    """Kalibrasyon durumunu goster."""
    print("TMC Akis Kalibrasyon Durumu")
    print(f"{'=' * 50}")

    data = load_calibration()
    if not data:
        print("Kalibrasyon verisi bulunamadi.")
        print(f"\nDosya: {CALIBRATION_FILE}")
        print("Yeni kalibrasyon icin: kos-calibrate flow-test")
        return

    print(f"\n{'Filament/Sicaklik':<20} {'Baseline SG':>12} {'Onerilen Akis':>15}")
    print(f"{'-' * 50}")

    for key, entry in data.items():
        baseline = entry.get("baseline_sg", 0)
        # Basit akis orani onerisi: SG_RESULT degeri yuksekse akis arttirilabilir,
        # dusukse azaltilmali. 50 referans degeri uzerinden hesaplama.
        if baseline > 0:
            flow_ratio = min(max(0.85 + (baseline / 500.0), 0.85), 1.15)
            flow_pct = f"%{flow_ratio * 100:.1f}"
        else:
            flow_pct = "N/A"

        print(f"  {key:<18} {baseline:>10}   {flow_pct:>13}")

    print(f"\nKalibrasyon dosyasi: {CALIBRATION_FILE}")

    # Guncel TMC degerini de goster
    current_sg = get_tmc_sg_result()
    if current_sg is not None:
        print(f"Guncel SG_RESULT:   {current_sg}")


def cmd_flow_test(_args):
    """Yeni kalibrasyon testi baslat (interaktif)."""
    print("TMC Akis Kalibrasyon Testi")
    print(f"{'=' * 50}")

    # Filament tipi sor
    valid_filaments = ["PLA", "PETG", "ABS", "TPU"]
    print(f"\nFilament tipleri: {', '.join(valid_filaments)}")
    filament = input("Filament tipi: ").strip().upper()
    if filament not in valid_filaments:
        print(f"Hata: Gecersiz filament tipi '{filament}'.")
        print(f"Gecerli tipler: {', '.join(valid_filaments)}")
        sys.exit(1)

    # Nozul sicakligi sor
    temp_str = input("Nozul sicakligi (C): ").strip()
    try:
        temp = int(temp_str)
        if temp < 150 or temp > 350:
            print(f"Uyari: Sicaklik degeri normal aralik disinda: {temp}C")
    except ValueError:
        print(f"Hata: Gecersiz sicaklik degeri '{temp_str}'.")
        sys.exit(1)

    key = f"{filament}_{temp}"
    print(f"\nKalibrasyon anahtari: {key}")
    print("TMC SG_RESULT ornekleri toplaniyor (30 saniye)...")

    # 30 saniye boyunca her saniye TMC SG_RESULT degerini oku
    samples = []
    for i in range(30):
        sg = get_tmc_sg_result()
        if sg is not None:
            samples.append(sg)
            status = f"  [{i + 1:2d}/30] SG_RESULT = {sg}"
        else:
            status = f"  [{i + 1:2d}/30] SG_RESULT = okunamadi"
        print(status)
        if i < 29:
            time.sleep(1)

    # Sonuclari hesapla
    if not samples:
        print("\nHata: Hic SG_RESULT ornegi toplanamadi.")
        print("TMC2209 extruder yapilandirmasini kontrol edin.")
        print("Moonraker baglantisini kontrol edin.")
        sys.exit(1)

    mean_sg = sum(samples) / len(samples)
    baseline = int(round(mean_sg))

    print(f"\nSonuc:")
    print(f"  Toplanan ornek: {len(samples)}/30")
    print(f"  Ortalama SG:    {mean_sg:.1f}")
    print(f"  Baseline:       {baseline}")

    # Kalibrasyon dosyasina kaydet
    data = load_calibration()
    data[key] = {
        "baseline_sg": baseline,
        "sample_count": len(samples),
        "filament": filament,
        "temp": temp,
        "timestamp": time.time(),
    }
    save_calibration(data)

    print(f"\nKalibrasyon kaydedildi: {key} -> baseline={baseline}")
    print(f"Dosya: {CALIBRATION_FILE}")


def cmd_flow_reset(_args):
    """Kalibrasyon verisini sil."""
    if CALIBRATION_FILE.exists():
        try:
            CALIBRATION_FILE.unlink()
            print("Kalibrasyon verisi silindi.")
            print(f"Dosya: {CALIBRATION_FILE}")
        except OSError as e:
            print(f"Hata: Kalibrasyon dosyasi silinemedi: {e}")
    else:
        print("Kalibrasyon dosyasi zaten mevcut degil.")
        print(f"Dosya: {CALIBRATION_FILE}")


def main():
    parser = argparse.ArgumentParser(
        description="KlipperOS-AI TMC Akis Kalibrasyon Araci",
        prog="kos-calibrate",
    )
    subparsers = parser.add_subparsers(dest="command", help="Komut")

    subparsers.add_parser("flow-status", help="Kalibrasyon durumu")
    subparsers.add_parser("flow-test", help="Yeni kalibrasyon testi")
    subparsers.add_parser("flow-reset", help="Kalibrasyon verisini sil")

    args = parser.parse_args()

    commands = {
        "flow-status": cmd_flow_status,
        "flow-test": cmd_flow_test,
        "flow-reset": cmd_flow_reset,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
