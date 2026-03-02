#!/usr/bin/env python3
"""
KlipperOS-AI Terminal Dashboard (Bloomberg-style TUI)
=====================================================
Terminal uzerinde calisan canli kontrol paneli.
Yazici durumu, sicakliklar, baski ilerlemesi, servisler, AI durumu.

Kullanim:
    kos-dashboard              # Tam dashboard
    kos-dashboard --minimal    # Minimal mod (LIGHT profil icin)
    kos-dashboard --refresh 5  # 5 saniye yenileme

Gereksinim: pip install rich psutil
"""

import argparse
import datetime
import json
import os
import signal
import subprocess
import sys
import time

try:
    from rich.console import Console
    from rich.layout import Layout
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.live import Live
    from rich import box
except ImportError:
    print("HATA: 'rich' kutuphanesi gerekli.")
    print("Kur:  pip install rich")
    sys.exit(1)

try:
    import psutil
except ImportError:
    psutil = None

# --- Constants ---

VERSION = "2.0.0"
MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")
KOS_CONFIG_DIR = "/etc/klipperos-ai"

COLORS = {
    "ok": "green",
    "warn": "yellow",
    "crit": "red",
    "info": "cyan",
    "dim": "bright_black",
    "value": "white",
    "bar_low": "green",
    "bar_mid": "yellow",
    "bar_high": "red",
}

LOG_PATHS = {
    "klippy": "/home/klipper/printer_data/logs/klippy.log",
    "moonraker": "/home/klipper/printer_data/logs/moonraker.log",
    "crowsnest": "/var/log/crowsnest.log",
    "ai-mon": "/home/klipper/printer_data/logs/ai-monitor.log",
}

KOS_SERVICES = [
    ("klipper.service", "Klipper"),
    ("moonraker.service", "Moonraker"),
    ("nginx.service", "Nginx"),
    ("KlipperScreen.service", "KlipperScreen"),
    ("crowsnest.service", "Crowsnest"),
    ("klipperos-ai-monitor.service", "AI Monitor"),
    ("ollama.service", "Ollama"),
    ("tailscaled.service", "Tailscale"),
]


# --- Data Collection ---

def _moonraker_get(endpoint, default=None):
    """Query Moonraker REST API."""
    try:
        import urllib.request
        url = f"{MOONRAKER_URL}{endpoint}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
            return data.get("result", data)
    except Exception:
        return default


def get_printer_status():
    """Get printer status from Moonraker."""
    data = _moonraker_get(
        "/printer/objects/query?print_stats&heater_bed&extruder&display_status"
    )
    if not data:
        return None

    status = data.get("status", {})
    ps = status.get("print_stats", {})
    ext = status.get("extruder", {})
    bed = status.get("heater_bed", {})
    disp = status.get("display_status", {})

    return {
        "state": ps.get("state", "unknown"),
        "filename": ps.get("filename", ""),
        "progress": disp.get("progress", 0) * 100,
        "print_duration": ps.get("print_duration", 0),
        "extruder_temp": ext.get("temperature", 0),
        "extruder_target": ext.get("target", 0),
        "bed_temp": bed.get("temperature", 0),
        "bed_target": bed.get("target", 0),
    }


def get_gcode_position():
    """Get current Z height and layer info."""
    data = _moonraker_get(
        "/printer/objects/query?gcode_move&print_stats"
    )
    if not data:
        return {"z": 0}
    status = data.get("status", {})
    gcode = status.get("gcode_move", {})
    pos = gcode.get("gcode_position", [0, 0, 0, 0])
    return {"z": pos[2] if len(pos) > 2 else 0}


def get_cpu_info():
    info = {"percent": 0, "freq": 0, "cores": 0, "temp": None}
    if not psutil:
        return info
    info["percent"] = psutil.cpu_percent(interval=0.5)
    info["cores"] = psutil.cpu_count()
    freq = psutil.cpu_freq()
    if freq:
        info["freq"] = int(freq.current)
    try:
        temps = psutil.sensors_temperatures()
        if temps:
            for entries in temps.values():
                if entries:
                    info["temp"] = int(entries[0].current)
                    break
    except (AttributeError, OSError):
        pass
    return info


