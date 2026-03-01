"""Tests for KlipperAI-OS image builder scripts and configs."""

import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
IMG_DIR = ROOT / "image-builder"


class TestBuildScript:
    """build-image.sh syntax and structure tests."""

    def test_exists(self):
        assert (IMG_DIR / "build-image.sh").exists()

    def test_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(IMG_DIR / "build-image.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_has_lb_config(self):
        content = (IMG_DIR / "build-image.sh").read_text()
        assert "lb config" in content

    def test_has_lb_build(self):
        content = (IMG_DIR / "build-image.sh").read_text()
        assert "lb build" in content

    def test_has_version(self):
        content = (IMG_DIR / "build-image.sh").read_text()
        assert 'VERSION=' in content


class TestPackageList:
    """Package list tests."""

    def test_exists(self):
        assert (IMG_DIR / "config" / "package-lists" / "klipperos.list.chroot").exists()

    def test_has_essential_packages(self):
        content = (IMG_DIR / "config" / "package-lists" / "klipperos.list.chroot").read_text()
        essential = ["python3", "git", "nginx", "network-manager", "whiptail", "sudo"]
        for pkg in essential:
            assert pkg in content, f"Missing package: {pkg}"

    def test_has_klipper_build_deps(self):
        content = (IMG_DIR / "config" / "package-lists" / "klipperos.list.chroot").read_text()
        assert "gcc-arm-none-eabi" in content

    def test_has_gtk_packages(self):
        content = (IMG_DIR / "config" / "package-lists" / "klipperos.list.chroot").read_text()
        assert "gir1.2-gtk-3.0" in content


class TestBuildHook:
    """Build hook tests."""

    def test_exists(self):
        assert (IMG_DIR / "config" / "hooks" / "live" / "0100-setup.hook.chroot").exists()

    def test_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(IMG_DIR / "config" / "hooks" / "live" / "0100-setup.hook.chroot")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_creates_klipper_user(self):
        content = (IMG_DIR / "config" / "hooks" / "live" / "0100-setup.hook.chroot").read_text()
        assert "useradd" in content
        assert "klipper" in content

    def test_has_sudoers(self):
        content = (IMG_DIR / "config" / "hooks" / "live" / "0100-setup.hook.chroot").read_text()
        assert "sudoers" in content


class TestFirstBootService:
    """Systemd service tests."""

    def test_exists(self):
        svc = IMG_DIR / "config" / "includes.chroot" / "etc" / "systemd" / "system" / "klipperai-first-boot.service"
        assert svc.exists()

    def test_has_condition(self):
        svc = IMG_DIR / "config" / "includes.chroot" / "etc" / "systemd" / "system" / "klipperai-first-boot.service"
        content = svc.read_text()
        assert "ConditionPathExists" in content
        assert ".first-boot" in content

    def test_execstart_points_to_wizard(self):
        svc = IMG_DIR / "config" / "includes.chroot" / "etc" / "systemd" / "system" / "klipperai-first-boot.service"
        content = svc.read_text()
        assert "klipperai-wizard" in content


class TestWizard:
    """First boot wizard tests."""

    def test_exists(self):
        assert (IMG_DIR / "first-boot-wizard.sh").exists()

    def test_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(IMG_DIR / "first-boot-wizard.sh")],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_has_all_steps(self):
        content = (IMG_DIR / "first-boot-wizard.sh").read_text()
        steps = [
            "step_welcome", "step_detect_hardware", "step_select_profile",
            "step_network", "step_user_settings", "step_disk_install",
            "step_install_profile", "step_complete",
        ]
        for step in steps:
            assert step in content, f"Missing step: {step}"

    def test_has_profile_recommendation(self):
        content = (IMG_DIR / "first-boot-wizard.sh").read_text()
        assert "RECOMMENDED_PROFILE" in content
        assert "LIGHT" in content
        assert "STANDARD" in content
        assert "FULL" in content

    def test_has_disk_install(self):
        content = (IMG_DIR / "first-boot-wizard.sh").read_text()
        assert "parted" in content
        assert "rsync" in content
        assert "grub-install" in content


class TestGrubConfig:
    """GRUB config tests."""

    def test_exists(self):
        assert (IMG_DIR / "config" / "bootloaders" / "grub" / "grub.cfg").exists()

    def test_has_menu_entries(self):
        content = (IMG_DIR / "config" / "bootloaders" / "grub" / "grub.cfg").read_text()
        assert content.count("menuentry") >= 2

    def test_has_klipperai_branding(self):
        content = (IMG_DIR / "config" / "bootloaders" / "grub" / "grub.cfg").read_text()
        assert "KlipperAI-OS" in content
