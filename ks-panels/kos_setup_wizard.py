# ks-panels/kos_setup_wizard.py
"""KlipperOS-AI — Setup Wizard Panel for KlipperScreen.

Ilk acilis kurulum sihirbazi GTK3 paneli.
OOBE Orchestrator ile JSON dosyalari uzerinden iletisir.
Gtk.Stack ile 7 sayfa halinde calisir.

Mimari:
    Orchestrator (kos_oobe.py) -> oobe-state.json -> Bu panel (okur)
    Bu panel -> oobe-command.json -> Orchestrator (okur)
"""

import json
import logging
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import Gtk, GLib, Pango
from ks_includes.screen_panel import ScreenPanel

logger = logging.getLogger("KOS-SetupWizard")

# Paths (must match kos_oobe.py)
KOS_CONFIG_DIR = Path("/etc/klipperos-ai")
STATE_FILE = KOS_CONFIG_DIR / "oobe-state.json"
COMMAND_FILE = KOS_CONFIG_DIR / "oobe-command.json"
OOBE_DONE_MARKER = KOS_CONFIG_DIR / ".oobe-done"

# Step names
STEPS = ["welcome", "hw_detect", "wifi", "profile", "install", "tuning", "complete"]
STEP_NAMES_TR = {
    "welcome": "Hosgeldiniz",
    "hw_detect": "Donanim Algilama",
    "wifi": "Ag Yapilandirma",
    "profile": "Profil Secimi",
    "install": "Kurulum",
    "tuning": "Sistem Ayarlari",
    "complete": "Tamamlandi",
}

PROFILE_DESC = {
    "LIGHT": "Temel - Klipper + Moonraker + Mainsail",
    "STANDARD": "Dengeli - + KlipperScreen + AI (qwen3:1.7b)",
    "FULL": "Tam - + Coklu yazici + Gelismis AI (qwen3:4b)",
}


# ---------------------------------------------------------------------------
# JSON I/O (matches orchestrator's atomic write pattern)
# ---------------------------------------------------------------------------

def _read_state() -> Optional[dict]:
    """Read OOBE state from JSON file."""
    try:
        if not STATE_FILE.exists():
            return None
        with open(STATE_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("State okuma hatasi: %s", exc)
        return None


def _send_command(command: str, args: Optional[dict] = None) -> None:
    """Write a command for the orchestrator to read (atomic)."""
    data = {
        "command": command,
        "args": args or {},
        "timestamp": time.time(),
    }
    try:
        KOS_CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(KOS_CONFIG_DIR), suffix=".tmp", prefix=".cmd-"
        )
        with os.fdopen(fd, "w") as f:
            json.dump(data, f, ensure_ascii=False)
            f.write("\n")
        os.replace(tmp, str(COMMAND_FILE))
    except OSError as exc:
        logger.error("Komut yazma hatasi: %s", exc)
        try:
            os.unlink(tmp)
        except OSError:
            pass


