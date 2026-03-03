"""Profile definitions tests."""
from __future__ import annotations


def test_profiles_import():
    from packages.installer.profiles import PROFILES

    assert "LIGHT" in PROFILES
    assert "STANDARD" in PROFILES
    assert "FULL" in PROFILES


def test_light_profile_has_klipper():
    from packages.installer.profiles import PROFILES

    light = PROFILES["LIGHT"]
    assert "klipper" in light.components


def test_light_profile_no_klipperscreen():
    from packages.installer.profiles import PROFILES

    light = PROFILES["LIGHT"]
    assert "klipperscreen" not in light.components


def test_standard_has_klipperscreen():
    from packages.installer.profiles import PROFILES

    std = PROFILES["STANDARD"]
    assert "klipperscreen" in std.components
    assert "crowsnest" in std.components


def test_full_has_all():
    from packages.installer.profiles import PROFILES

    full = PROFILES["FULL"]
    assert "klipper" in full.components
    assert "klipperscreen" in full.components
    assert "ai_monitor" in full.components


def test_profile_apt_packages():
    from packages.installer.profiles import PROFILES

    light = PROFILES["LIGHT"]
    assert "nginx" in light.apt_packages
    assert "build-essential" in light.apt_packages


def test_standard_has_display_packages():
    from packages.installer.profiles import PROFILES

    std = PROFILES["STANDARD"]
    assert "xserver-xorg" in std.apt_packages


def test_profile_min_ram():
    from packages.installer.profiles import PROFILES

    assert PROFILES["LIGHT"].min_ram_mb == 512
    assert PROFILES["STANDARD"].min_ram_mb == 2048
    assert PROFILES["FULL"].min_ram_mb == 4096
