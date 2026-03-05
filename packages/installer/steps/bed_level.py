"""Adim 8.5: Bed level yapilandirma wizard."""
from __future__ import annotations

from ..tui import TUI
from ..utils.logger import get_logger

logger = get_logger()

# Bilinen yazici vida pozisyonlari (printer_model -> screw list)
KNOWN_SCREW_POSITIONS = {
    "ender3": [
        ("30.5, 37", "Sol On"),
        ("30.5, 207", "Sol Arka"),
        ("204.5, 207", "Sag Arka"),
        ("204.5, 37", "Sag On"),
    ],
    "ender3v2": [
        ("30.5, 37", "Sol On"),
        ("30.5, 207", "Sol Arka"),
        ("204.5, 207", "Sag Arka"),
        ("204.5, 37", "Sag On"),
    ],
}

PROBE_TYPES = [
    ("none", "Prob yok (manuel leveling)"),
    ("bltouch", "BLTouch / 3DTouch"),
    ("inductive", "Inductive / Capacitive Probe"),
    ("klicky", "Klicky / Tap (Voron)"),
]

MESH_DENSITIES = [
    ("3", "3x3 — Hizli (~30 sn)"),
    ("5", "5x5 — Dengeli (~1.5 dk) [Onerilen]"),
    ("7", "7x7 — Detayli (~3 dk)"),
]


