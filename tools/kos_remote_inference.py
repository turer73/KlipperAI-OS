"""
KlipperOS-AI — Remote AI Inference via Tailscale Mesh Network
==============================================================
Dusuk kaynak SBC'lerin (Raspberry Pi, 512MB-2GB RAM) AI sorgularini
Tailscale VPN mesh uzerinden guclu bir makineye yonlendirmesini saglar.

Fallback zinciri: Uzak Ollama (Tailscale) -> Yerel Ollama -> Kural tabanli

Kullanim:
    kos-remote discover           # Tailscale aginda Ollama sunuculari bul
    kos-remote health [url]       # Sunucu saglik kontrolu
    kos-remote chat "mesaj"       # En iyi sunucuya sorgu gonder
    kos-remote status             # Konfigurasyon ve baglanti durumu
"""

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request

import yaml

# --- Constants ---

TAG = "[kos-remote]"
GREEN = "\033[0;32m"
YELLOW = "\033[1;33m"
RED = "\033[0;31m"
CYAN = "\033[0;36m"
DIM = "\033[2m"
NC = "\033[0m"

AGENT_CONFIG_PATH = "/etc/klipperos-ai/ai-agent.yml"
MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")
OLLAMA_PORT = 11434
DISCOVERY_CACHE_SEC = 300
REMOTE_TIMEOUT_SEC = 10
LOCAL_TIMEOUT_SEC = 30


# --- Output helpers ---

def info(msg):
    print(f"{GREEN}{TAG}{NC} {msg}")


def warn(msg):
    print(f"{YELLOW}{TAG}{NC} {msg}")


def error(msg):
    print(f"{RED}{TAG}{NC} {msg}")


# --- Remote Inference Client ---

