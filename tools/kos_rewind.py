#!/usr/bin/env python3
"""
KlipperOS-AI — Smart Rewind Tool
=================================
Akis durmasinda baskiyi belirli bir katmandan yeniden baslatma.

Kullanim:
    kos-rewind status              # Mevcut baski durumu
    kos-rewind preview             # Kamera goruntusunu kaydet
    kos-rewind goto --layer 50     # 50. katmandan yeniden baslat
    kos-rewind auto                # FlowGuard son OK katmanindan devam et
"""

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Optional, Tuple, List

import requests

MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")
CAMERA_URL = os.environ.get("CAMERA_URL", "http://127.0.0.1:8080/?action=snapshot")


def find_layer_position(gcode_text: str, target_layer: int) -> Tuple[Optional[int], Optional[float]]:
    """G-code metninde hedef katmanin byte konumunu ve Z yuksekligini bul.

    Desteklenen formatlar:
        ;LAYER:N            (Cura)
        ;BEFORE_LAYER_CHANGE + ;Z  (PrusaSlicer/OrcaSlicer)

    Returns:
        (byte_offset, z_height) or (None, None) if not found.
    """
    lines = gcode_text.split("\n")
    current_pos = 0
    z_height = None
    pending_z = None

    for i, line in enumerate(lines):
        stripped = line.strip()

        # PrusaSlicer: ;BEFORE_LAYER_CHANGE followed by ;Z_VALUE
        if stripped == ";BEFORE_LAYER_CHANGE":
            # Next line should have Z value
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line.startswith(";") and not next_line.startswith(";LAYER"):
                    try:
                        pending_z = float(next_line.lstrip(";"))
                    except ValueError:
                        pass

        # Cura/PrusaSlicer: ;LAYER:N
        layer_match = re.match(r"^;LAYER:(\d+)", stripped)
        if layer_match:
            layer_num = int(layer_match.group(1))
            if layer_num == target_layer:
                return current_pos, pending_z or z_height

        # Track Z from G1 commands
        z_match = re.match(r"^G1\s.*Z([\d.]+)", stripped)
        if z_match:
            z_height = float(z_match.group(1))

        current_pos += len(line) + 1  # +1 for \n

    return None, None


def apply_z_offset(lines: List[str], z_offset: float) -> List[str]:
    """G-code satirlarindaki Z degerlerine offset ekle.

    Args:
        lines: G-code satirlari
        z_offset: Eklenecek Z offset (mm)

    Returns:
        Z degerlerine offset eklenmis satirlar.
    """
    if z_offset == 0.0:
        return list(lines)

    result = []
    for line in lines:
        match = re.match(r"^(G1\s.*Z)([\d.]+)(.*)", line)
        if match:
            prefix = match.group(1)
            z_val = float(match.group(2))
            suffix = match.group(3)
            new_z = z_val + z_offset
            result.append(f"{prefix}{new_z:.3f}{suffix}")
        else:
            result.append(line)
    return result


def generate_preamble(state: dict, purge_length: float = 30.0) -> str:
    """Resume icin on-gcode olustur."""
    extruder_temp = state.get("extruder_temp", 210)
    bed_temp = state.get("bed_temp", 60)
    fan_speed = state.get("fan_speed", 0.0)
    fan_pwm = int(float(fan_speed) * 255)

    lines = [
        "; === KlipperOS-AI Rewind Preamble ===",
        f"M104 S{extruder_temp}   ; Extruder hedef",
        f"M140 S{bed_temp}        ; Bed hedef",
        f"M109 S{extruder_temp}   ; Extruder bekle",
        f"M190 S{bed_temp}        ; Bed bekle",
        f"M106 S{fan_pwm}         ; Fan",
        "G92 E0                   ; Extruder sifirla",
        f"G1 E{purge_length} F300 ; Purge",
        "G1 E-2 F1800             ; Retract",
        "G92 E0                   ; Extruder sifirla",
        "; === Rewind Start ===",
        "",
    ]
    return "\n".join(lines)


