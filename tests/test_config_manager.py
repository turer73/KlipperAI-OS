"""Tests for AI Config Manager."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))

import pytest
from unittest.mock import patch, MagicMock
from config_manager import ConfigManager, ConfigChange


SAMPLE_CONFIG = """\
[extruder]
pid_kp = 22.5
pid_ki = 1.1
pid_kd = 95.0
pressure_advance = 0.05

[heater_bed]
pid_kp = 60.0
pid_ki = 0.5
pid_kd = 300.0

[input_shaper]
shaper_freq_x = 48.6
shaper_freq_y = 36.2
shaper_type_x = mzv
shaper_type_y = ei
"""


class TestConfigParsing:
    def test_parse_sections(self):
        cm = ConfigManager("http://localhost:7125")
        sections = cm.parse_sections(SAMPLE_CONFIG)
        assert "extruder" in sections
        assert sections["extruder"]["pid_kp"] == "22.5"
        assert sections["heater_bed"]["pid_kd"] == "300.0"
        assert sections["input_shaper"]["shaper_type_x"] == "mzv"

    def test_update_value(self):
        cm = ConfigManager("http://localhost:7125")
        updated = cm.update_value(SAMPLE_CONFIG, "extruder", "pid_kp", "25.0")
        sections = cm.parse_sections(updated)
        assert sections["extruder"]["pid_kp"] == "25.0"
        # Other values unchanged
        assert sections["extruder"]["pid_ki"] == "1.1"

    def test_update_nonexistent_key_appends(self):
        cm = ConfigManager("http://localhost:7125")
        updated = cm.update_value(SAMPLE_CONFIG, "extruder", "rotation_distance", "7.82")
        sections = cm.parse_sections(updated)
        assert sections["extruder"]["rotation_distance"] == "7.82"
        # Original keys still present
        assert sections["extruder"]["pid_kp"] == "22.5"


class TestWhitelist:
    def test_allowed_params_pass(self):
        cm = ConfigManager("http://localhost:7125")
        assert cm.is_allowed("extruder", "pid_kp") is True
        assert cm.is_allowed("extruder", "pressure_advance") is True
        assert cm.is_allowed("heater_bed", "pid_ki") is True
        assert cm.is_allowed("input_shaper", "shaper_freq_x") is True
        assert cm.is_allowed("kos_flowguard", "heater_threshold") is True

    def test_blocked_params_fail(self):
        cm = ConfigManager("http://localhost:7125")
        assert cm.is_allowed("extruder", "step_pin") is False
        assert cm.is_allowed("stepper_x", "position_max") is False
        assert cm.is_allowed("mcu", "serial") is False


class TestConfigChange:
    def test_creation(self):
        change = ConfigChange(
            section="extruder",
            key="pid_kp",
            old_value="22.5",
            new_value="25.0",
            reason="PID autotune result",
        )
        assert change.section == "extruder"
        assert change.key == "pid_kp"
        assert change.old_value == "22.5"
        assert change.new_value == "25.0"
        assert change.reason == "PID autotune result"
        assert change.timestamp != ""

    def test_str_representation(self):
        change = ConfigChange(
            section="extruder",
            key="pid_kp",
            old_value="22.5",
            new_value="25.0",
            reason="PID autotune",
        )
        s = str(change)
        assert "[extruder]" in s
        assert "pid_kp" in s
        assert "22.5" in s
        assert "25.0" in s
        assert "PID autotune" in s


class TestApplyChanges:
    @patch.object(ConfigManager, "read_config")
    @patch.object(ConfigManager, "write_config")
    @patch.object(ConfigManager, "send_notification")
    def test_successful_apply(self, mock_notify, mock_write, mock_read):
        mock_read.return_value = SAMPLE_CONFIG
        mock_write.return_value = True

        cm = ConfigManager("http://localhost:7125")
        changes = [
            ConfigChange(
                section="extruder",
                key="pid_kp",
                old_value="22.5",
                new_value="25.0",
                reason="PID autotune",
            )
        ]
        result = cm.apply_changes("printer.cfg", changes)
        assert result is True
        mock_read.assert_called_once_with("printer.cfg")
        mock_write.assert_called_once()
        mock_notify.assert_called_once()
        assert len(cm.change_log) == 1

    @patch.object(ConfigManager, "read_config")
    def test_blocked_param_returns_false(self, mock_read):
        mock_read.return_value = SAMPLE_CONFIG

        cm = ConfigManager("http://localhost:7125")
        changes = [
            ConfigChange(
                section="mcu",
                key="serial",
                old_value="/dev/ttyACM0",
                new_value="/dev/ttyUSB0",
                reason="change port",
            )
        ]
        result = cm.apply_changes("printer.cfg", changes)
        assert result is False
