# tests/test_kos_mcu.py
"""Tests for MCU Management panel."""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ks-panels'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import pytest
from unittest.mock import patch, MagicMock


class TestMCUPanel:
    def test_import(self):
        from kos_mcu_panel import PANEL_TITLE
        assert PANEL_TITLE == "MCU Yonetimi"

    def test_format_port_entry(self):
        from kos_mcu_panel import format_port_entry
        text = format_port_entry({"device": "/dev/ttyACM0", "description": "STM32 Bootloader"})
        assert "/dev/ttyACM0" in text
        assert "STM32" in text

    def test_format_port_entry_no_desc(self):
        from kos_mcu_panel import format_port_entry
        text = format_port_entry({"device": "/dev/ttyUSB0"})
        assert "/dev/ttyUSB0" in text

    def test_format_board_entry(self):
        from kos_mcu_panel import format_board_entry
        text = format_board_entry("btt-skr-mini-e3-v3", {"mcu": "stm32g0b1xx"})
        assert "btt-skr-mini-e3-v3" in text
        assert "stm32g0b1xx" in text

    @patch("tools.kos_mcu.find_serial_ports")
    def test_scan_ports(self, mock_scan):
        mock_scan.return_value = [{"device": "/dev/ttyACM0", "description": "Klipper", "hwid": "1234"}]
        from kos_mcu_panel import scan_ports
        ports = scan_ports()
        assert len(ports) == 1
        assert ports[0]["device"] == "/dev/ttyACM0"

    @patch("tools.kos_mcu.load_board_db")
    def test_get_board_list(self, mock_db):
        mock_db.return_value = {"test-board": {"mcu": "stm32f4"}}
        from kos_mcu_panel import get_board_list
        boards = get_board_list()
        assert "test-board" in boards
