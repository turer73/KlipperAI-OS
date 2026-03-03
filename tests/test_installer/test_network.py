"""Network module tests."""
from __future__ import annotations

from unittest.mock import patch


def test_network_import():
    from packages.installer.network import NetworkManager
    assert NetworkManager is not None


def test_check_internet_connected():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (True, "1.1.1.1")
        assert nm.check_internet() is True


def test_check_internet_disconnected():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (False, "")
        assert nm.check_internet() is False


def test_scan_wifi_parses_output():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    nmcli_output = "MyNetwork:85\nOtherNet:42\n:10\n"
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (True, nmcli_output)
        networks = nm.scan_wifi()
        assert len(networks) == 2  # bos SSID filtrelenir
        assert networks[0] == ("MyNetwork", 85)
        assert networks[1] == ("OtherNet", 42)


def test_scan_wifi_empty():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (False, "")
        networks = nm.scan_wifi()
        assert networks == []


def test_connect_wifi():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (True, "successfully activated")
        result = nm.connect_wifi("TestSSID", "password123")
        assert result is True
        mock_run.assert_called_once()
        call_args = mock_run.call_args[0][0]
        assert "TestSSID" in call_args
        assert "password123" in call_args