def get_memory_info():
    if not psutil:
        return {"total": 0, "used": 0, "percent": 0, "swap_percent": 0}
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "total": mem.total // (1024 * 1024),
        "used": mem.used // (1024 * 1024),
        "available": mem.available // (1024 * 1024),
        "percent": mem.percent,
        "swap_total": swap.total // (1024 * 1024),
        "swap_used": swap.used // (1024 * 1024),
        "swap_percent": swap.percent,
    }


def get_disk_info():
    if not psutil:
        return []
    disks = []
    for part in psutil.disk_partitions():
        try:
            usage = psutil.disk_usage(part.mountpoint)
            disks.append({
                "mount": part.mountpoint,
                "total": usage.total // (1024**3),
                "used": usage.used // (1024**3),
                "free": usage.free // (1024**3),
                "percent": usage.percent,
            })
        except PermissionError:
            pass
    return disks


def get_service_status(name):
    try:
        r = subprocess.run(
            ["systemctl", "is-active", name],
            capture_output=True, text=True, timeout=3,
        )
        state = r.stdout.strip()
        if state == "active":
            return "active", "ok"
        if state == "inactive":
            return "inactive", "dim"
        return state, "warn"
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return "?", "dim"


def get_ollama_models():
    try:
        r = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return []
        models = []
        for line in r.stdout.strip().split("\n")[1:]:
            parts = line.split()
            if len(parts) >= 2:
                models.append({
                    "name": parts[0],
                    "size": parts[2] if len(parts) > 2 else "?",
                })
        return models
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return []


def get_tailscale_status():
    try:
        r = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if r.returncode != 0:
            return None
        data = json.loads(r.stdout)
        peers = data.get("Peer", {})
        return {
            "ip": data.get("TailscaleIPs", ["?"])[0] if data.get("TailscaleIPs") else "?",
            "hostname": data.get("Self", {}).get("HostName", "?"),
            "peers": len(peers),
            "connected": data.get("BackendState") == "Running",
        }
    except (subprocess.SubprocessError, FileNotFoundError, OSError, json.JSONDecodeError):
        return None


def get_flowguard_status():
    """Read FlowGuard status from AI monitor."""
    try:
        log_path = LOG_PATHS["ai-mon"]
        if not os.path.isfile(log_path):
            return None
        with open(log_path) as f:
            lines = f.readlines()[-50:]
        for line in reversed(lines):
            if "FlowGuard" in line or "flowguard" in line:
                return line.strip()[-80:]
        return "Aktif — son 50 satirda uyari yok"
    except OSError:
        return None


def get_camera_status():
    """Check Crowsnest camera status."""
    state, _ = get_service_status("crowsnest.service")
    if state != "active":
        return {"active": False, "streams": 0}

    # Count configured streams from crowsnest.conf
    streams = 0
    conf_path = "/home/klipper/printer_data/config/crowsnest.conf"
    try:
        with open(conf_path) as f:
            for line in f:
                if line.strip().startswith("[cam"):
                    streams += 1
    except OSError:
        pass
    return {"active": True, "streams": streams}


def get_uptime():
    if not psutil:
        return "?"
    boot = datetime.datetime.fromtimestamp(psutil.boot_time())
    delta = datetime.datetime.now() - boot
    days = delta.days
    hours = delta.seconds // 3600
    mins = (delta.seconds % 3600) // 60
    if days > 0:
        return f"{days}g {hours}s {mins}dk"
    if hours > 0:
        return f"{hours}s {mins}dk"
    return f"{mins}dk"


def get_load_avg():
    try:
        load = os.getloadavg()
        return f"{load[0]:.1f}  {load[1]:.1f}  {load[2]:.1f}"
    except (OSError, AttributeError):
        if psutil:
            return f"{psutil.cpu_percent():.0f}%"
        return "N/A"


def read_recent_logs(n=8):
    lines = []
    for tag, lf in LOG_PATHS.items():
        try:
            with open(lf) as f:
                for line in f.readlines()[-3:]:
                    line = line.strip()
                    if line:
                        lines.append((tag[:6], line[:120]))
        except OSError:
            pass
    lines.sort(key=lambda x: x[1], reverse=True)
    return lines[:n]


