#!/usr/bin/env python3
"""KlipperOS-AI Chat Server.

Mainsail'e entegre AI sohbet terminali.
Ollama LLM + Moonraker yazici durumu birlestirerek
akilli 3D baski asistani sunar.

Port: 8085 (varsayilan)
Bagimliliklar: requests (pip), ollama (localhost:11434)
"""

import json
import logging
import os
import socket
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

import requests

# RAG bagimliliklari — yoksa graceful degradation
try:
    from knowledge_base import KnowledgeBase
    _kb_class = KnowledgeBase
except ImportError:
    _kb_class = None

# --- Yapilandirma ---
HOST = os.environ.get("AI_CHAT_HOST", "0.0.0.0")
PORT = int(os.environ.get("AI_CHAT_PORT", "8085"))
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434")
MOONRAKER_URL = os.environ.get("MOONRAKER_URL", "http://127.0.0.1:7125")
MODEL_NAME = os.environ.get("AI_MODEL", "klipperos-ai")
STATIC_DIR = Path(__file__).parent / "static"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("ai-chat")


# --- Moonraker Client ---

class PrinterContext:
    """Moonraker'dan yazici durumunu alir ve AI icin context olusturur."""

    def __init__(self, base_url: str = MOONRAKER_URL):
        self.base_url = base_url
        self._cache = {}
        self._cache_time = 0
        self._cache_ttl = 5  # 5 saniye cache

    def _query(self, endpoint: str, params: dict = None) -> dict:
        try:
            resp = requests.get(
                f"{self.base_url}{endpoint}",
                params=params,
                timeout=3,
            )
            resp.raise_for_status()
            return resp.json().get("result", {})
        except Exception as e:
            logger.debug("Moonraker sorgu hatasi: %s", e)
            return {}

    def get_status(self) -> dict:
        """Yazici durum bilgilerini al (cache'li)."""
        now = time.time()
        if now - self._cache_time < self._cache_ttl and self._cache:
            return self._cache

        status = {}

        # Yazici durumu
        info = self._query("/printer/info")
        status["state"] = info.get("state", "unknown")
        status["state_message"] = info.get("state_message", "")

        # Sicakliklar
        objects = self._query(
            "/printer/objects/query",
            {"extruder": "temperature,target", "heater_bed": "temperature,target"},
        )
        obj_status = objects.get("status", {})

        ext = obj_status.get("extruder", {})
        status["extruder_temp"] = ext.get("temperature", 0)
        status["extruder_target"] = ext.get("target", 0)

        bed = obj_status.get("heater_bed", {})
        status["bed_temp"] = bed.get("temperature", 0)
        status["bed_target"] = bed.get("target", 0)

        # Baski durumu
        print_stats = self._query(
            "/printer/objects/query",
            {"print_stats": "state,filename,total_duration,print_duration"},
        )
        ps = print_stats.get("status", {}).get("print_stats", {})
        status["print_state"] = ps.get("state", "standby")
        status["filename"] = ps.get("filename", "")
        status["print_duration"] = ps.get("print_duration", 0)

        # Pozisyon
        motion = self._query(
            "/printer/objects/query",
            {"gcode_move": "gcode_position,speed"},
        )
        gm = motion.get("status", {}).get("gcode_move", {})
        pos = gm.get("gcode_position", [0, 0, 0, 0])
        status["position"] = {"x": pos[0], "y": pos[1], "z": pos[2]}
        status["speed"] = gm.get("speed", 0)

        self._cache = status
        self._cache_time = now
        return status

    def get_detailed_status(self) -> dict:
        """Genisletilmis yazici durumunu al (fan, progress dahil)."""
        status = self.get_status()

        # Ek bilgiler — i7'de context genisligi yeterli
        extra = self._query(
            "/printer/objects/query",
            {
                "fan": "speed",
                "display_status": "progress,message",
                "virtual_sdcard": "progress,file_position",
                "system_stats": "cpufreq,cputemp,memavail",
            },
        )
        extra_s = extra.get("status", {})

        fan = extra_s.get("fan", {})
        status["fan_speed"] = fan.get("speed", 0)

        disp = extra_s.get("display_status", {})
        status["progress"] = disp.get("progress", 0)

        sys_stats = extra_s.get("system_stats", {})
        status["cpu_temp"] = sys_stats.get("cputemp", 0)
        status["mem_avail"] = sys_stats.get("memavail", 0)

        return status

    def build_system_prompt(self, minimal: bool = False, rag_context: str = "") -> str:
        """AI icin system prompt olustur.

        Prompt token sayisi dogrudan ilk-yanit suresini etkiler.
        i7 M640'da her 100 token ~32s prompt eval suresi demek.
        Bu yuzden kompakt tutmak kritik.

        Args:
            minimal: True ise (Atom gibi yavas HW), ultra-kisa prompt.
            rag_context: RAG bilgi bankasi sonuclari (bos ise atlanir).
        """
        if minimal:
            return "3D yazici asistani. Kisa cevap ver. Turkce."

        # Kompakt system role (~15 token)
        prompt = "3D yazici/Klipper uzmani. Turkce kisa yanit ver.\n"

        # Yazici durumu — sadece aktifse detay goster
        status = self.get_detailed_status()
        state = status.get("state", "unknown")
        ps = status.get("print_state", "standby")

        if ps != "standby":
            # Baski aktif — detayli durum ekle
            et = status.get("extruder_temp", 0)
            bt = status.get("bed_temp", 0)
            progress = status.get("progress", 0) * 100
            prompt += f"Yazici: {ps}"
            if status.get("filename"):
                prompt += f" {status['filename']}"
            if progress > 0:
                prompt += f" %{progress:.0f}"
            prompt += f" N={et:.0f}C T={bt:.0f}C\n"
        elif state not in ("ready", "unknown"):
            # Hata durumu — kisa bildir (uzun hata mesajlari token israfi)
            msg = status.get("state_message", "")
            if msg:
                # Sadece ilk satiri al, max 60 karakter
                msg = msg.split("\n")[0][:60]
            prompt += f"Yazici: {state}"
            if msg:
                prompt += f" ({msg})"
            prompt += "\n"
        # state=ready ve standby ise: yazici bilgisi ekleme (token tasarrufu)

        # RAG context (bilgi bankasi sonuclari)
        if rag_context:
            prompt += rag_context
            prompt += "\nEn alakali kaynagi kullan.\n"

        return prompt