class RemoteInferenceClient:
    """Client for offloading AI inference to remote Ollama over Tailscale."""

    def __init__(self, config_path=AGENT_CONFIG_PATH):
        self._config_path = config_path
        self._config = {}
        self._remote_cfg = {}
        self._cached_servers = []
        self._cache_time = 0.0
        self._load_config()

    def _load_config(self):
        try:
            if os.path.exists(self._config_path):
                with open(self._config_path, "r") as f:
                    self._config = yaml.safe_load(f) or {}
        except (yaml.YAMLError, IOError) as exc:
            warn(f"Konfigurasyon okunamadi: {exc}")
            self._config = {}
        self._remote_cfg = self._config.get("remote_inference", {})

    @property
    def enabled(self):
        return self._remote_cfg.get("enabled", True)

    @property
    def discovery_interval(self):
        return self._remote_cfg.get("discovery_interval_sec", DISCOVERY_CACHE_SEC)

    @property
    def preferred_server(self):
        return self._remote_cfg.get("preferred_server", "")

    @property
    def timeout(self):
        return self._remote_cfg.get("timeout_sec", REMOTE_TIMEOUT_SEC)

    @property
    def fallback_local(self):
        return self._remote_cfg.get("fallback_to_local", True)

    @property
    def fallback_rules(self):
        return self._remote_cfg.get("fallback_to_rules", True)

    def _default_model(self):
        agent_cfg = self._config.get("agent", {})
        return agent_cfg.get("model_primary", "klipperos-ai-agent")

    # --- Tailscale discovery ---

    def _get_tailscale_peers(self):
        """Run tailscale status --json and return online peer list."""
        try:
            result = subprocess.run(
                ["tailscale", "status", "--json"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode != 0 or not result.stdout:
                return []
            data = json.loads(result.stdout)
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            return []

        peers = []
        for peer in data.get("Peer", {}).values():
            if not peer.get("Online", False):
                continue
            ts_ips = peer.get("TailscaleIPs", [])
            if not ts_ips:
                continue
            ip = ts_ips[0]
            for addr in ts_ips:
                if "." in addr:
                    ip = addr
                    break
            peers.append({
                "hostname": peer.get("HostName", "unknown"),
                "ip": ip,
                "os": peer.get("OS", "?"),
            })
        return peers

    def _probe_ollama(self, ip):
        """Probe a peer IP for Ollama on port 11434."""
        url = f"http://{ip}:{OLLAMA_PORT}"
        tags_url = f"{url}/api/tags"
        start = time.monotonic()
        try:
            req = urllib.request.Request(tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=3) as resp:
                body = resp.read(8192)
            elapsed = (time.monotonic() - start) * 1000
            data = json.loads(body)
            models = [m.get("name", "unknown") for m in data.get("models", [])]
            return {
                "url": url, "ip": ip, "models": models,
                "latency_ms": round(elapsed, 1),
            }
        except (urllib.error.URLError, urllib.error.HTTPError,
                OSError, json.JSONDecodeError, ValueError):
            return None

    def discover_servers(self):
        """Find Ollama servers on Tailscale mesh. Results cached."""
        now = time.monotonic()
        if self._cached_servers and (now - self._cache_time) < self.discovery_interval:
            return self._cached_servers

        peers = self._get_tailscale_peers()
        if not peers:
            self._cached_servers = []
            self._cache_time = now
            return []

        servers = []
        for peer in peers:
            result = self._probe_ollama(peer["ip"])
            if result is not None:
                result["hostname"] = peer["hostname"]
                result["os"] = peer["os"]
                servers.append(result)

        servers.sort(key=lambda s: s["latency_ms"])
        self._cached_servers = servers
        self._cache_time = now
        return servers

    def get_best_server(self):
        """Return URL of the fastest healthy server, or None."""
        if self.preferred_server:
            pref_url = f"http://{self.preferred_server}:{OLLAMA_PORT}"
            hc = self.health_check(pref_url)
            if hc.get("healthy"):
                return pref_url

        servers = self.discover_servers()
        if servers:
            return servers[0]["url"]
        return None

    # --- Health check ---

    def health_check(self, server_url):
        tags_url = f"{server_url}/api/tags"
        start = time.monotonic()
        try:
            req = urllib.request.Request(tags_url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as resp:
                body = resp.read(8192)
            elapsed = (time.monotonic() - start) * 1000
            data = json.loads(body)
            models = [m.get("name", "?") for m in data.get("models", [])]
            return {"healthy": True, "url": server_url, "models": models,
                    "latency_ms": round(elapsed, 1)}
        except (urllib.error.URLError, urllib.error.HTTPError,
                OSError, json.JSONDecodeError, ValueError) as exc:
            return {"healthy": False, "url": server_url, "models": [],
                    "latency_ms": -1, "error": str(exc)}

    # --- Chat ---

    def chat(self, messages, model=None, server_url=None):
        if server_url is None:
            server_url = self.get_best_server()
        if server_url is None:
            return None
        if model is None:
            model = self._default_model()

        chat_url = f"{server_url}/api/chat"
        payload = json.dumps({
            "model": model, "messages": messages, "stream": False,
            "options": {"temperature": 0.3, "top_p": 0.9, "num_predict": 2048},
        }).encode("utf-8")

        try:
            req = urllib.request.Request(
                chat_url, data=payload, method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                body = resp.read(65536)
            data = json.loads(body)
            return data.get("message", {}).get("content", "")
        except (urllib.error.URLError, urllib.error.HTTPError,
                OSError, json.JSONDecodeError, ValueError):
            return None

    def _local_chat(self, messages, model=None):
        if model is None:
            model = self._default_model()
        payload = json.dumps({
            "model": model, "messages": messages, "stream": False,
            "options": {"temperature": 0.3, "top_p": 0.9, "num_predict": 2048},
        })
        try:
            result = subprocess.run(
                ["curl", "-s", "-X", "POST",
                 f"http://localhost:{OLLAMA_PORT}/api/chat",
                 "-H", "Content-Type: application/json", "-d", payload],
                capture_output=True, text=True, timeout=LOCAL_TIMEOUT_SEC,
            )
            if result.returncode == 0 and result.stdout:
                data = json.loads(result.stdout)
                return data.get("message", {}).get("content", "")
        except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
            pass
        return None

    def chat_with_fallback(self, messages, model=None):
        """Try remote -> local -> rules fallback chain.

        Returns: (response_text, backend_used)
        """
        if self.enabled:
            info("Uzak sunucu deneniyor...")
            response = self.chat(messages, model=model)
            if response:
                info("Yanit: uzak sunucu (Tailscale)")
                return response, "remote"
            warn("Uzak sunucu yanitlamadi.")

        if self.fallback_local:
            info("Yerel Ollama deneniyor...")
            response = self._local_chat(messages, model=model)
            if response:
                info("Yanit: yerel Ollama")
                return response, "local"
            warn("Yerel Ollama yanitlamadi.")

        if self.fallback_rules:
            user_msg = ""
            for m in reversed(messages):
                if m.get("role") == "user":
                    user_msg = m.get("content", "")
                    break
            response = self._rules_fallback(user_msg)
            info("Yanit: kural tabanli (AI yok)")
            return response, "rules"

        return "AI sunucusu bulunamadi.", "none"

    # --- Rules-based fallback (3D yazici odakli) ---

    def _rules_fallback(self, user_message):
        """Keyword-based responses for printer queries when no AI is available."""
        msg = user_message.lower()

        # Yazici durumu
        if any(kw in msg for kw in ("yazici", "printer", "durum", "status")):
            return self._moonraker_query(
                "/printer/objects/query?print_stats&extruder&heater_bed",
                "Yazici durumu alinamadi. Moonraker calisiyor mu?",
            )

        # Sicaklik
        if any(kw in msg for kw in ("sicaklik", "temp", "nozul", "nozzle", "yatak", "bed")):
            return self._moonraker_query(
                "/printer/objects/query?extruder=temperature,target&heater_bed=temperature,target",
                "Sicaklik bilgisi alinamadi.",
            )

        # Baski ilerlemesi
        if any(kw in msg for kw in ("ilerleme", "progress", "baski", "print")):
            return self._moonraker_query(
                "/printer/objects/query?print_stats=state,filename,print_duration",
                "Baski ilerlemesi alinamadi.",
            )

        # RAM info
        if any(kw in msg for kw in ("ram", "bellek", "memory")):
            return self._run_fallback_cmd(["free", "-h"], "Bellek bilgisi okunamadi.")

        # Disk info
        if "disk" in msg:
            return self._run_fallback_cmd(["df", "-h"], "Disk bilgisi okunamadi.")

        # Servis listesi
        if any(kw in msg for kw in ("servis", "service")):
            return self._run_fallback_cmd(
                ["systemctl", "list-units", "--type=service",
                 "--state=running", "--no-pager", "--no-legend"],
                "Servis listesi alinamadi.",
            )

        return ("Bu soruyu yanitlamak icin AI sunucusu gerekli. "
                "Tailscale ile bagli bir Ollama sunucusuna baglanin.\n"
                "  kos-remote discover  # sunuculari bul\n"
                "  kos-remote status    # baglanti durumu")

    def _moonraker_query(self, endpoint, error_msg):
        """Query Moonraker API and return formatted result."""
        try:
            import requests
            resp = requests.get(f"{MOONRAKER_URL}{endpoint}", timeout=5)
            if resp.status_code == 200:
                return json.dumps(resp.json().get("result", {}), indent=2, ensure_ascii=False)
        except Exception:
            pass
        return error_msg

    @staticmethod
    def _run_fallback_cmd(cmd_args, error_msg):
        try:
            result = subprocess.run(
                cmd_args, capture_output=True, text=True, timeout=5,
            )
            output = result.stdout.strip()
            if result.returncode == 0 and output:
                return output[:4096]
            return error_msg
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return error_msg


# --- CLI Commands ---

def cmd_discover(client):
    info("Tailscale aginda Ollama sunuculari araniyor...")
    servers = client.discover_servers()
    if not servers:
        warn("Hicbir Ollama sunucusu bulunamadi.")
        warn("  1. Tailscale bagli mi? (tailscale status)")
        warn("  2. Uzak makinede Ollama calisiyor mu? (ollama serve)")
        warn("  3. Port 11434 acik mi?")
        return
    info(f"{len(servers)} sunucu bulundu:\n")
    for i, srv in enumerate(servers, 1):
        models_str = ", ".join(srv["models"][:5]) if srv["models"] else "model yok"
        print(f"  {i}. {srv['hostname']} ({srv['ip']})")
        print(f"     OS: {srv['os']}  Gecikme: {srv['latency_ms']:.0f}ms")
        print(f"     Modeller: {models_str}")
        print(f"     URL: {srv['url']}\n")


def cmd_health(client, server_url=None):
    if server_url is None:
        server_url = client.get_best_server()
        if server_url is None:
            error("Bagli sunucu bulunamadi. Once: kos-remote discover")
            return
    info(f"Saglik kontrolu: {server_url}")
    hc = client.health_check(server_url)
    if hc["healthy"]:
        print(f"  Durum:    {GREEN}Saglikli{NC}")
        print(f"  Gecikme:  {hc['latency_ms']:.0f}ms")
        models_str = ", ".join(hc["models"][:10]) if hc["models"] else "yok"
        print(f"  Modeller: {models_str}")
    else:
        print(f"  Durum:    {RED}Erisilemiyor{NC}")
        print(f"  Hata:     {hc.get('error', 'bilinmiyor')}")


def cmd_chat(client, message):
    messages = [
        {"role": "system", "content":
         "Sen KlipperOS-AI asistanisin. 3D yazici ve Klipper konusunda uzmansin. Turkce kisa ve net cevap ver."},
        {"role": "user", "content": message},
    ]
    response, backend = client.chat_with_fallback(messages)
    print(f"\n{CYAN}AI ({backend}):{NC} {response}")


def cmd_status(client):
    print(f"\n{'=' * 50}")
    print("  KlipperOS-AI Uzak Cikarsama (Remote Inference)")
    print(f"{'=' * 50}\n")

    print(f"  Konfigurasyon: {client._config_path}")
    print(f"  Etkin:         {'Evet' if client.enabled else 'Hayir'}")
    print(f"  Tercih edilen: {client.preferred_server or '(otomatik)'}")
    print(f"  Zaman asimi:   {client.timeout}s")
    print(f"  Yerel fallback: {'Evet' if client.fallback_local else 'Hayir'}")
    print(f"  Kural fallback: {'Evet' if client.fallback_rules else 'Hayir'}\n")

    # Tailscale status
    print("  Tailscale:")
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0 and result.stdout:
            data = json.loads(result.stdout)
            self_node = data.get("Self", {})
            ts_ips = self_node.get("TailscaleIPs", [])
            online = self_node.get("Online", False)
            peer_count = len(data.get("Peer", {}))
            status_str = f"{GREEN}Bagli{NC}" if online else f"{RED}Bagli degil{NC}"
            print(f"    Durum:    {status_str}")
            print(f"    Hostname: {self_node.get('HostName', '?')}")
            if ts_ips:
                print(f"    IP:       {ts_ips[0]}")
            print(f"    Peer:     {peer_count} cihaz")
        else:
            print(f"    Durum:    {RED}Calismiyor{NC}")
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        print(f"    Durum:    {RED}tailscale bulunamadi{NC}")

    # Discovered servers
    print("\n  Ollama Sunuculari:")
    servers = client.discover_servers()
    if servers:
        for srv in servers:
            model_count = len(srv.get("models", []))
            print(f"    {GREEN}*{NC} {srv['hostname']} ({srv['ip']}) "
                  f"- {srv['latency_ms']:.0f}ms, {model_count} model")
    else:
        print(f"    {YELLOW}Sunucu bulunamadi{NC}")

    # Local Ollama
    print("\n  Yerel Ollama:")
    try:
        req = urllib.request.Request(
            f"http://localhost:{OLLAMA_PORT}/api/tags", method="GET")
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = resp.read(8192)
        data = json.loads(body)
        model_names = [m.get("name", "?") for m in data.get("models", [])]
        print(f"    Durum:    {GREEN}Calisiyor{NC}")
        if model_names:
            print(f"    Modeller: {', '.join(model_names[:8])}")
    except (urllib.error.URLError, urllib.error.HTTPError,
            OSError, json.JSONDecodeError, ValueError):
        print(f"    Durum:    {YELLOW}Calismiyor{NC}")
    print()


# --- CLI entry point ---

def main():
    parser = argparse.ArgumentParser(
        prog="kos-remote",
        description="KlipperOS-AI: Tailscale uzerinden uzak AI cikarsama",
    )
    sub = parser.add_subparsers(dest="command", help="Komutlar")

    sub.add_parser("discover", help="Tailscale aginda Ollama sunuculari bul")

    p_health = sub.add_parser("health", help="Sunucu saglik kontrolu")
    p_health.add_argument("server_url", nargs="?", default=None,
                          help="Sunucu URL (ornek: http://100.64.0.5:11434)")

    p_chat = sub.add_parser("chat", help="AI sorgula")
    p_chat.add_argument("message", help="Sorgu metni")
    p_chat.add_argument("--model", default=None, help="Ollama model adi")

    sub.add_parser("status", help="Konfigurasyon ve baglanti durumu")

    args = parser.parse_args()
    client = RemoteInferenceClient()

    if args.command == "discover":
        cmd_discover(client)
    elif args.command == "health":
        cmd_health(client, args.server_url)
    elif args.command == "chat":
        cmd_chat(client, args.message)
    elif args.command == "status":
        cmd_status(client)
    else:
        parser.print_help()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{TAG} Kapatildi.")