def read_ai_alerts(n=6):
    """Read recent alerts from AI monitor log."""
    alerts = []
    log_path = LOG_PATHS["ai-mon"]
    try:
        if not os.path.isfile(log_path):
            return alerts
        with open(log_path) as f:
            lines = f.readlines()[-100:]
        keywords = ("WARN", "ERROR", "ALERT", "PAUSE", "spaghetti", "FlowGuard")
        for line in reversed(lines):
            if any(kw in line for kw in keywords):
                alerts.append(line.strip()[-100:])
                if len(alerts) >= n:
                    break
    except OSError:
        pass
    return alerts


# --- Panel Builders ---

def make_bar(percent, width=20):
    filled = int(width * percent / 100)
    empty = width - filled
    if percent >= 90:
        color = COLORS["bar_high"]
    elif percent >= 70:
        color = COLORS["bar_mid"]
    else:
        color = COLORS["bar_low"]
    bar = f"[{color}]{'█' * filled}[/{color}][{COLORS['dim']}]{'░' * empty}[/{COLORS['dim']}]"
    return bar


def make_temp_bar(current, target, width=16):
    """Temperature bar with target indicator."""
    if target <= 0:
        # No target — show dim
        return f"[{COLORS['dim']}]{'░' * width}[/{COLORS['dim']}]"
    pct = min(current / target * 100, 100) if target > 0 else 0
    filled = int(width * pct / 100)
    empty = width - filled
    color = "green" if pct >= 95 else "yellow" if pct >= 50 else "cyan"
    return f"[{color}]{'█' * filled}[/{color}][{COLORS['dim']}]{'░' * empty}[/{COLORS['dim']}]"


def panel_header(tick):
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    uptime = get_uptime()
    load = get_load_avg()
    dots = "●" if tick % 2 == 0 else "○"

    text = Text()
    text.append(" ◆ KLIPPEROS-AI ", style="bold white on dark_blue")
    text.append(f" v{VERSION} ", style="bold cyan")
    text.append("│", style="bright_black")
    text.append(f" {now} ", style="white")
    text.append("│", style="bright_black")
    text.append(f" Uptime: {uptime} ", style="green")
    text.append("│", style="bright_black")
    text.append(f" Load: {load} ", style="yellow")
    text.append(f" {dots}", style="green")
    return text


def panel_printer_status(printer):
    """Printer status panel — state, file, progress."""
    table = Table(box=None, show_header=False, padding=(0, 1), expand=True)
    table.add_column("label", style=COLORS["dim"], width=12)
    table.add_column("val", style=COLORS["value"])

    if printer is None:
        table.add_row("Durum", "[red]Moonraker erisilemez[/red]")
        return Panel(table, title="[bold cyan]◆ Yazici[/bold cyan]",
                     border_style="red", box=box.ROUNDED)

    state = printer["state"]
    state_colors = {
        "printing": "green", "paused": "yellow", "complete": "cyan",
        "standby": "bright_black", "error": "red", "cancelled": "red",
    }
    sc = state_colors.get(state, "white")
    table.add_row("Durum", f"[{sc}]{state.upper()}[/{sc}]")

    if printer["filename"]:
        fname = printer["filename"][:30]
        table.add_row("Dosya", fname)

    if state == "printing":
        pct = printer["progress"]
        dur = int(printer["print_duration"])
        hrs, rem = divmod(dur, 3600)
        mins = rem // 60
        table.add_row("Ilerleme", f"{pct:.1f}%")
        table.add_row("Sure", f"{hrs}s {mins}dk")

    return Panel(table, title="[bold cyan]◆ Yazici[/bold cyan]",
                 border_style="cyan", box=box.ROUNDED)


def panel_print_progress(printer, gcode_pos):
    """Large print progress bar with Z height."""
    if printer is None or printer["state"] != "printing":
        text = Text("Baski aktif degil", style="bright_black")
        return Panel(text, title="[bold green]◆ Baski Ilerlemesi[/bold green]",
                     border_style="bright_black", box=box.ROUNDED)

    pct = printer["progress"]
    bar_width = 30
    filled = int(bar_width * pct / 100)
    empty = bar_width - filled
    bar_color = "green" if pct > 50 else "cyan"

    text = Text()
    text.append(f"  [{'█' * filled}{'░' * empty}] {pct:.1f}%\n", style=bar_color)
    text.append(f"  Z: {gcode_pos.get('z', 0):.2f} mm\n", style="white")

    return Panel(text, title="[bold green]◆ Baski Ilerlemesi[/bold green]",
                 border_style="green", box=box.ROUNDED)


