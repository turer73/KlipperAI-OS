"""Network module tests."""
from __future__ import annotations

from unittest.mock import patch, MagicMock, PropertyMock


# ------------------------------------------------------------------
# Import
# ------------------------------------------------------------------

def test_network_import():
    from packages.installer.network import NetworkManager
    assert NetworkManager is not None


# ------------------------------------------------------------------
# check_internet
# ------------------------------------------------------------------

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


# ------------------------------------------------------------------
# _is_nm_running / _ensure_nm
# ------------------------------------------------------------------

def test_is_nm_running_yes():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (True, "")
        assert nm._is_nm_running() is True


def test_is_nm_running_no():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (False, "inactive")
        assert nm._is_nm_running() is False


def test_ensure_nm_already_running():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch.object(nm, "_is_nm_running", return_value=True):
        assert nm._ensure_nm() is True


def test_ensure_nm_needs_start():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    call_count = 0

    def is_running_side_effect():
        nonlocal call_count
        call_count += 1
        return call_count > 1  # ilk cagri False, sonra True

    with patch.object(nm, "_is_nm_running", side_effect=is_running_side_effect):
        with patch.object(nm, "_start_nm", return_value=True):
            assert nm._ensure_nm() is True


# ------------------------------------------------------------------
# _get_wifi_iface
# ------------------------------------------------------------------

def test_get_wifi_iface_found(tmp_path):
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    # /sys/class/net/wlan0/wireless simulasyonu
    wlan_dir = tmp_path / "wlan0" / "wireless"
    wlan_dir.mkdir(parents=True)
    with patch("packages.installer.network.Path") as MockPath:
        net_dir = tmp_path
        MockPath.return_value = net_dir
        result = nm._get_wifi_iface()
    assert result == "wlan0"


def test_get_wifi_iface_not_found(tmp_path):
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    # Sadece lo ve eth0 var, wireless yok
    (tmp_path / "lo").mkdir()
    (tmp_path / "eth0").mkdir()
    with patch("packages.installer.network.Path") as MockPath:
        MockPath.return_value = tmp_path
        result = nm._get_wifi_iface()
    assert result is None


# ------------------------------------------------------------------
# ensure_wifi_up (rfkill dahil)
# ------------------------------------------------------------------

def test_ensure_wifi_up_already_enabled():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.side_effect = [
            (True, ""),        # rfkill unblock
            (True, "enabled"), # nmcli radio wifi
        ]
        result = nm.ensure_wifi_up()
    assert result is True
    assert mock_run.call_count == 2  # rfkill + radio check


def test_ensure_wifi_up_disabled():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.side_effect = [
            (True, ""),         # rfkill unblock
            (True, "disabled"), # nmcli radio wifi check
            (True, ""),         # nmcli radio wifi on
        ]
        with patch("packages.installer.network.time"):
            result = nm.ensure_wifi_up()
    assert result is True
    assert mock_run.call_count == 3


# ------------------------------------------------------------------
# scan_wifi
# ------------------------------------------------------------------

def _mock_scan_wifi_calls(nm_running=True, wifi_iface="wlan0",
                          nmcli_output="MyNet:85\nOther:42\n:10\n"):
    """scan_wifi icin ortak mock yapisi dondur."""
    patches = {}
    patches["ensure_nm"] = patch.object(
        type(nm := None).__mro__[0] if nm else
        __import__("packages.installer.network", fromlist=["NetworkManager"]).NetworkManager,
        "_ensure_nm", return_value=nm_running,
    )
    return patches


def test_scan_wifi_parses_output():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    nmcli_output = "MyNetwork:85\nOtherNet:42\n:10\n"
    with patch.object(nm, "_ensure_nm", return_value=True), \
         patch.object(nm, "_get_wifi_iface", return_value="wlan0"), \
         patch.object(nm, "ensure_wifi_up", return_value=True), \
         patch("packages.installer.network.run_cmd") as mock_run, \
         patch("packages.installer.network.time"):
        mock_run.return_value = (True, nmcli_output)
        networks = nm.scan_wifi()
    assert len(networks) == 2
    assert networks[0] == ("MyNetwork", 85)
    assert networks[1] == ("OtherNet", 42)


def test_scan_wifi_dedup():
    """Ayni SSID birden fazla cikabilir — tekrarlar filtrelenmeli."""
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    nmcli_output = "HomeNet:90\nHomeNet:75\nGuest:60\n"
    with patch.object(nm, "_ensure_nm", return_value=True), \
         patch.object(nm, "_get_wifi_iface", return_value="wlan0"), \
         patch.object(nm, "ensure_wifi_up", return_value=True), \
         patch("packages.installer.network.run_cmd") as mock_run, \
         patch("packages.installer.network.time"):
        mock_run.return_value = (True, nmcli_output)
        networks = nm.scan_wifi()
    assert len(networks) == 2
    ssids = [n[0] for n in networks]
    assert ssids.count("HomeNet") == 1


def test_scan_wifi_nm_not_running():
    """NM calismiyorsa bos liste don."""
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch.object(nm, "_ensure_nm", return_value=False):
        networks = nm.scan_wifi()
    assert networks == []


def test_scan_wifi_no_interface():
    """WiFi arayuzu yoksa bos liste don."""
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch.object(nm, "_ensure_nm", return_value=True), \
         patch.object(nm, "_get_wifi_iface", return_value=None):
        networks = nm.scan_wifi()
    assert networks == []


def test_scan_wifi_empty_retries():
    """Ilk tarama bos donerse ikinci kez dener."""
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    call_count = 0

    def parse_side_effect():
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return []
        return [("LateNet", 70)]

    with patch.object(nm, "_ensure_nm", return_value=True), \
         patch.object(nm, "_get_wifi_iface", return_value="wlan0"), \
         patch.object(nm, "ensure_wifi_up", return_value=True), \
         patch.object(nm, "_parse_wifi_list", side_effect=parse_side_effect), \
         patch("packages.installer.network.run_cmd") as mock_run, \
         patch("packages.installer.network.time"):
        mock_run.return_value = (True, "")  # rescan
        networks = nm.scan_wifi()
    assert len(networks) == 1
    assert networks[0] == ("LateNet", 70)


# ------------------------------------------------------------------
# connect_wifi
# ------------------------------------------------------------------

def test_connect_wifi():
    from packages.installer.network import NetworkManager
    nm = NetworkManager()
    with patch("packages.installer.network.run_cmd") as mock_run:
        mock_run.return_value = (True, "successfully activated")
        with patch("packages.installer.network.time"):
            result = nm.connect_wifi("TestSSID", "password123")
    assert result is True
    assert mock_run.call_count == 2


# ------------------------------------------------------------------
# signal_bars (NetworkStep)
# ------------------------------------------------------------------

def test_signal_bars():
    from packages.installer.steps.network_step import NetworkStep
    assert NetworkStep._signal_bars(90) == "||||"
    assert NetworkStep._signal_bars(70) == "|||."
    assert NetworkStep._signal_bars(50) == "||.."
    assert NetworkStep._signal_bars(30) == "|..."
    assert NetworkStep._signal_bars(10) == "...."
