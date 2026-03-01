"""
KlipperOS-AI -- AI Config Manager
==================================
Manages AI-driven Klipper configuration editing via Moonraker File API.
Only whitelisted parameters can be modified to prevent dangerous changes
to motion, MCU, or pin configuration.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, List, Dict

import requests


@dataclass
class ConfigChange:
    """Represents a single configuration change."""
    section: str
    key: str
    old_value: str
    new_value: str
    reason: str
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def __str__(self) -> str:
        return f"[{self.section}] {self.key}: {self.old_value} -> {self.new_value} ({self.reason})"


ALLOWED_PARAMS: Dict[str, List[str]] = {
    "extruder": [
        "pid_kp", "pid_ki", "pid_kd",
        "pressure_advance", "pressure_advance_smooth_time",
        "rotation_distance",
    ],
    "heater_bed": [
        "pid_kp", "pid_ki", "pid_kd",
    ],
    "input_shaper": [
        "shaper_freq_x", "shaper_freq_y",
        "shaper_type", "shaper_type_x", "shaper_type_y",
    ],
    "kos_flowguard": [
        "heater_threshold", "sg_clog_threshold", "sg_empty_threshold",
        "ai_spaghetti_threshold", "ai_no_extrusion_threshold",
        "warning_escalation_count",
    ],
}


class ConfigManager:
    """AI-driven Klipper config editor using Moonraker File API."""

    def __init__(self, moonraker_url: str):
        self.moonraker_url = moonraker_url.rstrip("/")
        self.change_log: List[ConfigChange] = []

    # ------------------------------------------------------------------
    # Whitelist
    # ------------------------------------------------------------------

    def is_allowed(self, section: str, key: str) -> bool:
        """Check whether a section/key pair is in the whitelist."""
        return key in ALLOWED_PARAMS.get(section, [])

    # ------------------------------------------------------------------
    # Config parsing helpers
    # ------------------------------------------------------------------

    def parse_sections(self, content: str) -> Dict[str, Dict[str, str]]:
        """Parse INI-like Klipper config into nested dicts.

        Returns:
            { "section_name": { "key": "value", ... }, ... }
        """
        sections: Dict[str, Dict[str, str]] = {}
        current_section: Optional[str] = None

        for line in content.splitlines():
            stripped = line.strip()
            # Section header
            match = re.match(r"^\[([^\]]+)\]", stripped)
            if match:
                current_section = match.group(1).strip()
                sections.setdefault(current_section, {})
                continue
            # Key = value
            if current_section is not None and "=" in stripped and not stripped.startswith("#"):
                key, _, value = stripped.partition("=")
                sections[current_section][key.strip()] = value.strip()

        return sections

    def update_value(self, content: str, section: str, key: str, new_value: str) -> str:
        """Update a single value in a config string.

        If the key exists in the section, its value is replaced in-place.
        If the key does not exist, it is appended at the end of the section.

        Returns:
            The modified config string.
        """
        lines = content.splitlines(keepends=True)
        in_section = False
        key_found = False
        section_end_index: Optional[int] = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            header = re.match(r"^\[([^\]]+)\]", stripped)
            if header:
                if in_section and not key_found:
                    # Reached next section without finding key -- insert before this line
                    section_end_index = i
                    break
                in_section = header.group(1).strip() == section
                continue

            if in_section and not stripped.startswith("#") and "=" in stripped:
                line_key, _, _ = stripped.partition("=")
                if line_key.strip() == key:
                    # Replace value in-place, preserving leading whitespace
                    leading = line[: len(line) - len(line.lstrip())]
                    newline = "\n" if line.endswith("\n") else ""
                    lines[i] = f"{leading}{key} = {new_value}{newline}"
                    key_found = True
                    break

        if not key_found:
            # Determine where to append
            if section_end_index is not None:
                insert_idx = section_end_index
            else:
                # Section is at the end of the file
                insert_idx = len(lines)
            new_line = f"{key} = {new_value}\n"
            lines.insert(insert_idx, new_line)

        return "".join(lines)

    # ------------------------------------------------------------------
    # Moonraker File API
    # ------------------------------------------------------------------

    def read_config(self, filename: str) -> Optional[str]:
        """Read a config file from Moonraker.

        GET /server/files/config/{filename}
        """
        try:
            resp = requests.get(
                f"{self.moonraker_url}/server/files/config/{filename}",
                timeout=10,
            )
            resp.raise_for_status()
            return resp.text
        except requests.RequestException:
            return None

    def write_config(self, filename: str, content: str) -> bool:
        """Write a config file via Moonraker upload.

        POST /server/files/upload
        """
        try:
            resp = requests.post(
                f"{self.moonraker_url}/server/files/upload",
                files={"file": (filename, content)},
                data={"root": "config"},
                timeout=10,
            )
            resp.raise_for_status()
            return True
        except requests.RequestException:
            return False

    def send_notification(self, message: str) -> None:
        """Send a notification through Moonraker.

        POST /server/notifications/create
        """
        try:
            requests.post(
                f"{self.moonraker_url}/server/notifications/create",
                json={"title": "KOS Config Manager", "message": message},
                timeout=5,
            )
        except requests.RequestException:
            pass

    # ------------------------------------------------------------------
    # High-level apply
    # ------------------------------------------------------------------

    def apply_changes(self, filename: str, changes: List[ConfigChange]) -> bool:
        """Validate, apply, and write a list of config changes.

        Steps:
            1. Validate all changes against the whitelist.
            2. Read the current config file.
            3. Apply each change.
            4. Write the updated config.
            5. Send a notification summarising the changes.

        Returns:
            True on success, False if any change is blocked or I/O fails.
        """
        # 1. Validate
        for change in changes:
            if not self.is_allowed(change.section, change.key):
                return False

        # 2. Read
        content = self.read_config(filename)
        if content is None:
            return False

        # 3. Apply
        for change in changes:
            content = self.update_value(content, change.section, change.key, change.new_value)

        # 4. Write
        if not self.write_config(filename, content):
            return False

        # 5. Log and notify
        self.change_log.extend(changes)
        summary = "; ".join(str(c) for c in changes)
        self.send_notification(f"Config updated: {summary}")
        return True

    # ------------------------------------------------------------------
    # Convenience wrappers
    # ------------------------------------------------------------------

    def apply_pid_result(self, heater: str, kp: str, ki: str, kd: str) -> bool:
        """Apply PID autotune result for a heater section."""
        changes = [
            ConfigChange(section=heater, key="pid_kp", old_value="", new_value=kp,
                         reason="PID autotune"),
            ConfigChange(section=heater, key="pid_ki", old_value="", new_value=ki,
                         reason="PID autotune"),
            ConfigChange(section=heater, key="pid_kd", old_value="", new_value=kd,
                         reason="PID autotune"),
        ]
        return self.apply_changes("printer.cfg", changes)

    def apply_pressure_advance(self, pa_value: str) -> bool:
        """Apply pressure advance value for the extruder."""
        changes = [
            ConfigChange(section="extruder", key="pressure_advance", old_value="",
                         new_value=pa_value, reason="PA calibration"),
        ]
        return self.apply_changes("printer.cfg", changes)

    def apply_input_shaper(self, freq_x: str, freq_y: str,
                           type_x: str, type_y: str) -> bool:
        """Apply input shaper calibration results."""
        changes = [
            ConfigChange(section="input_shaper", key="shaper_freq_x", old_value="",
                         new_value=freq_x, reason="Input shaper calibration"),
            ConfigChange(section="input_shaper", key="shaper_freq_y", old_value="",
                         new_value=freq_y, reason="Input shaper calibration"),
            ConfigChange(section="input_shaper", key="shaper_type_x", old_value="",
                         new_value=type_x, reason="Input shaper calibration"),
            ConfigChange(section="input_shaper", key="shaper_type_y", old_value="",
                         new_value=type_y, reason="Input shaper calibration"),
        ]
        return self.apply_changes("printer.cfg", changes)