def panel_temperatures(printer):
    """Real-time temperature bars."""
    table = Table(box=None, show_header=False, padding=(0, 1), expand=True)
    table.add_column("label", style=COLORS["dim"], width=10)
    table.add_column("bar", width=18)
    table.add_column("val", style=COLORS["value"], width=16, justify="right")

    if printer is None:
        table.add_row("", "", "[dim]Veri yok[/dim]")
        return Panel(table, title="[bold red]◆ Sicakliklar[/bold red]",
                     border_style="red", box=box.ROUNDED)

    # Extruder
    et = printer["extruder_temp"]
    ett = printer["extruder_target"]
    table.add_row(
        "Nozul",
        make_temp_bar(et, ett if ett > 0 else 260),
        f"{et:.0f}°C / {ett:.0f}°C" if ett > 0 else f"{et:.0f}°C",
    )

    # Bed
    bt = printer["bed_temp"]
    btt = printer["bed_target"]
    table.add_row(
        "Yatak",
        make_temp_bar(bt, btt if btt > 0 else 110),
        f"{bt:.0f}°C / {btt:.0f}°C" if btt > 0 else f"{bt:.0f}°C",
    )

    return Panel(table, title="[bold red]◆ Sicakliklar[/bold red]",
                 border_style="red", box=box.ROUNDED)


def panel_cpu(cpu_info):
    table = Table(box=None, show_header=False, padding=(0, 1), expand=True)
    table.add_column("label", style=COLORS["dim"], width=10)
    table.add_column("bar", width=22)
    table.add_column("val", style=COLORS["value"], width=10, justify="right")

    table.add_row("CPU", make_bar(cpu_info["percent"]), f"{cpu_info['percent']:5.1f}%")
    if cpu_info.get("freq"):
        table.add_row("Frekans", "", f"{cpu_info['freq']} MHz")
    if cpu_info.get("temp") is not None:
        temp = cpu_info["temp"]
        tc = "red" if temp > 80 else "yellow" if temp > 60 else "green"
        table.add_row("Sicaklik", "", f"[{tc}]{temp}°C[/{tc}]")

    return Panel(table, title="[bold cyan]◆ CPU[/bold cyan]",
                 border_style="cyan", box=box.ROUNDED)


def panel_memory(mem_info):
    table = Table(box=None, show_header=False, padding=(0, 1), expand=True)
    table.add_column("label", style=COLORS["dim"], width=10)
    table.add_column("bar", width=22)
    table.add_column("val", style=COLORS["value"], width=12, justify="right")

    table.add_row(
        "RAM", make_bar(mem_info["percent"]),
        f"{mem_info['used']}/{mem_info['total']} MB",
    )
    if mem_info.get("swap_total", 0) > 0:
        table.add_row(
            "Swap", make_bar(mem_info["swap_percent"]),
            f"{mem_info['swap_used']}/{mem_info['swap_total']} MB",
        )

    return Panel(table, title="[bold magenta]◆ Bellek[/bold magenta]",
                 border_style="magenta", box=box.ROUNDED)


def panel_disk(disks):
    table = Table(box=None, show_header=True, padding=(0, 1), expand=True)
    table.add_column("Baglam", style=COLORS["dim"], width=10)
    table.add_column("Kullanim", width=22)
    table.add_column("Bos", style=COLORS["value"], width=8, justify="right")

    for d in disks[:3]:
        table.add_row(d["mount"][:10], make_bar(d["percent"]), f"{d['free']} GB")

    return Panel(table, title="[bold yellow]◆ Disk[/bold yellow]",
                 border_style="yellow", box=box.ROUNDED)


def panel_services():
    table = Table(box=None, show_header=False, padding=(0, 1), expand=True)
    table.add_column("icon", width=2)
    table.add_column("name", style=COLORS["value"], width=14)
    table.add_column("status", width=10)

    for svc_name, display_name in KOS_SERVICES:
        state, color = get_service_status(svc_name)
        icon = "●" if state == "active" else "○"
        table.add_row(
            f"[{COLORS[color]}]{icon}[/{COLORS[color]}]",
            display_name,
            f"[{COLORS[color]}]{state}[/{COLORS[color]}]",
        )

    return Panel(table, title="[bold green]◆ Servisler[/bold green]",
                 border_style="green", box=box.ROUNDED)


