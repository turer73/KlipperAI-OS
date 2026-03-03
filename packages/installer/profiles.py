"""Kurulum profil tanimlari."""
from __future__ import annotations

from dataclasses import dataclass, field


# --- APT Paket Gruplari ---
BASE_APT = [
    "build-essential",
    "cmake",
    "pkg-config",
    "python3-dev",
    "python3-setuptools",
    "python3-wheel",
    "gcc-arm-none-eabi",
    "binutils-arm-none-eabi",
    "libnewlib-arm-none-eabi",
    "stm32flash",
    "dfu-util",
    "avrdude",
    "nginx",
    "lsb-release",
    "can-utils",
    "python3-psutil",
    "zstd",
    "usbutils",
    "pciutils",
    "libffi-dev",
    "libncurses-dev",
    "libusb-1.0-0-dev",
    "supervisor",
    "lsof",
]

DISPLAY_APT = [
    "xserver-xorg",
    "xinit",
    "x11-xserver-utils",
    "python3-gi",
    "python3-gi-cairo",
    "gir1.2-gtk-3.0",
    "gir1.2-vte-2.91",
    "libopenjp2-7",
    "libcairo2-dev",
    "fonts-freefont-ttf",
    "xinput",
    "matchbox-keyboard",
]

MEDIA_APT = [
    "ffmpeg",
    "v4l-utils",
]


@dataclass
class Profile:
    """Kurulum profili."""

    name: str
    description: str
    min_ram_mb: int
    apt_packages: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)


PROFILES: dict[str, Profile] = {
    "LIGHT": Profile(
        name="LIGHT",
        description="Klipper + Moonraker + Mainsail (512MB+)",
        min_ram_mb=512,
        apt_packages=BASE_APT.copy(),
        components=["klipper", "moonraker", "mainsail"],
    ),
    "STANDARD": Profile(
        name="STANDARD",
        description="+ KlipperScreen + Kamera + AI Monitor (2GB+)",
        min_ram_mb=2048,
        apt_packages=BASE_APT + DISPLAY_APT + MEDIA_APT,
        components=[
            "klipper",
            "moonraker",
            "mainsail",
            "klipperscreen",
            "crowsnest",
            "ai_monitor",
        ],
    ),
    "FULL": Profile(
        name="FULL",
        description="+ Multi-printer + Timelapse + Tam AI (4GB+)",
        min_ram_mb=4096,
        apt_packages=BASE_APT + DISPLAY_APT + MEDIA_APT,
        components=[
            "klipper",
            "moonraker",
            "mainsail",
            "klipperscreen",
            "crowsnest",
            "ai_monitor",
            "multi_printer",
            "timelapse",
        ],
    ),
}