class Panel(ScreenPanel):
    """KlipperScreen OOBE setup wizard panel.

    Uses Gtk.Stack to show 7 wizard pages.
    Polls oobe-state.json every 2 seconds to update display.
    Sends commands via oobe-command.json.
    """

    def __init__(self, screen, title):
        title = title or "Kurulum Sihirbazi"
        super().__init__(screen, title)

        self._state: Optional[dict] = None
        self._current_page: str = "welcome"
        self._poll_timer_id: Optional[int] = None
        self._wifi_networks: List[dict] = []
        self._selected_ssid: Optional[str] = None

        self._build_ui()

        # Start polling
        self._poll_timer_id = GLib.timeout_add_seconds(2, self._poll_state)
        GLib.idle_add(self._poll_state)

    def _build_ui(self):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # --- Top progress bar ---
        self._progress_bar = Gtk.ProgressBar()
        self._progress_bar.set_show_text(True)
        self._progress_bar.set_text("Baslatiliyor...")
        main_box.pack_start(self._progress_bar, False, False, 0)

        # --- Step indicator ---
        self._step_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self._step_box.set_halign(Gtk.Align.CENTER)
        self._step_box.set_margin_top(8)
        self._step_box.set_margin_bottom(8)
        self._step_labels = {}
        for step in STEPS:
            lbl = Gtk.Label(label=f" {STEP_NAMES_TR[step]} ")
            lbl.get_style_context().add_class("dim-label")
            self._step_labels[step] = lbl
            self._step_box.pack_start(lbl, False, False, 2)
        main_box.pack_start(self._step_box, False, False, 0)

        # --- Stack for pages ---
        self._stack = Gtk.Stack()
        self._stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT)
        self._stack.set_transition_duration(300)

        self._stack.add_named(self._build_welcome_page(), "welcome")
        self._stack.add_named(self._build_hw_detect_page(), "hw_detect")
        self._stack.add_named(self._build_wifi_page(), "wifi")
        self._stack.add_named(self._build_profile_page(), "profile")
        self._stack.add_named(self._build_install_page(), "install")
        self._stack.add_named(self._build_tuning_page(), "tuning")
        self._stack.add_named(self._build_complete_page(), "complete")
        self._stack.add_named(self._build_waiting_page(), "waiting")

        main_box.pack_start(self._stack, True, True, 0)
        self.content.add(main_box)

    # ===================================================================
    # Page Builders
    # ===================================================================

    def _build_welcome_page(self) -> Gtk.Box:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        page.set_valign(Gtk.Align.CENTER)
        page.set_margin_start(40)
        page.set_margin_end(40)

        title = Gtk.Label()
        title.set_markup("<span size='xx-large' weight='bold'>KlipperOS-AI</span>")
        page.pack_start(title, False, False, 10)

        subtitle = Gtk.Label()
        subtitle.set_markup("<span size='large'>Ilk Acilis Kurulum Sihirbazi</span>")
        page.pack_start(subtitle, False, False, 5)

        desc = Gtk.Label(
            label="Bu sihirbaz sisteminizi yapilandiracak:\n"
            "  Donanim algilama (MCU, kamera)\n"
            "  WiFi baglantisi\n"
            "  Profil secimi ve model kurulumu\n"
            "  Sistem optimizasyonu"
        )
        desc.set_line_wrap(True)
        desc.set_justify(Gtk.Justification.CENTER)
        page.pack_start(desc, False, False, 15)

        btn = Gtk.Button(label="  Basla  ")
        btn.get_style_context().add_class("suggested-action")
        btn.connect("clicked", self._on_start_clicked)
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_size_request(200, 50)
        page.pack_start(btn, False, False, 20)

        return page

    def _build_hw_detect_page(self) -> Gtk.Box:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_margin_start(30)
        page.set_margin_end(30)
        page.set_margin_top(20)

        title = Gtk.Label()
        title.set_markup("<b>Donanim Algilama</b>")
        page.pack_start(title, False, False, 10)

        self._hw_spinner = Gtk.Spinner()
        self._hw_spinner.start()
        page.pack_start(self._hw_spinner, False, False, 10)

        self._hw_status = Gtk.Label(label="Donanim taraniyor...")
        page.pack_start(self._hw_status, False, False, 5)

        self._hw_results = Gtk.Grid()
        self._hw_results.set_column_spacing(15)
        self._hw_results.set_row_spacing(8)
        self._hw_results.set_halign(Gtk.Align.CENTER)
        page.pack_start(self._hw_results, False, False, 10)

        return page

    def _build_wifi_page(self) -> Gtk.Box:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        page.set_margin_start(20)
        page.set_margin_end(20)
        page.set_margin_top(15)

        title = Gtk.Label()
        title.set_markup("<b>Ag Yapilandirma</b>")
        page.pack_start(title, False, False, 5)

        self._wifi_status = Gtk.Label(label="Aglar taraniyor...")
        page.pack_start(self._wifi_status, False, False, 3)

        btn_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        scan_btn = Gtk.Button(label="Yeniden Tara")
        scan_btn.connect("clicked", self._on_wifi_rescan)
        btn_row.pack_start(scan_btn, False, False, 0)

        skip_btn = Gtk.Button(label="Atla")
        skip_btn.connect("clicked", self._on_wifi_skip)
        btn_row.pack_end(skip_btn, False, False, 0)
        page.pack_start(btn_row, False, False, 3)

        scroll = self._gtk.ScrolledWindow()
        scroll.set_min_content_height(120)
        scroll.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        self._wifi_listbox = Gtk.ListBox()
        self._wifi_listbox.connect("row-selected", self._on_wifi_selected)
        scroll.add(self._wifi_listbox)
        page.pack_start(scroll, True, True, 3)

        pw_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=5)
        pw_label = Gtk.Label(label="Sifre:")
        self._wifi_pw_entry = Gtk.Entry()
        self._wifi_pw_entry.set_visibility(False)
        self._wifi_pw_entry.set_placeholder_text("WiFi sifresi")
        pw_box.pack_start(pw_label, False, False, 0)
        pw_box.pack_start(self._wifi_pw_entry, True, True, 0)
        page.pack_start(pw_box, False, False, 3)

        connect_btn = Gtk.Button(label="Baglan")
        connect_btn.get_style_context().add_class("suggested-action")
        connect_btn.connect("clicked", self._on_wifi_connect)
        connect_btn.set_halign(Gtk.Align.CENTER)
        connect_btn.set_size_request(180, 40)
        page.pack_start(connect_btn, False, False, 5)

        self._wifi_error_label = Gtk.Label(label="")
        page.pack_start(self._wifi_error_label, False, False, 3)

        return page

    def _build_profile_page(self) -> Gtk.Box:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_margin_start(30)
        page.set_margin_end(30)
        page.set_margin_top(20)

        title = Gtk.Label()
        title.set_markup("<b>Profil Secimi</b>")
        page.pack_start(title, False, False, 10)

        self._profile_info = Gtk.Label(label="")
        self._profile_info.set_line_wrap(True)
        page.pack_start(self._profile_info, False, False, 5)

        self._profile_radios: Dict[str, Gtk.RadioButton] = {}
        group = None
        for key, desc in PROFILE_DESC.items():
            if group is None:
                radio = Gtk.RadioButton.new_with_label(None, f"{key} - {desc}")
                group = radio
            else:
                radio = Gtk.RadioButton.new_with_label_from_widget(group, f"{key} - {desc}")
            radio.set_margin_start(20)
            radio.set_margin_top(5)
            self._profile_radios[key] = radio
            page.pack_start(radio, False, False, 3)

        self._profile_recommend = Gtk.Label()
        self._profile_recommend.set_markup("<i>Onerilen profil hesaplaniyor...</i>")
        page.pack_start(self._profile_recommend, False, False, 10)

        btn = Gtk.Button(label="  Profili Onayla  ")
        btn.get_style_context().add_class("suggested-action")
        btn.connect("clicked", self._on_profile_confirm)
        btn.set_halign(Gtk.Align.CENTER)
        btn.set_size_request(200, 45)
        page.pack_start(btn, False, False, 10)

        return page

    def _build_install_page(self) -> Gtk.Box:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_margin_start(30)
        page.set_margin_end(30)
        page.set_valign(Gtk.Align.CENTER)

        title = Gtk.Label()
        title.set_markup("<b>Kurulum</b>")
        page.pack_start(title, False, False, 10)

        self._install_spinner = Gtk.Spinner()
        page.pack_start(self._install_spinner, False, False, 10)

        self._install_status = Gtk.Label(label="Kurulum hazirlaniyor...")
        self._install_status.set_line_wrap(True)
        page.pack_start(self._install_status, False, False, 5)

        self._install_progress = Gtk.ProgressBar()
        self._install_progress.set_show_text(True)
        page.pack_start(self._install_progress, False, False, 10)

        self._install_detail = Gtk.Label(label="")
        self._install_detail.set_line_wrap(True)
        page.pack_start(self._install_detail, False, False, 5)

        return page

    def _build_tuning_page(self) -> Gtk.Box:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        page.set_margin_start(30)
        page.set_margin_end(30)
        page.set_valign(Gtk.Align.CENTER)

        title = Gtk.Label()
        title.set_markup("<b>Sistem Ayarlari</b>")
        page.pack_start(title, False, False, 10)

        self._tuning_spinner = Gtk.Spinner()
        self._tuning_spinner.start()
        page.pack_start(self._tuning_spinner, False, False, 10)

        self._tuning_status = Gtk.Label(label="Sistem ayarlari uygulaniyor...")
        self._tuning_status.set_line_wrap(True)
        page.pack_start(self._tuning_status, False, False, 5)

        self._tuning_items = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=5)
        self._tuning_items.set_halign(Gtk.Align.CENTER)

        for item in ["Servis optimizasyonu", "Zram swap", "Bellek limitleri"]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            icon = Gtk.Label(label="o")
            label = Gtk.Label(label=item)
            row.pack_start(icon, False, False, 0)
            row.pack_start(label, False, False, 0)
            self._tuning_items.pack_start(row, False, False, 2)

        page.pack_start(self._tuning_items, False, False, 10)
        return page

    def _build_complete_page(self) -> Gtk.Box:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        page.set_margin_start(40)
        page.set_margin_end(40)
        page.set_valign(Gtk.Align.CENTER)

        title = Gtk.Label()
        title.set_markup("<span size='x-large' weight='bold'>Kurulum Tamamlandi!</span>")
        page.pack_start(title, False, False, 10)

        self._complete_summary = Gtk.Label(label="")
        self._complete_summary.set_line_wrap(True)
        self._complete_summary.set_justify(Gtk.Justification.CENTER)
        page.pack_start(self._complete_summary, False, False, 10)

        btn_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=20)
        btn_box.set_halign(Gtk.Align.CENTER)

        reboot_btn = Gtk.Button(label="  Yeniden Baslat  ")
        reboot_btn.get_style_context().add_class("destructive-action")
        reboot_btn.connect("clicked", self._on_reboot)
        reboot_btn.set_size_request(180, 45)
        btn_box.pack_start(reboot_btn, False, False, 0)

        close_btn = Gtk.Button(label="  Kapat  ")
        close_btn.connect("clicked", self._on_close)
        close_btn.set_size_request(120, 45)
        btn_box.pack_start(close_btn, False, False, 0)

        page.pack_start(btn_box, False, False, 15)
        return page

    def _build_waiting_page(self) -> Gtk.Box:
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        page.set_valign(Gtk.Align.CENTER)

        spinner = Gtk.Spinner()
        spinner.start()
        page.pack_start(spinner, False, False, 10)

        self._waiting_label = Gtk.Label(
            label="Kurulum orkestratoru bekleniyor...\n"
            "Lutfen kos-oobe servisinin calistigindan emin olun."
        )
        self._waiting_label.set_line_wrap(True)
        self._waiting_label.set_justify(Gtk.Justification.CENTER)
        page.pack_start(self._waiting_label, False, False, 10)

        return page

    # ===================================================================
    # State Polling
    # ===================================================================

    def _poll_state(self) -> bool:
        state = _read_state()

        if state is None:
            self._stack.set_visible_child_name("waiting")
            return True

        self._state = state
        current = state.get("current_step")
        progress = state.get("progress_percent", 0)

        self._progress_bar.set_fraction(progress / 100.0)
        self._progress_bar.set_text(f"Ilerleme: %{progress}")

        for step_name, lbl in self._step_labels.items():
            step_info = state.get("steps", {}).get(step_name, {})
            st = step_info.get("status", "pending")
            if st == "completed":
                lbl.set_markup(f"<b><span color='green'>{STEP_NAMES_TR[step_name]}</span></b>")
            elif st in ("running", "waiting_input"):
                lbl.set_markup(f"<b><span color='#3584e4'>{STEP_NAMES_TR[step_name]}</span></b>")
            elif st == "error":
                lbl.set_markup(f"<span color='red'>{STEP_NAMES_TR[step_name]}</span>")
            else:
                lbl.set_markup(f"<span color='gray'>{STEP_NAMES_TR[step_name]}</span>")

        if current and current in STEPS:
            self._update_page_content(current, state)
            if current != self._current_page:
                self._stack.set_visible_child_name(current)
                self._current_page = current

        return True

    def _update_page_content(self, step: str, state: dict) -> None:
        step_data = state.get("steps", {}).get(step, {})
        data = step_data.get("data", {})
        status = step_data.get("status", "pending")

        if step == "hw_detect":
            self._update_hw_page(data, status)
        elif step == "wifi":
            self._update_wifi_page(data, status)
        elif step == "profile":
            self._update_profile_page(data, status)
        elif step == "install":
            self._update_install_page(data, status)
        elif step == "tuning":
            self._update_tuning_page(data, status)
        elif step == "complete":
            self._update_complete_page(data, status)

    def _update_hw_page(self, data: dict, status: str) -> None:
        if status == "completed":
            self._hw_spinner.stop()
            self._hw_status.set_text("Donanim algilandi!")
            for child in self._hw_results.get_children():
                self._hw_results.remove(child)
            items = [
                ("RAM:", f"{data.get('ram_mb', '?')} MB"),
                ("CPU:", data.get("cpu_model", "?")),
                ("MCU:", f"{data.get('mcu_count', 0)} adet"),
                ("Kamera:", f"{data.get('camera_count', 0)} adet"),
                ("Onerilen:", data.get("recommended_profile", "?")),
            ]
            for i, (label, value) in enumerate(items):
                lbl = Gtk.Label(label=label)
                lbl.set_halign(Gtk.Align.END)
                val = Gtk.Label(label=value)
                val.set_halign(Gtk.Align.START)
                self._hw_results.attach(lbl, 0, i, 1, 1)
                self._hw_results.attach(val, 1, i, 1, 1)
            self._hw_results.show_all()
        elif status == "running":
            self._hw_spinner.start()
            self._hw_status.set_text("Donanim taraniyor...")

    def _update_wifi_page(self, data: dict, status: str) -> None:
        if status in ("completed", "skipped"):
            ip = data.get("ip", "yok")
            ssid = data.get("ssid", "")
            msg = f"Baglandi: {ssid} ({ip})" if ip != "yok" else "Ag adimi atlandi"
            self._wifi_status.set_text(msg)
            self._wifi_error_label.set_text("")
        elif status == "waiting_input":
            networks = data.get("networks", [])
            error_msg = data.get("error", "")

            if networks != self._wifi_networks:
                self._wifi_networks = networks
                for child in self._wifi_listbox.get_children():
                    self._wifi_listbox.remove(child)
                for net in networks:
                    ssid = net.get("ssid", "?")
                    signal = net.get("signal", 0)
                    security = net.get("security", "")
                    lock = "[x]" if security and security != "OPEN" else "   "
                    row = Gtk.ListBoxRow()
                    label = Gtk.Label(label=f"{lock} {ssid}  {signal}%")
                    label.set_halign(Gtk.Align.START)
                    row.add(label)
                    self._wifi_listbox.add(row)
                self._wifi_listbox.show_all()
                self._wifi_status.set_text(f"{len(networks)} ag bulundu")

            if error_msg:
                self._wifi_error_label.set_markup(
                    f"<span color='red'>{error_msg}</span>"
                )

    def _update_profile_page(self, data: dict, status: str) -> None:
        recommended = data.get("recommended", "STANDARD")
        ram_mb = data.get("ram_mb", 0)
        if status == "waiting_input":
            self._profile_info.set_text(f"Algilanan RAM: {ram_mb} MB")
            self._profile_recommend.set_markup(
                f"<i>Onerilen profil: <b>{recommended}</b></i>"
            )
            if recommended in self._profile_radios:
                self._profile_radios[recommended].set_active(True)

    def _update_install_page(self, data: dict, status: str) -> None:
        if status == "running":
            self._install_spinner.start()
            current = data.get("current_model", "")
            idx = data.get("current_index", 0)
            total = data.get("total_models", 0)
            if current:
                self._install_status.set_text(
                    f"Model indiriliyor: {current} ({idx}/{total})"
                )
                self._install_progress.set_fraction(
                    (idx - 1) / total if total > 0 else 0
                )
                self._install_progress.set_text(f"{idx}/{total}")
        elif status == "completed":
            self._install_spinner.stop()
            downloaded = data.get("models_downloaded", [])
            needed = data.get("models_needed", [])
            skipped = data.get("skipped", False)
            if skipped:
                self._install_status.set_text("Model kurulumu atlandi.")
            elif len(downloaded) == len(needed):
                self._install_status.set_text("Tum modeller basariyla indirildi!")
            else:
                self._install_status.set_text(
                    f"{len(downloaded)}/{len(needed)} model indirildi."
                )
            self._install_progress.set_fraction(1.0)
            self._install_detail.set_text(
                ", ".join(downloaded) if downloaded else ""
            )

    def _update_tuning_page(self, data: dict, status: str) -> None:
        if status == "running":
            self._tuning_spinner.start()
            sub = data.get("sub_step", "")
            self._tuning_status.set_text(f"Ayarlaniyor: {sub}...")
            items = self._tuning_items.get_children()
            checks = [
                data.get("service_optimizer", False),
                data.get("zram", False),
                data.get("memory_limits", False),
            ]
            for row, done in zip(items, checks):
                children = row.get_children()
                if children:
                    children[0].set_text("[+]" if done else "o")
        elif status == "completed":
            self._tuning_spinner.stop()
            self._tuning_status.set_text("Sistem ayarlari tamamlandi!")
            items = self._tuning_items.get_children()
            checks = [
                data.get("service_optimizer", False),
                data.get("zram", False),
                data.get("memory_limits", False),
            ]
            for row, done in zip(items, checks):
                children = row.get_children()
                if children:
                    children[0].set_text("[+]" if done else "[-]")

    def _update_complete_page(self, data: dict, status: str) -> None:
        if status == "completed":
            profile = data.get("profile", "?")
            ip = data.get("ip", "yok")
            ram = data.get("ram_mb", 0)
            models = data.get("models", [])
            mcu_count = data.get("mcu_count", 0)
            cam_count = data.get("camera_count", 0)
            summary = (
                f"Profil: {profile}\n"
                f"RAM: {ram} MB\n"
                f"IP: {ip}\n"
                f"MCU: {mcu_count} adet\n"
                f"Kamera: {cam_count} adet\n"
                f"Modeller: {', '.join(models) or 'yok'}"
            )
            self._complete_summary.set_text(summary)

    # ===================================================================
    # Event Handlers
    # ===================================================================

    def _on_start_clicked(self, _button) -> None:
        _send_command("start")

    def _on_wifi_selected(self, _listbox, row) -> None:
        if row is not None:
            idx = row.get_index()
            if 0 <= idx < len(self._wifi_networks):
                self._selected_ssid = self._wifi_networks[idx].get("ssid")

    def _on_wifi_connect(self, _button) -> None:
        if not self._selected_ssid:
            self._wifi_error_label.set_markup(
                "<span color='red'>Bir ag secin</span>"
            )
            return
        password = self._wifi_pw_entry.get_text()
        _send_command("wifi_connect", {
            "ssid": self._selected_ssid,
            "password": password,
        })
        self._wifi_status.set_text(f"Baglaniyor: {self._selected_ssid}...")
        self._wifi_error_label.set_text("")

    def _on_wifi_rescan(self, _button) -> None:
        _send_command("wifi_rescan")
        self._wifi_status.set_text("Yeniden taraniyor...")

    def _on_wifi_skip(self, _button) -> None:
        _send_command("wifi_skip")

    def _on_profile_confirm(self, _button) -> None:
        selected = "STANDARD"
        for key, radio in self._profile_radios.items():
            if radio.get_active():
                selected = key
                break
        _send_command("select_profile", {"profile": selected})

    def _on_reboot(self, _button) -> None:
        _send_command("reboot")
        try:
            subprocess.Popen(["sudo", "reboot"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def _on_close(self, _button) -> None:
        if self._poll_timer_id:
            GLib.source_remove(self._poll_timer_id)
            self._poll_timer_id = None
        self._screen._menu_go_back()
