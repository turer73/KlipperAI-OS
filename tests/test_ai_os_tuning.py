"""Tests for OS Tuning & CPU Affinity scripts (Phase 0.5)."""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
CONFIG = ROOT / "config"


class TestSetupOsTuning:
    """setup-os-tuning.sh script tests."""

    SCRIPT = SCRIPTS / "setup-os-tuning.sh"

    def test_exists(self):
        assert self.SCRIPT.exists()

    def test_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(self.SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_has_root_guard(self):
        content = self.SCRIPT.read_text()
        assert "EUID" in content
        assert "root" in content.lower()

    def test_has_marker_check(self):
        content = self.SCRIPT.read_text()
        assert "os-tuning-applied" in content
        assert "FORCE_REAPPLY" in content

    def test_has_hardware_detection(self):
        content = self.SCRIPT.read_text()
        assert "nproc" in content
        assert "MemTotal" in content
        assert "device-tree" in content

    def test_has_kernel_boot_params(self):
        content = self.SCRIPT.read_text()
        assert "threadirqs" in content
        assert "consoleblank" in content
        assert "preempt=full" in content

    def test_has_io_scheduler(self):
        content = self.SCRIPT.read_text()
        assert "scheduler" in content
        assert "mq-deadline" in content

    def test_has_filesystem_tuning(self):
        content = self.SCRIPT.read_text()
        assert "noatime" in content
        assert "commit=60" in content
        assert "tmpfs" in content

    def test_has_journald_limits(self):
        content = self.SCRIPT.read_text()
        assert "journald" in content
        assert "SystemMaxUse" in content
        assert "RuntimeMaxUse" in content

    def test_has_network_tuning(self):
        content = self.SCRIPT.read_text()
        assert "somaxconn" in content
        assert "tcp_fastopen" in content
        assert "ipv6" in content.lower()

    def test_has_cpu_affinity_call(self):
        content = self.SCRIPT.read_text()
        assert "generate-cpu-affinity.sh" in content
        assert "CPU_CORES" in content

    def test_supports_rpi_and_x86(self):
        content = self.SCRIPT.read_text()
        assert "rpi" in content
        assert "x86" in content
        assert "cmdline.txt" in content
        assert "GRUB" in content or "grub" in content

    def test_has_low_ram_mode(self):
        content = self.SCRIPT.read_text()
        assert "LOW_RAM" in content


class TestGenerateCpuAffinity:
    """generate-cpu-affinity.sh script tests."""

    SCRIPT = SCRIPTS / "generate-cpu-affinity.sh"

    def test_exists(self):
        assert self.SCRIPT.exists()

    def test_bash_syntax(self):
        result = subprocess.run(
            ["bash", "-n", str(self.SCRIPT)],
            capture_output=True, text=True,
        )
        assert result.returncode == 0, f"Syntax error: {result.stderr}"

    def test_has_core_detection(self):
        content = self.SCRIPT.read_text()
        assert "nproc" in content
        assert "CPU_CORES" in content

    def test_has_affinity_map(self):
        content = self.SCRIPT.read_text()
        # 4 cekirdek planı
        assert "0-1" in content
        # 8 cekirdek planı
        assert "2-3" in content

    def test_creates_klipper_dropin(self):
        content = self.SCRIPT.read_text()
        assert "klipper.service.d" in content
        assert "CPUAffinity" in content

    def test_creates_ai_monitor_dropin(self):
        content = self.SCRIPT.read_text()
        assert "klipperos-ai-monitor.service.d" in content

    def test_creates_crowsnest_dropin(self):
        content = self.SCRIPT.read_text()
        assert "crowsnest.service.d" in content

    def test_sets_nice_priorities(self):
        content = self.SCRIPT.read_text()
        assert "Nice=-5" in content   # Klipper: yuksek oncelik
        assert "Nice=5" in content    # AI: normal
        assert "Nice=10" in content   # Kamera: dusuk

    def test_daemon_reload(self):
        content = self.SCRIPT.read_text()
        assert "daemon-reload" in content

    def test_skips_low_core_count(self):
        content = self.SCRIPT.read_text()
        assert "lt 4" in content or "< 4" in content


class TestOsTuningService:
    """kos-os-tuning.service systemd unit tests."""

    SERVICE = CONFIG / "systemd" / "kos-os-tuning.service"

    def test_exists(self):
        assert self.SERVICE.exists()

    def test_is_oneshot(self):
        content = self.SERVICE.read_text()
        assert "Type=oneshot" in content
        assert "RemainAfterExit=yes" in content

    def test_ordering(self):
        content = self.SERVICE.read_text()
        assert "After=kos-zram.service" in content
        assert "Before=klipper.service" in content

    def test_exec_start(self):
        content = self.SERVICE.read_text()
        assert "setup-os-tuning.sh" in content

    def test_install_target(self):
        content = self.SERVICE.read_text()
        assert "WantedBy=multi-user.target" in content
