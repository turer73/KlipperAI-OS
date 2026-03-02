#!/usr/bin/env python3
"""
KlipperOS-AI Agent — Tool-calling AI assistant for 3D printers
===============================================================
Klipper yazdirma yonetimi, G-code analizi, sicaklik izleme,
baski optimizasyonu ve sistem yonetimi icin yerel AI asistan.

Kullanim:
    kos-agent                         # Interaktif mod
    kos-agent "Yazici durumunu gor"   # Tek seferlik soru
    kos-agent --status                # Agent durumu
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys

try:
    import psutil
except ImportError:
    psutil = None

try:
    import yaml
except ImportError:
    yaml = None

# --- Constants ---

TAG = "[kos-agent]"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
DIM = "\033[2m"
NC = "\033[0m"

AGENT_CONFIG_PATH = "/etc/klipperos-ai/ai-agent.yml"
MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")

OLLAMA_MODEL_AGENT = "klipperos-ai-agent"
OLLAMA_MODEL_CODER = "klipperos-ai-coder"
OLLAMA_MODEL = OLLAMA_MODEL_AGENT
OLLAMA_API = "http://localhost:11434/api/chat"

PRINTER_DATA = "/home/klipper/printer_data"
LOG_DIR = os.path.join(PRINTER_DATA, "logs")

# G-code commands that require explicit user confirmation
DANGEROUS_GCODE = [
    "M112",               # Emergency stop
    "FIRMWARE_RESTART",   # Firmware restart
    "SAVE_CONFIG",        # Write config
    "SET_KINEMATIC_POSITION",
]

SYSTEM_PROMPT = (
    "Sen KlipperOS-AI asistanisin. 3D yazici yonetimi, Klipper konfigurasyonu, "
    "baski hatasi tespiti, G-code analizi ve yazici optimizasyonu konusunda uzmansin. "
    "Turkce konusuyorsun. Kisa ve net cevap ver.\n\n"
)


# --- Output helpers ---

def info(msg):
    print(f"{GREEN}{TAG}{NC} {msg}")

def warn(msg):
    print(f"{YELLOW}{TAG}{NC} {msg}")

def error(msg):
    print(f"{RED}{TAG}{NC} {msg}")

def agent_say(msg):
    print(f"{CYAN}AI:{NC} {msg}")

def user_prompt():
    try:
        return input(f"\n{GREEN}Sen:{NC} ").strip()
    except (EOFError, KeyboardInterrupt):
        return None


# --- Config Loader ---

_config = None


def load_config():
    global _config, OLLAMA_MODEL_AGENT, OLLAMA_MODEL_CODER, OLLAMA_API
    if _config is not None:
        return _config

    _config = {}
    if not yaml:
        return _config
    try:
        if os.path.exists(AGENT_CONFIG_PATH):
            with open(AGENT_CONFIG_PATH) as f:
                _config = yaml.safe_load(f) or {}
            agent_cfg = _config.get("agent", {})
            if agent_cfg.get("model_primary"):
                OLLAMA_MODEL_AGENT = agent_cfg["model_primary"]
            if agent_cfg.get("model_fallback"):
                OLLAMA_MODEL_CODER = agent_cfg["model_fallback"]
            if agent_cfg.get("ollama_api"):
                OLLAMA_API = agent_cfg["ollama_api"] + "/api/chat"
    except (ValueError, OSError):
        pass
    return _config


# --- Moonraker API ---

def _moonraker_get(endpoint):
    """Query Moonraker REST API."""
    try:
        import urllib.request
        url = f"{MOONRAKER_URL}{endpoint}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            return data.get("result", data)
    except Exception:
        return None


def _moonraker_post(endpoint, data=None):
    """POST to Moonraker REST API."""
    try:
        import urllib.request
        url = f"{MOONRAKER_URL}{endpoint}"
        body = json.dumps(data or {}).encode()
        req = urllib.request.Request(url, data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"error": str(e)}


# --- Tool Registry ---

TOOLS = []


def register_tool(name, description, func, requires_confirm=False, params=None):
    TOOLS.append({
        "name": name,
        "description": description,
        "function": func,
        "requires_confirm": requires_confirm,
        "params": params or {},
    })


def get_tools_prompt():
    lines = ["You have access to these tools:\n"]
    for t in TOOLS:
        params_str = ""
        if t["params"]:
            params_str = f" Params: {json.dumps(t['params'])}"
        confirm = " [REQUIRES USER CONFIRMATION]" if t["requires_confirm"] else ""
        lines.append(f"- {t['name']}: {t['description']}{params_str}{confirm}")

    lines.append("\nTo use a tool, respond with JSON in this format:")
    lines.append('{"tool": "tool_name", "params": {"key": "value"}}')
    lines.append("\nYou can call multiple tools by returning a JSON array.")
    lines.append("If no tool is needed, respond normally in Turkish.")
    lines.append("Always explain what you're doing before calling tools.")
    return "\n".join(lines)


def find_tool(name):
    for t in TOOLS:
        if t["name"] == name:
            return t
    return None


# =============================================================================
# Printer Tools
# =============================================================================

def tool_printer_status():
    """Get printer status from Moonraker."""
    data = _moonraker_get(
        "/printer/objects/query?print_stats&heater_bed&extruder&display_status&toolhead"
    )
    if not data:
        return json.dumps({"error": "Moonraker erisilemez"})

    status = data.get("status", {})
    ps = status.get("print_stats", {})
    ext = status.get("extruder", {})
    bed = status.get("heater_bed", {})
    disp = status.get("display_status", {})
    th = status.get("toolhead", {})

    return json.dumps({
        "state": ps.get("state", "unknown"),
        "filename": ps.get("filename", ""),
        "progress_pct": round((disp.get("progress", 0)) * 100, 1),
        "print_duration_s": int(ps.get("print_duration", 0)),
        "extruder_temp": round(ext.get("temperature", 0), 1),
        "extruder_target": round(ext.get("target", 0), 1),
        "bed_temp": round(bed.get("temperature", 0), 1),
        "bed_target": round(bed.get("target", 0), 1),
        "position": th.get("position", []),
        "homed_axes": th.get("homed_axes", ""),
    }, indent=2, ensure_ascii=False)


def tool_printer_temps():
    """Get current temperatures."""
    data = _moonraker_get("/printer/objects/query?extruder&heater_bed")
    if not data:
        return json.dumps({"error": "Moonraker erisilemez"})
    status = data.get("status", {})
    return json.dumps({
        "extruder": {
            "temp": round(status.get("extruder", {}).get("temperature", 0), 1),
            "target": round(status.get("extruder", {}).get("target", 0), 1),
        },
        "bed": {
            "temp": round(status.get("heater_bed", {}).get("temperature", 0), 1),
            "target": round(status.get("heater_bed", {}).get("target", 0), 1),
        },
    }, indent=2)


def tool_print_progress():
    """Get detailed print progress."""
    data = _moonraker_get(
        "/printer/objects/query?print_stats&display_status&gcode_move"
    )
    if not data:
        return json.dumps({"error": "Moonraker erisilemez"})
    status = data.get("status", {})
    ps = status.get("print_stats", {})
    disp = status.get("display_status", {})
    gcode = status.get("gcode_move", {})
    pos = gcode.get("gcode_position", [0, 0, 0, 0])

    duration = int(ps.get("print_duration", 0))
    hrs, rem = divmod(duration, 3600)
    mins = rem // 60

    return json.dumps({
        "state": ps.get("state", "unknown"),
        "filename": ps.get("filename", ""),
        "progress_pct": round((disp.get("progress", 0)) * 100, 1),
        "duration": f"{hrs}s {mins}dk",
        "z_height_mm": round(pos[2], 2) if len(pos) > 2 else 0,
        "speed_factor": round(gcode.get("speed_factor", 1) * 100),
        "extrude_factor": round(gcode.get("extrude_factor", 1) * 100),
    }, indent=2, ensure_ascii=False)


def tool_pause_print():
    """Pause current print (requires confirmation)."""
    result = _moonraker_post("/printer/print/pause")
    if result and "error" not in result:
        return json.dumps({"success": True, "message": "Baski duraklatildi"})
    return json.dumps({"error": "Baski duraklatma basarisiz", "detail": str(result)})


def tool_resume_print():
    """Resume paused print (requires confirmation)."""
    result = _moonraker_post("/printer/print/resume")
    if result and "error" not in result:
        return json.dumps({"success": True, "message": "Baski devam ediyor"})
    return json.dumps({"error": "Baski devam basarisiz", "detail": str(result)})


def tool_cancel_print():
    """Cancel current print (requires confirmation)."""
    result = _moonraker_post("/printer/print/cancel")
    if result and "error" not in result:
        return json.dumps({"success": True, "message": "Baski iptal edildi"})
    return json.dumps({"error": "Baski iptal basarisiz", "detail": str(result)})


def tool_send_gcode(gcode=""):
    """Send G-code command to printer (requires confirmation for dangerous)."""
    if not gcode:
        return json.dumps({"error": "G-code komutu gerekli"})

    # Check for dangerous commands
    gcode_upper = gcode.strip().upper()
    for dangerous in DANGEROUS_GCODE:
        if dangerous in gcode_upper:
            return json.dumps({
                "error": f"Tehlikeli G-code: {dangerous}. Kullanici onayi gerekli.",
                "gcode": gcode,
            })

    data = _moonraker_post("/printer/gcode/script", {"script": gcode})
    if data and "error" not in data:
        return json.dumps({"success": True, "gcode": gcode})
    return json.dumps({"error": "G-code gonderilemedi", "detail": str(data)})


def tool_set_temp(heater="extruder", target=0):
    """Set heater temperature (requires confirmation)."""
    try:
        target = int(target)
    except (ValueError, TypeError):
        return json.dumps({"error": "Gecersiz sicaklik degeri"})

    # Safety limits
    if heater == "extruder" and target > 300:
        return json.dumps({"error": "Nozul sicakligi 300°C'yi gecemez"})
    if heater == "heater_bed" and target > 120:
        return json.dumps({"error": "Yatak sicakligi 120°C'yi gecemez"})

    gcode = f"SET_HEATER_TEMPERATURE HEATER={heater} TARGET={target}"
    data = _moonraker_post("/printer/gcode/script", {"script": gcode})
    if data and "error" not in data:
        return json.dumps({"success": True, "heater": heater, "target": target})
    return json.dumps({"error": "Sicaklik ayarlanamadi"})


def tool_adjust_speed(factor=100):
    """Adjust print speed factor (percentage)."""
    try:
        factor = int(factor)
    except (ValueError, TypeError):
        return json.dumps({"error": "Gecersiz hiz degeri"})
    if not 10 <= factor <= 300:
        return json.dumps({"error": "Hiz faktoru 10-300 arasinda olmali"})

    gcode = f"M220 S{factor}"
    data = _moonraker_post("/printer/gcode/script", {"script": gcode})
    if data and "error" not in data:
        return json.dumps({"success": True, "speed_factor": factor})
    return json.dumps({"error": "Hiz ayarlanamadi"})


def tool_home_printer():
    """Home all axes (G28) (requires confirmation)."""
    data = _moonraker_post("/printer/gcode/script", {"script": "G28"})
    if data and "error" not in data:
        return json.dumps({"success": True, "message": "Tum eksenler sifirlandi (G28)"})
    return json.dumps({"error": "Home basarisiz"})


def tool_list_gcode_files():
    """List G-code files available for printing."""
    data = _moonraker_get("/server/files/list?root=gcodes")
    if not data:
        return json.dumps({"error": "Dosya listesi alinamadi"})
    files = []
    for f in (data if isinstance(data, list) else []):
        files.append({
            "filename": f.get("filename", "?"),
            "size_mb": round(f.get("size", 0) / (1024 * 1024), 1),
            "modified": f.get("modified", ""),
        })
    files.sort(key=lambda x: x.get("modified", ""), reverse=True)
    return json.dumps(files[:20], indent=2, ensure_ascii=False)


def tool_camera_snapshot():
    """Get camera/Crowsnest status."""
    state = "unknown"
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "crowsnest.service"],
            capture_output=True, text=True, timeout=3,
        )
        state = r.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    streams = 0
    conf_path = os.path.join(PRINTER_DATA, "config/crowsnest.conf")
    try:
        with open(conf_path) as f:
            for line in f:
                if line.strip().startswith("[cam"):
                    streams += 1
    except OSError:
        pass

    return json.dumps({
        "crowsnest": state,
        "streams": streams,
        "snapshot_url": f"{MOONRAKER_URL}/webcam/?action=snapshot" if state == "active" else None,
    }, indent=2)


def tool_ai_monitor_status():
    """Get AI print monitor alerts and status."""
    log_path = os.path.join(LOG_DIR, "ai-monitor.log")
    alerts = []
    try:
        if os.path.isfile(log_path):
            with open(log_path) as f:
                lines = f.readlines()[-100:]
            keywords = ("WARN", "ERROR", "ALERT", "PAUSE", "spaghetti", "FlowGuard")
            for line in reversed(lines):
                if any(kw in line for kw in keywords):
                    alerts.append(line.strip()[-120:])
                    if len(alerts) >= 10:
                        break
    except OSError:
        pass

    # Service status
    state = "unknown"
    try:
        r = subprocess.run(
            ["systemctl", "is-active", "klipperos-ai-monitor.service"],
            capture_output=True, text=True, timeout=3,
        )
        state = r.stdout.strip()
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return json.dumps({
        "service": state,
        "recent_alerts": alerts,
        "alert_count": len(alerts),
    }, indent=2, ensure_ascii=False)


def tool_printer_config(filename="printer.cfg"):
    """Read a Klipper config file (read-only)."""
    safe_dir = os.path.join(PRINTER_DATA, "config")
    abs_path = os.path.abspath(os.path.join(safe_dir, filename))

    if not abs_path.startswith(safe_dir):
        return json.dumps({"error": "Guvenlik: Sadece printer_data/config/ okunabilir"})

    try:
        with open(abs_path) as f:
            content = f.read(8192)  # Max 8KB
        return json.dumps({"path": abs_path, "content": content}, ensure_ascii=False)
    except (FileNotFoundError, PermissionError) as e:
        return json.dumps({"error": str(e)})


def tool_list_macros():
    """List Klipper macros from config."""
    data = _moonraker_get("/printer/objects/list")
    if not data:
        return json.dumps({"error": "Moonraker erisilemez"})

    objects = data.get("objects", [])
    macros = [obj.replace("gcode_macro ", "") for obj in objects
              if obj.startswith("gcode_macro ")]
    return json.dumps({"macros": sorted(macros), "count": len(macros)}, indent=2)


# =============================================================================
# System Tools (kept from Linux-AI, adapted)
# =============================================================================

def tool_system_info():
    """Get system resource information."""
    if not psutil:
        return json.dumps({"error": "psutil bulunamadi"})

    cpu_percent = psutil.cpu_percent(interval=1)
    mem = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return json.dumps({
        "cpu_percent": cpu_percent,
        "cpu_cores": psutil.cpu_count(),
        "ram_total_mb": mem.total // (1024 * 1024),
        "ram_used_mb": mem.used // (1024 * 1024),
        "ram_percent": mem.percent,
        "disk_total_gb": disk.total // (1024**3),
        "disk_free_gb": disk.free // (1024**3),
        "disk_percent": disk.percent,
    }, indent=2)


def tool_run_command(cmd=""):
    """Run a safe system command (requires confirmation)."""
    if not cmd:
        return json.dumps({"error": "Komut gerekli"})

    allowed_prefixes = [
        "systemctl status", "systemctl is-active",
        "df ", "free ", "uptime", "uname ",
        "ollama list", "ollama ps",
        "journalctl -u klipper", "journalctl -u moonraker",
        "ping -c 3 ",
        "ip addr", "ip route",
        "tailscale status",
    ]

    dangerous = ["rm ", "dd ", "mkfs", "sudo rm", "> /dev/", "chmod 777",
                 "curl | sh", "wget | sh", "eval ", ";", "&&", "||", "`"]

    if any(d in cmd for d in dangerous):
        return json.dumps({"error": "Guvenlik: Tehlikeli komut reddedildi"})

    if not any(cmd.startswith(p) for p in allowed_prefixes):
        return json.dumps({"error": f"Guvenlik: '{cmd}' izin listesinde degil"})

    try:
        result = subprocess.run(
            cmd.split(), capture_output=True, text=True, timeout=30,
        )
        return json.dumps({
            "returncode": result.returncode,
            "output": result.stdout[:2048],
        })
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        return json.dumps({"error": str(e)})


def tool_tailscale_status():
    """Get Tailscale VPN status and connected peers."""
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return json.dumps({"error": "Tailscale calismiyor"})
        data = json.loads(result.stdout)
        self_node = data.get("Self", {})
        peers = data.get("Peer", {})
        ips = self_node.get("TailscaleIPs", [])
        online_peers = sum(1 for p in peers.values() if p.get("Online"))
        peer_list = [
            {"hostname": p.get("HostName", "?"),
             "ip": p.get("TailscaleIPs", ["?"])[0] if p.get("TailscaleIPs") else "?",
             "online": p.get("Online", False)}
            for p in peers.values()
        ]
        return json.dumps({
            "connected": self_node.get("Online", False),
            "hostname": self_node.get("HostName", "?"),
            "ip": ips[0] if ips else "?",
            "peers_online": online_peers,
            "peers": peer_list[:10],
        }, ensure_ascii=False, indent=2)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return json.dumps({"error": "Tailscale bulunamadi"})


# =============================================================================
# Register All Tools
# =============================================================================

def register_all_tools():
    # Printer tools
    register_tool("printer_status", "Yazici durumu (sicaklik, durum, ilerleme)", tool_printer_status)
    register_tool("printer_temps", "Nozul ve yatak sicakliklari", tool_printer_temps)
    register_tool("print_progress", "Baski ilerlemesi detayli", tool_print_progress)
    register_tool("pause_print", "Baski duraklat", tool_pause_print, requires_confirm=True)
    register_tool("resume_print", "Baski devam ettir", tool_resume_print, requires_confirm=True)
    register_tool("cancel_print", "Baski iptal et", tool_cancel_print, requires_confirm=True)
    register_tool(
        "send_gcode", "G-code komutu gonder",
        tool_send_gcode, requires_confirm=True, params={"gcode": "str"},
    )
    register_tool(
        "set_temp", "Isitici sicaklik ayarla",
        tool_set_temp, requires_confirm=True,
        params={"heater": "str (extruder/heater_bed)", "target": "int"},
    )
    register_tool(
        "adjust_speed", "Baski hiz faktoru ayarla (%)",
        tool_adjust_speed, params={"factor": "int (10-300)"},
    )
    register_tool("home_printer", "Tum eksenleri sifirla (G28)", tool_home_printer, requires_confirm=True)
    register_tool("list_gcode_files", "G-code dosyalarini listele", tool_list_gcode_files)
    register_tool("camera_snapshot", "Kamera/Crowsnest durumu", tool_camera_snapshot)
    register_tool("ai_monitor_status", "AI print monitor uyarilari", tool_ai_monitor_status)
    register_tool(
        "printer_config", "Klipper config dosyasi oku",
        tool_printer_config, params={"filename": "str (varsayilan: printer.cfg)"},
    )
    register_tool("list_macros", "Klipper makrolarini listele", tool_list_macros)

    # System tools
    register_tool("system_info", "Sistem bilgisi (CPU, RAM, disk)", tool_system_info)
    register_tool(
        "run_command", "Guvenli sistem komutu calistir",
        tool_run_command, requires_confirm=True, params={"cmd": "str"},
    )
    register_tool("tailscale_status", "Tailscale VPN durumu", tool_tailscale_status)


# =============================================================================
# Ollama Communication
# =============================================================================

def ollama_available():
    try:
        import urllib.request
        req = urllib.request.Request("http://localhost:11434/api/tags")
        with urllib.request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


def detect_best_model():
    global OLLAMA_MODEL
    if not shutil.which("ollama"):
        return OLLAMA_MODEL
    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return OLLAMA_MODEL
        output = result.stdout
        if OLLAMA_MODEL_AGENT in output:
            OLLAMA_MODEL = OLLAMA_MODEL_AGENT
            info(f"Agent modeli: {OLLAMA_MODEL_AGENT}")
        elif OLLAMA_MODEL_CODER in output:
            OLLAMA_MODEL = OLLAMA_MODEL_CODER
            warn(f"Coder modeli: {OLLAMA_MODEL_CODER}")
        else:
            # Fallback: try any available model
            for line in output.strip().split("\n")[1:]:
                parts = line.split()
                if parts:
                    OLLAMA_MODEL = parts[0]
                    info(f"Varsayilan model: {OLLAMA_MODEL}")
                    break
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return OLLAMA_MODEL


def ollama_chat(messages, model=None):
    """Send chat to Ollama API. Falls back to remote inference."""
    model = model or OLLAMA_MODEL
    payload = json.dumps({
        "model": model,
        "messages": messages,
        "stream": False,
        "options": {
            "temperature": 0.3,
            "top_p": 0.9,
            "num_predict": 2048,
        },
    })

    # Try local Ollama first
    try:
        import urllib.request
        req = urllib.request.Request(
            OLLAMA_API,
            data=payload.encode(),
            method="POST",
        )
        req.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read())
            return data.get("message", {}).get("content", "")
    except Exception:
        pass

    # Fallback: remote inference
    try:
        from tools.kos_remote_inference import RemoteInferenceClient
        client = RemoteInferenceClient()
        user_msg = messages[-1].get("content", "") if messages else ""
        response = client.chat_with_fallback(user_msg)
        return response
    except Exception:
        return None


# --- Tool Call Parsing ---

def parse_tool_calls(text):
    calls = []
    remaining = text

    json_pattern = r'\{[^{}]*"tool"\s*:\s*"[^"]+[^{}]*\}'
    matches = re.findall(json_pattern, text)

    for match in matches:
        try:
            obj = json.loads(match)
            if "tool" in obj:
                calls.append((obj["tool"], obj.get("params", {})))
                remaining = remaining.replace(match, "").strip()
        except json.JSONDecodeError:
            continue

    array_pattern = r'\[[\s\S]*?\{[^{}]*"tool"[^{}]*\}[\s\S]*?\]'
    for match in re.findall(array_pattern, text):
        try:
            arr = json.loads(match)
            for obj in arr:
                if isinstance(obj, dict) and "tool" in obj:
                    calls.append((obj["tool"], obj.get("params", {})))
            remaining = remaining.replace(match, "").strip()
        except json.JSONDecodeError:
            continue

    return calls, remaining


def confirm_action(tool_name, params):
    print(f"\n{YELLOW}[ONAY GEREKLI]{NC} {tool_name}")
    if params:
        print(f"  Parametreler: {json.dumps(params, ensure_ascii=False)}")
    try:
        answer = input("  Onayliyor musunuz? (e/h): ").strip().lower()
        return answer in ("e", "evet", "y", "yes")
    except (EOFError, KeyboardInterrupt):
        return False


def execute_tool_calls(calls):
    results = []
    for tool_name, params in calls:
        tool = find_tool(tool_name)
        if not tool:
            results.append(f"[Hata: '{tool_name}' araci bulunamadi]")
            continue

        if tool["requires_confirm"]:
            if not confirm_action(tool_name, params):
                results.append(f"[{tool_name}: Kullanici tarafindan reddedildi]")
                continue

        try:
            print(f"{DIM}  -> {tool_name} calistiriliyor...{NC}")
            result = tool["function"](**params)
            results.append(f"[{tool_name} sonucu]:\n{result}")
        except Exception as e:
            results.append(f"[{tool_name} hatasi]: {e}")

    return "\n".join(results)


# =============================================================================
# Agent Loop
# =============================================================================

def run_agent_loop():
    load_config()

    print("")
    print("=" * 48)
    print("  KlipperOS-AI Agent — 3D Yazici AI Asistani")
    print("  Cikis: 'q' veya Ctrl+C")
    print("=" * 48)
    print("")

    if not ollama_available():
        warn("Yerel Ollama bulunamadi. Uzak AI kullanilacak.")
    else:
        detect_best_model()
        print(f"  Model: {OLLAMA_MODEL}")

    register_all_tools()
    print(f"  Araclar: {len(TOOLS)} kayitli")
    print("")

    system_msg = SYSTEM_PROMPT + get_tools_prompt()
    messages = [{"role": "system", "content": system_msg}]

    while True:
        user_input = user_prompt()
        if user_input is None or user_input.lower() in ("q", "quit", "exit", "cik"):
            info("Agent kapatiliyor.")
            break
        if not user_input:
            continue

        messages.append({"role": "user", "content": user_input})

        print(f"{DIM}  Dusunuyor...{NC}")
        response = ollama_chat(messages)

        if response is None:
            error("Model yanit vermedi.")
            messages.pop()
            continue

        tool_calls, text_response = parse_tool_calls(response)

        if text_response:
            agent_say(text_response)

        if tool_calls:
            tool_results = execute_tool_calls(tool_calls)
            if tool_results:
                messages.append({"role": "assistant", "content": response})
                messages.append({"role": "user", "content":
                    f"Arac sonuclari:\n{tool_results}\n\nBu sonuclari yorumla ve Turkce acikla."
                })
                print(f"{DIM}  Sonuclari yorumluyor...{NC}")
                interpretation = ollama_chat(messages)
                if interpretation:
                    agent_say(interpretation)
                    messages.append({"role": "assistant", "content": interpretation})
                else:
                    print(tool_results)
                    messages.append({"role": "assistant", "content": tool_results})
        else:
            messages.append({"role": "assistant", "content": response})

        # Keep context manageable
        if len(messages) > 22:
            messages = [messages[0]] + messages[-20:]


def run_single_query(query):
    load_config()
    register_all_tools()

    system_msg = SYSTEM_PROMPT + get_tools_prompt()
    messages = [
        {"role": "system", "content": system_msg},
        {"role": "user", "content": query},
    ]

    response = ollama_chat(messages)
    if response is None:
        error("Model yanit vermedi.")
        sys.exit(1)

    tool_calls, text_response = parse_tool_calls(response)
    if text_response:
        print(text_response)

    if tool_calls:
        results = execute_tool_calls(tool_calls)
        if results:
            messages.append({"role": "assistant", "content": response})
            messages.append({"role": "user", "content":
                f"Arac sonuclari:\n{results}\n\nKisaca yorumla."
            })
            interpretation = ollama_chat(messages)
            if interpretation:
                print(interpretation)
            else:
                print(results)


def show_agent_status():
    register_all_tools()

    print(f"\n{'=' * 48}")
    print("  KlipperOS-AI Agent Durumu")
    print(f"{'=' * 48}\n")

    # Ollama
    if ollama_available():
        print(f"  Ollama:     {GREEN}Calisiyor{NC}")
        detect_best_model()
        print(f"  Model:      {OLLAMA_MODEL}")
    else:
        print(f"  Ollama:     {YELLOW}Calismiyor (uzak AI kullanilacak){NC}")

    # Moonraker
    mr = _moonraker_get("/server/info")
    if mr:
        print(f"  Moonraker:  {GREEN}Erisilebilir{NC}")
    else:
        print(f"  Moonraker:  {RED}Erisilemez{NC}")

    # Tools
    confirm_count = sum(1 for t in TOOLS if t["requires_confirm"])
    print(f"\n  Araclar ({len(TOOLS)} toplam, {confirm_count} onay gerekli):")
    for t in TOOLS:
        confirm = f" {YELLOW}[onay]{NC}" if t["requires_confirm"] else ""
        print(f"    - {t['name']}: {t['description']}{confirm}")
    print("")


# =============================================================================
# CLI
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog="kos-agent",
        description="KlipperOS-AI Agent — 3D yazici AI asistani (tool-calling)",
    )
    parser.add_argument("query", nargs="?", default=None, help="Tek seferlik soru")
    parser.add_argument("--status", action="store_true", help="Agent durumunu goster")
    parser.add_argument("--model", default=None, help="Ollama model adi")
    args = parser.parse_args()

    if args.model:
        global OLLAMA_MODEL
        OLLAMA_MODEL = args.model

    if args.status:
        show_agent_status()
    elif args.query:
        run_single_query(args.query)
    else:
        run_agent_loop()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{TAG} Kapatildi.")
