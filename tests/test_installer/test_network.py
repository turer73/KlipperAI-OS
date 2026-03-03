"""Network module tests."""
from __future__ import annotations

from unittest.mock import patch, MagicMock


def test_network_import():
    from packages.installer.network import NetworkManager
    assert NetworkManager is not None


def test_check_internet_connected():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    mock_sock = MagicMock()
    with patch("socket.create_connection", return_value=mock_sock):
        assert nm.check_internet() is True
        mock_sock.close.assert_called_once()


def test_check_internet_disconnected():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("socket.create_connection", side_effect=OSError("timeout")):
        assert nm.check_internet() is False


def test_scan_wifi_parses_output():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    nmcli_output = "MyNetwork:85\nOtherNet:42\n:10\n"
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (True, nmcli_output)
        with patch("packages.installer.network.time"):
            networks = nm.scan_wifi()
    assert len(networks) == 2  # bos SSID filtrelenir
    assert networks[0] == ("MyNetwork", 85)
    assert networks[1] == ("OtherNet", 42)


def test_scan_wifi_dedup():
    """Ayni SSID birden fazla cikabilir — tekrarlar filtrelenmeli."""
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    nmcli_output = "HomeNet:90\nHomeNet:75\nGuest:60\n"
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (True, nmcli_output)
        with patch("packages.installer.network.time"):
            networks = nm.scan_wifi()
    assert len(networks) == 2
    ssids = [n[0] for n in networks]
    assert ssids.count("HomeNet") == 1


def test_scan_wifi_empty():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (False, "")
        with patch("packages.installer.network.time"):
            networks = nm.scan_wifi()
    assert networks == []


def test_connect_wifi():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (True, "successfully activated")
        with patch("packages.installer.network.time"):
            result = nm.connect_wifi("TestSSID", "password123")
    assert result is True
    # connect cagrisi yapilmis olmali (delete + connect = 2 cagri)
    assert mock_run.call_count == 2


def test_ensure_wifi_up_already_enabled():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (True, "enabled")
        result = nm.ensure_wifi_up()
    assert result is True
    mock_run.assert_called_once()


def test_ensure_wifi_up_disabled():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.side_effect = [
            (True, "disabled"),  # radio wifi check
            (True, ""),          # radio wifi on
        ]
        with patch("packages.installer.network.time"):
            result = nm.ensure_wifi_up()
    assert result is True
    assert mock_run.call_count == 2


def test_signal_bars():
    from packages.installer.steps.network_step import NetworkStep
    assert NetworkStep._signal_bars(90) == "||||"
    assert NetworkStep._signal_bars(70) == "|||."
    assert NetworkStep._signal_bars(50) == "||.."
    assert NetworkStep._signal_bars(30) == "|..."
    assert NetworkStep._signal_bars(10) == "...."