def panel_ai_alerts(alerts):
    text = Text()
    if alerts:
        for line in alerts[:5]:
            if "ERROR" in line or "PAUSE" in line:
                text.append(f"  {line}\n", style="red")
            elif "WARN" in line:
                text.append(f"  {line}\n", style="yellow")
            else:
                text.append(f"  {line}\n", style="bright_black")
    else:
        text.append("  Uyari yok — sistem normal", style="green")

    return Panel(text, title="[bold white on red] ◆ AI Uyarilari [/bold white on red]",
                 border_style="red", box=box.HEAVY)


def panel_ollama(models):
    table = Table(box=None, show_header=False, padding=(0, 1), expand=True)
    table.add_column("model", style="cyan", width=24)
    table.add_column("size", style=COLORS["value"], width=8, justify="right")

    if models:
        for m in models[:6]:
            table.add_row(m["name"], m["size"])
    else:
        table.add_row("[dim]Ollama calismiyor[/dim]", "")

    return Panel(table, title="[bold cyan]◆ AI Modeller[/bold cyan]",
                 border_style="cyan", box=box.ROUNDED)


def panel_tailscale(ts_info):
    table = Table(box=None, show_header=False, padding=(0, 1), expand=True)
    table.add_column("label", style=COLORS["dim"], width=10)
    table.add_column("val", style=COLORS["value"])

    if ts_info and ts_info.get("connected"):
        table.add_row("Durum", "[green]● Bagli[/green]")
        table.add_row("IP", ts_info.get("ip", "?"))
        table.add_row("Peers", str(ts_info.get("peers", 0)))
    else:
        table.add_row("Durum", "[red]○ Bagli degil[/red]")

    return Panel(table, title="[bold blue]◆ Tailscale VPN[/bold blue]",
                 border_style="blue", box=box.ROUNDED)


def panel_flowguard(fg_status):
    text = Text()
    if fg_status:
        text.append(f"  {fg_status}", style="green")
    else:
        text.append("  FlowGuard durumu bilinmiyor", style="bright_black")

    return Panel(text, title="[bold yellow]◆ FlowGuard[/bold yellow]",
                 border_style="yellow", box=box.ROUNDED)


def panel_camera(cam_status):
    table = Table(box=None, show_header=False, padding=(0, 1), expand=True)
    table.add_column("label", style=COLORS["dim"], width=10)
    table.add_column("val", style=COLORS["value"])

    if cam_status["active"]:
        table.add_row("Durum", "[green]● Aktif[/green]")
        table.add_row("Stream", str(cam_status["streams"]))
    else:
        table.add_row("Durum", "[dim]○ Kapali[/dim]")

    return Panel(table, title="[bold blue]◆ Kamera[/bold blue]",
                 border_style="blue", box=box.ROUNDED)


def panel_logs(log_lines):
    text = Text()
    if log_lines:
        for src, line in log_lines:
            text.append(f"[{src}] ", style="cyan")
            if "error" in line.lower() or "fail" in line.lower():
                text.append(line[:100] + "\n", style="red")
            elif "warn" in line.lower():
                text.append(line[:100] + "\n", style="yellow")
            else:
                text.append(line[:100] + "\n", style="bright_black")
    else:
        text.append("Log bulunamadi", style="bright_black")

    return Panel(text, title="[bold white]◆ Son Loglar[/bold white]",
                 border_style="white", box=box.ROUNDED)