def moonraker_get(endpoint: str, params: dict = None) -> Optional[dict]:
    """Moonraker GET sorgusu."""
    try:
        resp = requests.get(f"{MOONRAKER_URL}{endpoint}", params=params, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except Exception:
        return None


def moonraker_gcode(gcode: str) -> bool:
    """Moonraker uzerinden G-code calistir."""
    try:
        resp = requests.post(
            f"{MOONRAKER_URL}/printer/gcode/script",
            json={"script": gcode},
            timeout=10,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        print(f"Moonraker hatasi: {e}")
        return False


def capture_preview(output_path: str) -> bool:
    """Kameradan snapshot al ve kaydet."""
    try:
        resp = requests.get(CAMERA_URL, timeout=10)
        resp.raise_for_status()
        with open(output_path, "wb") as f:
            f.write(resp.content)
        return True
    except Exception as e:
        print(f"Kamera hatasi: {e}")
        return False


def cmd_status(_args):
    """Mevcut baski durumu ve FlowGuard bilgisi."""
    print("Rewind Durum Bilgisi")
    print(f"{'='*50}")

    data = moonraker_get("/printer/objects/query",
                         {"print_stats": "state,filename,total_duration,info"})
    if data:
        status = data.get("result", {}).get("status", {})
        ps = status.get("print_stats", {})
        info = ps.get("info", {})
        print(f"  Durum:     {ps.get('state', '?')}")
        print(f"  Dosya:     {ps.get('filename', '?')}")
        print(f"  Katman:    {info.get('current_layer', '?')} / {info.get('total_layer', '?')}")
    else:
        print("  Moonraker'a ulasilamiyor.")


def cmd_preview(_args):
    """Kamera goruntusunu kaydet."""
    output = "/tmp/kos_rewind_preview.jpg"
    print("Kamera goruntusu aliniyor...")
    if capture_preview(output):
        print(f"Goruntu kaydedildi: {output}")
    else:
        print("Hata: Kamera goruntusu alinamadi.")


def cmd_goto(args):
    """Belirli bir katmandan yeniden baslat."""
    target_layer = args.layer
    z_offset = args.z_offset
    purge = args.purge
    dry_run = args.dry_run

    print(f"Smart Rewind -- Hedef Katman: {target_layer}")
    print(f"{'='*50}")

    # Mevcut baski dosyasini bul
    data = moonraker_get("/printer/objects/query",
                         {"print_stats": "filename", "virtual_sdcard": "file_path"})
    if not data:
        print("Hata: Moonraker'a ulasilamiyor.")
        sys.exit(1)

    status = data.get("result", {}).get("status", {})
    filename = status.get("print_stats", {}).get("filename", "")
    if not filename:
        print("Hata: Aktif baski dosyasi bulunamadi.")
        sys.exit(1)

    print(f"  Dosya: {filename}")

    # G-code dosyasini indir
    gcode_path = Path.home() / "printer_data" / "gcodes" / filename
    if not gcode_path.exists():
        print(f"Hata: G-code dosyasi bulunamadi: {gcode_path}")
        sys.exit(1)

    with open(gcode_path) as f:
        gcode_text = f.read()

    # Hedef katmani bul
    position, z_height = find_layer_position(gcode_text, target_layer)
    if position is None:
        print(f"Hata: Katman {target_layer} bulunamadi!")
        sys.exit(1)

    print(f"  Katman {target_layer} bulundu (Z={z_height:.1f}mm, pozisyon={position})")
    print(f"  Z offset: +{z_offset} mm")

    if dry_run:
        print(f"\n[DRY RUN] Gercek islem yapilmayacak.")
        print(f"  Rewind dosyasi olusturulacakti: {filename}_rewind_L{target_layer}.gcode")
        return

    # Preview
    preview_path = "/tmp/kos_rewind_preview.jpg"
    if capture_preview(preview_path):
        print(f"  Baski onizleme: {preview_path}")

    # Onay
    answer = input(f"\nKatman {target_layer}'dan yeniden baslatilacak. Devam? [e/H] ").strip().lower()
    if answer != "e":
        print("Iptal edildi.")
        return

    # Rewind G-code olustur
    state = {
        "extruder_temp": 210,
        "bed_temp": 60,
        "fan_speed": 0.0,
    }

    # PLR'dan temp bilgisi okumaya calis
    try:
        from kos_plr import read_plr_state
        plr = read_plr_state()
        if plr:
            state["extruder_temp"] = plr.get("plr_extruder_temp", 210)
            state["bed_temp"] = plr.get("plr_bed_temp", 60)
            state["fan_speed"] = plr.get("plr_fan_speed", 0.0)
    except ImportError:
        pass

    preamble = generate_preamble(state, purge_length=purge)

    # Katmandan sonraki gcode'u al ve Z offset uygula
    remaining_gcode = gcode_text[position:]
    remaining_lines = remaining_gcode.split("\n")
    if z_offset > 0:
        remaining_lines = apply_z_offset(remaining_lines, z_offset)

    rewind_gcode = preamble + "\n".join(remaining_lines)

    # Rewind dosyasini kaydet
    rewind_name = f"{Path(filename).stem}_rewind_L{target_layer}.gcode"
    rewind_path = Path.home() / "printer_data" / "gcodes" / rewind_name

    with open(rewind_path, "w") as f:
        f.write(rewind_gcode)
    print(f"Rewind dosyasi: {rewind_path}")

    # Makrolari calistir
    print("Yazici hazirlaniyor...")
    moonraker_gcode("KOS_REWIND_PARK")
    moonraker_gcode("KOS_REWIND_HOME")
    moonraker_gcode(
        f"KOS_REWIND_PREPARE EXTRUDER_TEMP={state['extruder_temp']} "
        f"BED_TEMP={state['bed_temp']} FAN_SPEED={state['fan_speed']} "
        f"PURGE_LENGTH={purge}"
    )

    # Baskiyi baslat
    print(f"Rewind baskisi baslatiliyor: {rewind_name}")
    try:
        resp = requests.post(
            f"{MOONRAKER_URL}/printer/print/start",
            json={"filename": rewind_name},
            timeout=10,
        )
        resp.raise_for_status()
        print("Rewind baskisi baslatildi!")
    except Exception as e:
        print(f"Hata: Baski baslatilamadi: {e}")
        print(f"Manuel baslatin: Mainsail/Fluidd'den {rewind_name} dosyasini secin.")


def cmd_auto(args):
    """FlowGuard son OK katmanindan otomatik rewind."""
    z_offset = args.z_offset

    print("Auto Rewind -- FlowGuard son saglikli katman")
    print(f"{'='*50}")

    # FlowGuard durumunu Moonraker'dan oku (bu bilgi monitor daemon'dan gelir)
    # Simdilik placeholder -- gercek implementasyonda daemon IPC kullanilir
    print("Uyari: Auto rewind icin FlowGuard monitor'un calisiyor olmasi gerekir.")
    print("Manuel olarak kullanin: kos-rewind goto --layer N")


def main():
    parser = argparse.ArgumentParser(
        description="KlipperOS-AI Smart Rewind Araci",
        prog="kos-rewind",
    )
    subparsers = parser.add_subparsers(dest="command", help="Komut")

    subparsers.add_parser("status", help="Mevcut baski durumu")
    subparsers.add_parser("preview", help="Kamera goruntusu al")

    goto_parser = subparsers.add_parser("goto", help="Belirli katmandan yeniden baslat")
    goto_parser.add_argument("--layer", "-l", type=int, required=True,
                             help="Hedef katman numarasi")
    goto_parser.add_argument("--z-offset", "-z", type=float, default=1.0,
                             help="Z offset (mm, default: 1.0)")
    goto_parser.add_argument("--purge", "-p", type=float, default=30.0,
                             help="Purge uzunlugu (mm, default: 30)")
    goto_parser.add_argument("--dry-run", action="store_true",
                             help="Sadece analiz yap, islem yapma")

    auto_parser = subparsers.add_parser("auto", help="FlowGuard ile otomatik rewind")
    auto_parser.add_argument("--z-offset", "-z", type=float, default=1.0,
                             help="Z offset (mm, default: 1.0)")

    args = parser.parse_args()

    commands = {
        "status": cmd_status,
        "preview": cmd_preview,
        "goto": cmd_goto,
        "auto": cmd_auto,
    }

    if args.command in commands:
        commands[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