# --- Ollama Client ---

class OllamaClient:
    """Ollama API istemcisi — streaming destekli."""

    def __init__(self, base_url: str = OLLAMA_URL, model: str = MODEL_NAME):
        self.base_url = base_url
        self.model = model

    def is_available(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:
            return False

    def get_models(self) -> list:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=5)
            data = resp.json()
            return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def _get_options(self) -> dict:
        """Model ve donanima gore uygun Ollama parametreleri.

        i7 M640 (no AVX, 2C/4T, 4MB L3):
        - num_ctx=1024: KV cache kucuk, prompt eval hizli
        - num_predict=256: cogu 3D yazici cevabi icin yeterli
        - num_thread=4: HT bu CPU'da %10 fayda sagliyor (benchmark sonucu)
        """
        if "smollm" in self.model:
            # Atom N455: 1 core, 1.9GB RAM — dusuk profil
            return {
                "temperature": 0.7,
                "top_p": 0.9,
                "num_predict": 64,
                "num_ctx": 512,
                "num_thread": 1,
                "repeat_penalty": 1.1,
            }
        # i7 / guclu donanim — optimize profil
        return {
            "temperature": 0.7,
            "top_p": 0.9,
            "num_predict": 256,
            "num_ctx": 1024,
            "num_thread": 4,
            "repeat_penalty": 1.1,
        }

    def chat_stream(self, messages: list, system: str = ""):
        """Streaming chat — yield ile token token dondurur."""
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": True,
            "options": self._get_options(),
        }
        if system:
            payload["messages"] = [{"role": "system", "content": system}] + messages

        # qwen3: think modunu devre disi birak (performans icin)
        # Yeni Ollama API'si "think" parametresi ile kontrol ediyor
        if "qwen3" in self.model:
            payload["think"] = False

        logger.info("Ollama istek: model=%s, msg_count=%d, system_len=%d",
                     self.model, len(payload["messages"]), len(system))

        try:
            resp = requests.post(
                f"{self.base_url}/api/chat",
                json=payload,
                stream=True,
                timeout=300,
            )
            resp.raise_for_status()
            logger.info("Ollama yanit basladi: HTTP %d", resp.status_code)

            for line in resp.iter_lines():
                if line:
                    data = json.loads(line)
                    msg = data.get("message", {})
                    content = msg.get("content", "")
                    if content:
                        yield content
                    if data.get("done"):
                        break
        except Exception as e:
            yield f"\n[Hata: {e}]"