class BedLevelStep:
    """Bed leveling yapilandirma wizard'i."""

    def __init__(self, tui: TUI, hw_info=None):
        self.tui = tui
        self.hw_info = hw_info
        self.probe_type = "none"
        self.probe_x_offset = 0.0
        self.probe_y_offset = 0.0
        self.mesh_count = 5
        self.bed_x_max = 235
        self.bed_y_max = 235

    def run(self) -> dict:
        """Wizard adimlari. Config verisini dict olarak dondurur."""
        logger.info("Bed level wizard basliyor...")

        # Atla secenegi
        skip = self.tui.yesno(
            "Bed leveling yapilandirmak ister misiniz?\n\n"
            "(Atlarsaniz varsayilan ayarlar kullanilir,\n"
            " ilk acilista KOS_BED_LEVEL_CALIBRATE ile baslayin)",
            title="Bed Leveling",
        )
        if not skip:
            logger.info("Bed level wizard atlandi.")
            return {"skipped": True}

        # 1. Probe tipi
        self.probe_type = self.tui.menu(
            "Probe Tipi",
            PROBE_TYPES,
            text="Yazicinizda Z probe var mi?",
        )
        logger.info("Probe tipi: %s", self.probe_type)

        # 2. Probe offset (probe varsa)
        if self.probe_type != "none":
            self._ask_probe_offset()

        # 3. Mesh ayarlari (probe varsa)
        if self.probe_type != "none":
            self._ask_mesh_settings()

        # 4. Ozet
        self._show_summary()

        result = {
            "skipped": False,
            "probe_type": self.probe_type,
            "probe_x_offset": self.probe_x_offset,
            "probe_y_offset": self.probe_y_offset,
            "mesh_count": self.mesh_count,
            "bed_x_max": self.bed_x_max,
            "bed_y_max": self.bed_y_max,
        }
        logger.info("Bed level config: %s", result)
        return result

    def _ask_probe_offset(self):
        """Probe offset bilgisi sor."""
        defaults = {
            "bltouch": (-44, -6),
            "inductive": (-25, 0),
            "klicky": (0, 0),
        }
        dx, dy = defaults.get(self.probe_type, (0, 0))

        use_default = self.tui.yesno(
            f"Varsayilan offset kullanilsin mi?\n\n"
            f"  X offset: {dx} mm\n"
            f"  Y offset: {dy} mm\n\n"
            f"(Sonra PROBE_CALIBRATE ile kalibre edebilirsiniz)",
            title="Probe Offset",
        )
        if use_default:
            self.probe_x_offset = dx
            self.probe_y_offset = dy
        else:
            x_str = self.tui.inputbox("Probe X offset (mm):", title="X Offset", default=str(dx))
            y_str = self.tui.inputbox("Probe Y offset (mm):", title="Y Offset", default=str(dy))
            try:
                self.probe_x_offset = float(x_str)
                self.probe_y_offset = float(y_str)
            except ValueError:
                self.probe_x_offset = dx
                self.probe_y_offset = dy

    def _ask_mesh_settings(self):
        """Mesh cozunurluk ayarlari."""
        choice = self.tui.menu(
            "Mesh Cozunurlugu",
            MESH_DENSITIES,
            text="Bed mesh prob noktasi sayisi:",
        )
        self.mesh_count = int(choice)

    def _show_summary(self):
        """Ozet goster."""
        probe_str = dict(PROBE_TYPES).get(self.probe_type, self.probe_type)
        lines = [
            f"  Probe:          {probe_str}",
        ]
        if self.probe_type != "none":
            lines.extend([
                f"  X Offset:       {self.probe_x_offset} mm",
                f"  Y Offset:       {self.probe_y_offset} mm",
                f"  Mesh:           {self.mesh_count}x{self.mesh_count}",
            ])
        lines.append("\nBu ayarlar printer.cfg'ye yazilacak.")

        self.tui.msgbox("Bed Level Ozeti", "\n".join(lines))

    def generate_config(self) -> str:
        """Klipper config blogu olustur."""
        sections = []

        # bed_screws (her zaman — probsuz da kullanilabilir)
        sections.append(
            "# --- Manuel Yatak Hizalama ---\n"
            "[bed_screws]\n"
            "screw1: 30.5, 37\n"
            "screw1_name: Sol On\n"
            "screw2: 30.5, 207\n"
            "screw2_name: Sol Arka\n"
            "screw3: 204.5, 207\n"
            "screw3_name: Sag Arka\n"
            "screw4: 204.5, 37\n"
            "screw4_name: Sag On\n"
        )

        if self.probe_type != "none":
            # probe section
            if self.probe_type == "bltouch":
                sections.append(
                    "\n[bltouch]\n"
                    "sensor_pin: ^PB1\n"
                    "control_pin: PB0\n"
                    f"x_offset: {self.probe_x_offset}\n"
                    f"y_offset: {self.probe_y_offset}\n"
                    "z_offset: 0\n"
                )
            else:
                sections.append(
                    "\n[probe]\n"
                    "pin: ^PC2\n"
                    f"x_offset: {self.probe_x_offset}\n"
                    f"y_offset: {self.probe_y_offset}\n"
                    "z_offset: 0\n"
                    "speed: 5.0\n"
                    "samples: 3\n"
                    "samples_result: median\n"
                )

            # safe_z_home
            cx = self.bed_x_max // 2
            cy = self.bed_y_max // 2
            sections.append(
                f"\n[safe_z_home]\n"
                f"home_xy_position: {cx}, {cy}\n"
                "speed: 80\n"
                "z_hop: 10\n"
            )

            # bed_mesh
            margin = 10
            mesh_min = f"{margin}, {margin}"
            mesh_max = f"{self.bed_x_max - margin}, {self.bed_y_max - margin}"
            algo = "bicubic" if self.mesh_count >= 4 else "lagrange"
            sections.append(
                "\n[bed_mesh]\n"
                "speed: 120\n"
                "horizontal_move_z: 5\n"
                f"mesh_min: {mesh_min}\n"
                f"mesh_max: {mesh_max}\n"
                f"probe_count: {self.mesh_count}, {self.mesh_count}\n"
                f"algorithm: {algo}\n"
                "fade_start: 1\n"
                "fade_end: 10\n"
            )

        sections.append("\n[include kos_bed_level.cfg]\n")
        return "\n".join(sections)