def panel_ticker(tick):
    messages = [
        "KlipperOS-AI v2 — AI-Powered 3D Printer OS",
        "Cikis: Ctrl+C | Yenile: Otomatik",
        "Web UI: http://klipperos.local | SSH: klipper@klipperos.local",
        "Komutlar: kos-agent | kos-recovery | kos-dashboard --minimal",
    ]
    idx = (tick // 3) % len(messages)
    return Text(f" ▶ {messages[idx]}", style="bold white on dark_blue")


# --- Main Layout ---

def build_dashboard(tick, minimal=False):
    # Collect data
    cpu_info = get_cpu_info()
    mem_info = get_memory_info()
    disks = get_disk_info()

    # Slow queries cached every 6 ticks (~30s at 5s refresh)
    if tick % 6 == 0 or tick == 0:
        build_dashboard._cache_printer = get_printer_status()
        build_dashboard._cache_gcode = get_gcode_position()
        build_dashboard._cache_ts = get_tailscale_status()
        build_dashboard._cache_models = get_ollama_models()
        build_dashboard._cache_logs = read_recent_logs()
        build_dashboard._cache_ai_alerts = read_ai_alerts()
        build_dashboard._cache_fg = get_flowguard_status()
        build_dashboard._cache_cam = get_camera_status()

    # Fast queries every tick for temps
    if tick % 2 == 0:
        build_dashboard._cache_printer = get_printer_status()
        build_dashboard._cache_gcode = get_gcode_position()

    printer = getattr(build_dashboard, '_cache_printer', None)
    gcode_pos = getattr(build_dashboard, '_cache_gcode', {"z": 0})
    ts_info = getattr(build_dashboard, '_cache_ts', None)
    models = getattr(build_dashboard, '_cache_models', [])
    log_lines = getattr(build_dashboard, '_cache_logs', [])
    ai_alerts = getattr(build_dashboard, '_cache_ai_alerts', [])
    fg_status = getattr(build_dashboard, '_cache_fg', None)
    cam_status = getattr(build_dashboard, '_cache_cam', {"active": False, "streams": 0})

    # Build layout
    layout = Layout()
    layout.split_column(
        Layout(name="header", size=1),
        Layout(name="alerts", size=5),
        Layout(name="main"),
        Layout(name="bottom", size=8),
        Layout(name="ticker", size=1),
    )

    layout["header"].update(panel_header(tick))
    layout["alerts"].update(panel_ai_alerts(ai_alerts))

    if minimal:
        # Minimal: Printer + Temps + Services only
        layout["main"].split_row(
            Layout(name="left", ratio=1),
            Layout(name="right", ratio=1),
        )
        layout["main"]["left"].split_column(
            Layout(panel_printer_status(printer)),
            Layout(panel_temperatures(printer)),
        )
        layout["main"]["right"].split_column(
            Layout(panel_services()),
            Layout(panel_memory(mem_info)),
        )
    else:
        # Full: 3-column layout
        layout["main"].split_row(
            Layout(name="left", ratio=2),
            Layout(name="center", ratio=2),
            Layout(name="right", ratio=2),
        )

        # Left: Printer
        layout["main"]["left"].split_column(
            Layout(panel_printer_status(printer), ratio=2),
            Layout(panel_temperatures(printer), ratio=1),
            Layout(panel_print_progress(printer, gcode_pos), ratio=1),
        )

        # Center: System
        layout["main"]["center"].split_column(
            Layout(panel_cpu(cpu_info), ratio=1),
            Layout(panel_memory(mem_info), ratio=1),
            Layout(panel_disk(disks), ratio=1),
            Layout(panel_services(), ratio=2),
        )

        # Right: AI + Network
        layout["main"]["right"].split_column(
            Layout(panel_ollama(models), ratio=1),
            Layout(panel_tailscale(ts_info), ratio=1),
            Layout(panel_flowguard(fg_status), ratio=1),
            Layout(panel_camera(cam_status), ratio=1),
        )

    layout["bottom"].update(panel_logs(log_lines))
    layout["ticker"].update(panel_ticker(tick))

    return layout


# --- Main ---

def main():
    parser = argparse.ArgumentParser(
        description="KlipperOS-AI Terminal Dashboard",
        prog="kos-dashboard",
    )
    parser.add_argument("--minimal", "-m", action="store_true",
                        help="Minimal mod (LIGHT profil icin)")
    parser.add_argument("--refresh", "-r", type=int, default=5,
                        help="Yenileme araligi (saniye, varsayilan: 5)")
    args = parser.parse_args()

    console = Console()

    if not psutil:
        console.print("[red]HATA:[/red] 'psutil' gerekli: pip install psutil")
        sys.exit(1)

    def signal_handler(sig, frame):
        console.clear()
        console.print("\n[cyan]KlipperOS-AI Dashboard kapatildi.[/cyan]")
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    tick = 0
    try:
        with Live(console=console, refresh_per_second=1, screen=True) as live:
            while True:
                layout = build_dashboard(tick, minimal=args.minimal)
                live.update(layout)
                time.sleep(args.refresh)
                tick += 1
    except KeyboardInterrupt:
        pass
    finally:
        console.clear()
        console.print("[cyan]KlipperOS-AI Dashboard kapatildi.[/cyan]")


if __name__ == "__main__":
    main()
