# ks-panels/kos_ai_chat.py
"""KlipperOS-AI — AI Chat Panel for KlipperScreen.

Touch-friendly chat interface that communicates with local Ollama.
Supports streaming responses and 3D printing context.
"""

import logging
import json
import threading
import urllib.request
import urllib.error

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango
from ks_includes.screen_panel import ScreenPanel

logger = logging.getLogger("KOS-AIChat")

OLLAMA_URL = "http://127.0.0.1:11434"
DEFAULT_MODEL = "qwen3:1.7b"
SYSTEM_PROMPT = (
    "Sen KlipperOS-AI 3D yazici asistanisin. Turkce yanit ver. "
    "Klipper firmware, baski ayarlari, filament, kalibrasyon ve "
    "3D yazici sorunlari hakkinda yardimci ol. Kisa ve net yanit ver."
)


class Panel(ScreenPanel):
    """KlipperScreen AI Chat panel with streaming Ollama support."""

    def __init__(self, screen, title):
        title = title or "AI Asistan"
        super().__init__(screen, title)

        self._messages = []
        self._is_generating = False
        self._current_model = DEFAULT_MODEL
        self._response_buffer = ""
        self._ai_bubble_frame = None

        self._build_ui()

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # --- Header bar ---
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        header.set_margin_top(5)
        header.set_margin_start(8)
        header.set_margin_end(8)
        header.set_margin_bottom(5)

        # Model selector
        self._model_combo = Gtk.ComboBoxText()
        self._model_combo.set_size_request(140, -1)
        self._populate_models()
        header.pack_end(self._model_combo, False, False, 0)

        model_label = Gtk.Label(label="Model:")
        header.pack_end(model_label, False, False, 0)

        # Clear button
        clear_btn = self._gtk.Button("refresh", "Temizle", "color2")
        clear_btn.connect("clicked", self._on_clear)
        header.pack_end(clear_btn, False, False, 5)

        main_box.pack_start(header, False, False, 0)
        main_box.pack_start(Gtk.Separator(), False, False, 0)

        # --- Chat area ---
        self._chat_scroll = self._gtk.ScrolledWindow()
        self._chat_scroll.set_policy(
            Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC
        )
        self._chat_scroll.set_vexpand(True)

        self._chat_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL, spacing=8
        )
        self._chat_box.set_margin_top(8)
        self._chat_box.set_margin_start(8)
        self._chat_box.set_margin_end(8)
        self._chat_box.set_margin_bottom(8)

        # Welcome message
        welcome = self._make_bubble(
            "Merhaba! Ben KlipperOS-AI asistaniyim. "
            "3D yazici, Klipper ayarlari ve baski sorunlari "
            "hakkinda sorularinizi yanitlayabilirim.",
            is_user=False,
        )
        self._chat_box.pack_start(welcome, False, False, 0)

        self._chat_scroll.add(self._chat_box)
        main_box.pack_start(self._chat_scroll, True, True, 0)
        main_box.pack_start(Gtk.Separator(), False, False, 0)

        # --- Input area ---
        input_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        input_box.set_margin_top(5)
        input_box.set_margin_start(8)
        input_box.set_margin_end(8)
        input_box.set_margin_bottom(8)

        self._entry = Gtk.Entry()
        self._entry.set_placeholder_text("Mesajinizi yazin...")
        self._entry.set_hexpand(True)
        self._entry.connect("activate", self._on_send)
        font_desc = Pango.FontDescription("sans 13")
        self._entry.override_font(font_desc)
        input_box.pack_start(self._entry, True, True, 0)

        self._send_btn = self._gtk.Button("arrow-right", "Gonder", "color1")
        self._send_btn.set_size_request(80, 45)
        self._send_btn.connect("clicked", self._on_send)
        input_box.pack_start(self._send_btn, False, False, 0)

        # Status label
        self._status = Gtk.Label(label="")
        self._status.set_halign(Gtk.Align.START)
        self._status.set_margin_start(8)

        main_box.pack_start(input_box, False, False, 0)
        main_box.pack_start(self._status, False, False, 2)

        self.content.add(main_box)

    def _populate_models(self):
        """Fetch available models from Ollama."""
        self._model_combo.remove_all()
        try:
            req = urllib.request.Request(f"{OLLAMA_URL}/api/tags")
            with urllib.request.urlopen(req, timeout=3) as resp:
                data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                for m in models:
                    self._model_combo.append_text(m)
                if DEFAULT_MODEL in models:
                    idx = models.index(DEFAULT_MODEL)
                    self._model_combo.set_active(idx)
                elif models:
                    self._model_combo.set_active(0)
        except Exception:
            self._model_combo.append_text(DEFAULT_MODEL)
            self._model_combo.set_active(0)

    def _make_bubble(self, text, is_user):
        """Create a chat bubble widget."""
        frame = Gtk.Frame()
        frame.set_shadow_type(Gtk.ShadowType.NONE)

        inner = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        inner.set_margin_top(6)
        inner.set_margin_bottom(6)
        inner.set_margin_start(10)
        inner.set_margin_end(10)

        role = Gtk.Label()
        if is_user:
            role.set_markup("<small><b>Siz</b></small>")
            role.set_halign(Gtk.Align.END)
        else:
            role.set_markup("<small><b>AI Asistan</b></small>")
            role.set_halign(Gtk.Align.START)
        inner.pack_start(role, False, False, 0)

        msg_label = Gtk.Label(label=text)
        msg_label.set_line_wrap(True)
        msg_label.set_line_wrap_mode(Pango.WrapMode.WORD_CHAR)
        msg_label.set_max_width_chars(60)
        msg_label.set_selectable(True)
        if is_user:
            msg_label.set_halign(Gtk.Align.END)
        else:
            msg_label.set_halign(Gtk.Align.START)
        inner.pack_start(msg_label, False, False, 0)

        frame.add(inner)

        ctx = frame.get_style_context()
        if is_user:
            css = b"frame { background-color: #1a5276; border-radius: 12px; margin-left: 60px; }"
        else:
            css = b"frame { background-color: #2c3e50; border-radius: 12px; margin-right: 60px; }"
        provider = Gtk.CssProvider()
        provider.load_from_data(css)
        ctx.add_provider(provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)

        return frame

    def _scroll_to_bottom(self):
        adj = self._chat_scroll.get_vadjustment()
        GLib.idle_add(
            lambda: adj.set_value(adj.get_upper() - adj.get_page_size())
        )

    def _on_send(self, _widget):
        text = self._entry.get_text().strip()
        if not text or self._is_generating:
            return

        self._current_model = (
            self._model_combo.get_active_text() or DEFAULT_MODEL
        )

        user_bubble = self._make_bubble(text, is_user=True)
        self._chat_box.pack_start(user_bubble, False, False, 0)
        user_bubble.show_all()
        self._entry.set_text("")
        self._scroll_to_bottom()

        self._messages.append({"role": "user", "content": text})

        self._ai_bubble_frame = self._make_bubble("Dusunuyor...", is_user=False)
        self._chat_box.pack_start(self._ai_bubble_frame, False, False, 0)
        self._ai_bubble_frame.show_all()
        self._scroll_to_bottom()

        self._is_generating = True
        self._send_btn.set_sensitive(False)
        self._entry.set_sensitive(False)
        self._status.set_text(f"Model: {self._current_model} | Yanit uretiliyor...")

        thread = threading.Thread(target=self._generate_response, daemon=True)
        thread.start()

    def _generate_response(self):
        """Call Ollama API (streaming) in background thread."""
        try:
            payload = {
                "model": self._current_model,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT}
                ] + self._messages[-10:],
                "stream": True,
                "options": {"num_predict": 512},
            }
            data = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                f"{OLLAMA_URL}/api/chat",
                data=data,
                headers={"Content-Type": "application/json"},
                method="POST",
            )

            self._response_buffer = ""
            in_thinking = False

            with urllib.request.urlopen(req, timeout=120) as resp:
                for line in resp:
                    if not line.strip():
                        continue
                    try:
                        chunk = json.loads(line)
                        token = chunk.get("message", {}).get("content", "")

                        if "<think>" in token:
                            in_thinking = True
                            token = token.split("<think>")[-1]
                        if "</think>" in token:
                            in_thinking = False
                            token = token.split("</think>")[-1]
                            continue
                        if in_thinking:
                            continue

                        self._response_buffer += token
                        GLib.idle_add(self._update_ai_bubble)

                        if chunk.get("done"):
                            break
                    except json.JSONDecodeError:
                        continue

            if self._response_buffer.strip():
                self._messages.append(
                    {"role": "assistant", "content": self._response_buffer}
                )
            GLib.idle_add(self._generation_complete)

        except urllib.error.URLError as e:
            GLib.idle_add(
                self._generation_error,
                f"Baglanti hatasi: Ollama calismiyor olabilir ({e})",
            )
        except Exception as e:
            GLib.idle_add(self._generation_error, str(e))

    def _update_ai_bubble(self):
        try:
            if self._ai_bubble_frame is None:
                return
            inner = self._ai_bubble_frame.get_child()
            children = inner.get_children()
            if len(children) >= 2:
                msg_label = children[1]
                display_text = self._response_buffer.strip() or "Dusunuyor..."
                msg_label.set_text(display_text)
                self._scroll_to_bottom()
        except Exception:
            pass

    def _generation_complete(self):
        self._is_generating = False
        self._send_btn.set_sensitive(True)
        self._entry.set_sensitive(True)
        self._entry.grab_focus()
        self._status.set_text(f"Model: {self._current_model} | Hazir")
        self._update_ai_bubble()
        self._scroll_to_bottom()

    def _generation_error(self, error_msg):
        self._is_generating = False
        self._send_btn.set_sensitive(True)
        self._entry.set_sensitive(True)
        self._response_buffer = f"Hata: {error_msg}"
        self._update_ai_bubble()
        self._status.set_text("Hata olustu")

    def _on_clear(self, _btn):
        self._messages.clear()
        children = self._chat_box.get_children()
        for child in children[1:]:
            self._chat_box.remove(child)
        self._status.set_text("")
