#!/usr/bin/env python3
"""
KlipperOS-AI — Gerçek Kamera Frame Toplama
============================================
Monitor çalışırken snapshot API'den frame toplar.
Kullanıcı normal baskı ve anomali durumlarında frame kaydeder.

Kullanım (sunucuda çalıştır):
    python3 collect_training_frames.py --label normal --count 100 --interval 2
    python3 collect_training_frames.py --label spaghetti --count 50 --interval 2
"""

import argparse
import os
import sys
import time
import urllib.request

# Config
API_BASE = "http://127.0.0.1:8470"
PRINTER_ID = "bambu-3e4daa5d"
SNAPSHOT_URL = f"{API_BASE}/api/v1/bambu/printers/{PRINTER_ID}/camera/snapshot"
OUTPUT_DIR = "/opt/klipperos-ai/training_data"


def collect_frames(label: str, count: int, interval: float):
    """Snapshot API'den frame topla ve diske kaydet."""
    label_dir = os.path.join(OUTPUT_DIR, label)
    os.makedirs(label_dir, exist_ok=True)

    # Mevcut dosya sayısını bul (devam edebilmek için)
    existing = len([f for f in os.listdir(label_dir) if f.endswith(".jpg")])
    print(f"\n{'='*50}")
    print(f"  Frame Toplama: {label}")
    print(f"  Hedef: {count} frame, aralik: {interval}s")
    print(f"  Mevcut: {existing} frame")
    print(f"  Kayit: {label_dir}")
    print(f"{'='*50}\n")

    collected = 0
    errors = 0

    for i in range(count):
        idx = existing + i
        filename = f"{label}_{idx:04d}.jpg"
        filepath = os.path.join(label_dir, filename)

        try:
            req = urllib.request.Request(SNAPSHOT_URL)
            with urllib.request.urlopen(req, timeout=10) as resp:
                jpeg_data = resp.read()

            if len(jpeg_data) < 1000:
                print(f"  [{i+1}/{count}] SKIP - cok kucuk ({len(jpeg_data)} byte)")
                errors += 1
                time.sleep(interval)
                continue

            with open(filepath, "wb") as f:
                f.write(jpeg_data)

            collected += 1
            size_kb = len(jpeg_data) / 1024
            print(f"  [{i+1}/{count}] {filename} ({size_kb:.0f} KB)")

        except Exception as e:
            errors += 1
            print(f"  [{i+1}/{count}] HATA: {e}")

        if i < count - 1:
            time.sleep(interval)

    print(f"\n{'='*50}")
    print(f"  Toplam: {collected} frame toplandi, {errors} hata")
    print(f"  Dizin: {label_dir}")
    print(f"{'='*50}\n")
    return collected


def main():
    parser = argparse.ArgumentParser(description="Kamera frame toplama")
    parser.add_argument(
        "--label",
        required=True,
        choices=["normal", "spaghetti", "stringing", "no_extrusion", "completed"],
        help="Frame etiketi (sinif)",
    )
    parser.add_argument(
        "--count", type=int, default=100, help="Toplanacak frame sayisi"
    )
    parser.add_argument(
        "--interval", type=float, default=2.0, help="Frame arasi bekleme (saniye)"
    )
    args = parser.parse_args()

    collect_frames(args.label, args.count, args.interval)


if __name__ == "__main__":
    main()
