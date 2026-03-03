"""Installer step tests."""
from __future__ import annotations


def test_all_steps_importable():
    from packages.installer.steps.welcome import WelcomeStep
    from packages.installer.steps.hardware import HardwareStep
    from packages.installer.steps.network_step import NetworkStep
    from packages.installer.steps.profile import ProfileStep
    from packages.installer.steps.user_setup import UserSetupStep
    from packages.installer.steps.install import InstallStep
    from packages.installer.steps.services import ServicesStep
    from packages.installer.steps.complete import CompleteStep
    assert all([
        WelcomeStep, HardwareStep, NetworkStep, ProfileStep,
        UserSetupStep, InstallStep, ServicesStep, CompleteStep,
    ])


def test_welcome_step_dry_run():
    from packages.installer.steps.welcome import WelcomeStep
    from packages.installer.tui import TUI
    tui = TUI(dry_run=True)
    step = WelcomeStep(tui=tui)
    result = step.run()
    assert result is True


def test_hardware_step_dry_run():
    from packages.installer.steps.hardware import HardwareStep
    from packages.installer.tui import TUI
    tui = TUI(dry_run=True)
    step = HardwareStep(tui=tui)
    hw = step.run()
    assert hw is not None


def test_profile_step_dry_run():
    from packages.installer.steps.profile import ProfileStep
    from packages.installer.tui import TUI
    from packages.installer.hw_detect import HardwareInfo
    tui = TUI(dry_run=True)
    hw = HardwareInfo(
        cpu_model="Test", cpu_cores=4, cpu_freq_mhz=2000,
        ram_total_mb=4096, disk_total_mb=32000,
        has_wifi=True, has_ethernet=True,
        board_type="x86", recommended_profile="FULL",
    )
    step = ProfileStep(tui=tui, hw_info=hw)
    profile = step.run()
    assert profile in ("LIGHT", "STANDARD", "FULL")
