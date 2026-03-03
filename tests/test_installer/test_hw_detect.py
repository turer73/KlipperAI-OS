"""Hardware detection tests."""
from __future__ import annotations


def test_hw_detect_import():
    from packages.installer.hw_detect import HardwareInfo
    assert HardwareInfo is not None


def test_profile_recommendation_light():
    from packages.installer.hw_detect import recommend_profile
    assert recommend_profile(ram_mb=1024, cpu_cores=2) == "LIGHT"


def test_profile_recommendation_standard():
    from packages.installer.hw_detect import recommend_profile
    assert recommend_profile(ram_mb=2048, cpu_cores=2) == "STANDARD"


def test_profile_recommendation_full():
    from packages.installer.hw_detect import recommend_profile
    assert recommend_profile(ram_mb=4096, cpu_cores=4) == "FULL"


def test_force_light_low_ram():
    from packages.installer.hw_detect import recommend_profile
    assert recommend_profile(ram_mb=512, cpu_cores=4) == "LIGHT"


def test_hardware_info_dataclass():
    from packages.installer.hw_detect import HardwareInfo
    hw = HardwareInfo(
        cpu_model="Test CPU",
        cpu_cores=4,
        cpu_freq_mhz=2000,
        ram_total_mb=4096,
        disk_total_mb=32000,
        has_wifi=True,
        has_ethernet=True,
        board_type="x86",
        recommended_profile="FULL",
    )
    assert hw.cpu_cores == 4
    assert hw.recommended_profile == "FULL"


def test_is_force_light():
    from packages.installer.hw_detect import HardwareInfo
    hw = HardwareInfo(
        cpu_model="", cpu_cores=1, cpu_freq_mhz=0,
        ram_total_mb=1024, disk_total_mb=0,
        has_wifi=False, has_ethernet=False,
        board_type="x86", recommended_profile="LIGHT",
    )
    assert hw.is_force_light is True

    hw2 = HardwareInfo(
        cpu_model="", cpu_cores=4, cpu_freq_mhz=0,
        ram_total_mb=4096, disk_total_mb=0,
        has_wifi=False, has_ethernet=False,
        board_type="x86", recommended_profile="FULL",
    )
    assert hw2.is_force_light is False