# --- HTTP Handler ---

class AIChatHandler(SimpleHTTPRequestHandler):
    """AI Chat HTTP istek isleyicisi."""

    protocol_version = "HTTP/1.1"

    printer_ctx = PrinterContext()
    ollama = OllamaClient()
    knowledge_base = _kb_class() if _kb_class else None

    def setup(self):
        """TCP_NODELAY + unbuffered wfile — SSE icin kritik."""
        super().setup()
        # Nagle algoritmasini devre disi birak (kucuk paketler hemen gidsin)
        self.connection.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        # wfile'i unbuffered yap (her write dogrudan socket'e)
        self.wfile = self.connection.makefile("wb", buffering=0)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(STATIC_DIR), **kwargs)

    def log_message(self, format, *args):
        logger.info(format % args)

    def do_GET(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/status":
            self._handle_status()
        elif parsed.path == "/api/printer":
            self._handle_printer_status()
        elif parsed.path == "/api/quick-status":
            self._handle_quick_status()
        elif parsed.path == "/api/models":
            self._handle_models()
        else:
            # Statik dosyalari sun
            super().do_GET()

    def do_POST(self):
        parsed = urlparse(self.path)

        if parsed.path == "/api/chat":
            self._handle_chat()
        else:
            self.send_error(404)

    def _send_json(self, data: dict, status: int = 200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", len(body))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def _handle_status(self):
        """AI sistem durumu."""
        ollama_ok = self.ollama.is_available()
        printer = self.printer_ctx.get_status()
        rag_stats = self.knowledge_base.get_stats() if self.knowledge_base else {"available": False}
        self._send_json({
            "ollama": ollama_ok,
            "model": MODEL_NAME,
            "printer_state": printer.get("state", "unknown"),
            "print_state": printer.get("print_state", "standby"),
            "rag": rag_stats,
        })

    def _handle_printer_status(self):
        """Yazici durum detayi."""
        self._send_json(self.printer_ctx.get_status())

    def _handle_quick_status(self):
        """Hizli yazici durum ozeti — AI modeline gitmeden, dogrudan Moonraker.

        Atom N455 gibi yavas donanımlarda AI cevabi 2-4 dakika surer.
        Bu endpoint, anlik yazici durumunu formatli metin olarak dondurur.
        Widget'taki quick-action butonlari bunu kullanir.
        """
        status = self.printer_ctx.get_detailed_status()

        state = status.get("state") or "unknown"
        state_msg = status.get("state_message") or ""
        et = status.get("extruder_temp") or 0
        et_t = status.get("extruder_target") or 0
        bt = status.get("bed_temp") or 0
        bt_t = status.get("bed_target") or 0
        ps = status.get("print_state") or "standby"
        fan = status.get("fan_speed") or 0

        lines = []
        lines.append(f"📊 **Yazici Durumu: {state.upper()}**")
        if state_msg:
            lines.append(f"   {state_msg}")
        lines.append("")

        # Sicakliklar
        nozul = f"🌡️ Nozul: {et:.0f}°C"
        if et_t > 0:
            nozul += f" → hedef {et_t:.0f}°C"
        lines.append(nozul)

        tabla = f"🛏️ Tabla: {bt:.0f}°C"
        if bt_t > 0:
            tabla += f" → hedef {bt_t:.0f}°C"
        lines.append(tabla)

        # Fan
        if fan > 0:
            lines.append(f"💨 Fan: %{fan*100:.0f}")

        # Baski durumu
        lines.append("")
        if ps == "printing":
            progress = status.get("progress", 0) * 100
            fname = status.get("filename", "bilinmiyor")
            dur = status.get("print_duration", 0)
            mins = int(dur // 60)
            lines.append(f"🖨️ Baski: {fname}")
            lines.append(f"   İlerleme: %{progress:.0f} — {mins} dakika")
        elif ps == "paused":
            lines.append("⏸️ Baski duraklatildi")
        else:
            lines.append("⏹️ Baski yok (standby)")

        # Pozisyon
        pos = status.get("position", {})
        if any(pos.get(k, 0) != 0 for k in ("x", "y", "z")):
            lines.append(f"📐 Pozisyon: X={pos.get('x',0):.1f} Y={pos.get('y',0):.1f} Z={pos.get('z',0):.1f}")

        # Sistem
        cpu_t = status.get("cpu_temp") or 0
        mem = status.get("mem_avail") or 0
        if cpu_t > 0 or mem > 0:
            lines.append("")
            if cpu_t > 0:
                lines.append(f"🔥 CPU Sicaklik: {cpu_t:.0f}°C")
            if mem > 0:
                lines.append(f"💾 Bos RAM: {mem/1024:.0f} MB")

        self._send_json({"text": "\n".join(lines)})

    def _handle_models(self):
        """Mevcut Ollama modelleri."""
        models = self.ollama.get_models()
        self._send_json({"models": models, "active": MODEL_NAME})

    def _handle_chat(self):
        """Streaming AI chat — SSE (Server-Sent Events)."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)

        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            self._send_json({"error": "Gecersiz JSON"}, 400)
            return

        messages = data.get("messages", [])
        if not messages:
            self._send_json({"error": "Mesaj gerekli"}, 400)
            return

        # RAG context olustur (sadece guclu modelde)
        rag_context = ""
        use_minimal = "smollm" in MODEL_NAME
        if not use_minimal and self.knowledge_base and self.knowledge_base.available:
            user_query = messages[-1].get("content", "") if messages else ""
            if user_query:
                rag_context = self.knowledge_base.build_context(user_query)
                if rag_context:
                    logger.debug("RAG context: %d karakter", len(rag_context))

        # System prompt
        system_prompt = self.printer_ctx.build_system_prompt(
            minimal=use_minimal, rag_context=rag_context
        )

        # System prompt boyutu loglama
        logger.info("Chat: %d mesaj, system_prompt=%d karakter, rag_context=%d karakter",
                     len(messages), len(system_prompt), len(rag_context))

        # SSE stream baslat
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()

        # Header'lari ve heartbeat'i hemen gonder
        # (Ollama cevap verene kadar client beklesin, baglanti canli)
        self.wfile.write(b": stream-start\n\n")
        self.wfile.flush()

        try:
            full_response = ""
            token_count = 0
            for token in self.ollama.chat_stream(messages, system=system_prompt):
                # /think bloklarini filtrele
                if "<think>" in full_response and "</think>" not in full_response:
                    full_response += token
                    if "</think>" in full_response:
                        # think blogu bitti, icerigi atla
                        idx = full_response.index("</think>") + len("</think>")
                        remaining = full_response[idx:].lstrip("\n")
                        if remaining:
                            event = f"data: {json.dumps({'token': remaining})}\n\n"
                            self.wfile.write(event.encode("utf-8"))
                            self.wfile.flush()
                    continue

                if "<think>" in token:
                    full_response += token
                    continue

                full_response += token
                token_count += 1
                event = f"data: {json.dumps({'token': token})}\n\n"
                self.wfile.write(event.encode("utf-8"))
                self.wfile.flush()

            # Stream bitti sinyali
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
            logger.info("Chat tamamlandi: %d token", token_count)

        except (BrokenPipeError, ConnectionResetError):
            logger.debug("Client baglantisi kesildi")
        except Exception as e:
            logger.error("Chat stream hatasi: %s", e)
            error_event = f"data: {json.dumps({'error': str(e)})}\n\n"
            try:
                self.wfile.write(error_event.encode("utf-8"))
                self.wfile.flush()
            except Exception:
                pass

    def do_OPTIONS(self):
        """CORS preflight."""
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()


# --- Main ---

def main():
    logger.info("KlipperOS-AI Chat Server baslatiliyor...")
    logger.info("  Adres: http://%s:%d", HOST, PORT)
    logger.info("  Ollama: %s (model: %s)", OLLAMA_URL, MODEL_NAME)
    logger.info("  Moonraker: %s", MOONRAKER_URL)

    # Ollama kontrolu
    ollama = OllamaClient()
    if ollama.is_available():
        models = ollama.get_models()
        logger.info("  Ollama modelleri: %s", models)
    else:
        logger.warning("  Ollama erisilemedi! Chat calismayacak.")

    # RAG kontrolu
    if _kb_class:
        kb = AIChatHandler.knowledge_base
        if kb and kb.available:
            logger.info("  RAG: Aktif (bagimlillik mevcut, lazy init)")
        else:
            logger.info("  RAG: Bagimliliklar eksik, devre disi")
    else:
        logger.info("  RAG: knowledge_base modulu bulunamadi, devre disi")

    server = ThreadingHTTPServer((HOST, PORT), AIChatHandler)
    server.daemon_threads = True

    logger.info("Server hazir. Istekler bekleniyor...")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Kapatiliyor...")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
