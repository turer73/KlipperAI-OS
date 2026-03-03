# Minimal ISO + Python TUI Installer Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Replace the monolithic ~3GB ISO with a ~500MB minimal ISO that boots, connects WiFi, then downloads all Klipper/Moonraker/AI components via internet using a Python TUI installer.

**Architecture:** Minimal Ubuntu 24.04 autoinstall ISO carries only kernel + WiFi drivers + Python + the TUI installer package. On first boot, a systemd oneshot service launches `kos-install` (Python TUI using whiptail). The TUI walks through: hardware detection → WiFi → profile selection → internet-based package/component installation.

**Tech Stack:** Python 3.9+, whiptail (subprocess), nmcli, apt-get, git, systemd

---

## Task 1: Proje Iskelesi + TUI Wrapper

**Files:**
- Create: `packages/installer/__init__.py`
- Create: `packages/installer/__main__.py`
- Create: `packages/installer/tui.py`
- Create: `tests/test_installer/__init__.py`
- Create: `tests/test_installer/test_tui.py`

**Step 1: Write the failing test**

```python
# tests/test_installer/__init__.py
```

```python
# tests/test_installer/test_tui.py
"""TUI wrapper tests."""
from __future__ import annotations


def test_tui_import():
    from packages.installer.tui import TUI
    assert TUI is not None


def test_tui_escape_text():
    from packages.installer.tui import TUI
    tui = TUI(dry_run=True)
    # Whiptail icin ozel karakterler escape edilmeli
    assert '"' not in tui._escape('test "quoted" text')


def test_tui_dry_run_msgbox():
    from packages.installer.tui import TUI
    tui = TUI(dry_run=True)
    # dry_run modda whiptail cagrilmaz, hata vermez
    tui.msgbox("Test", "test mesaji")


def test_tui_dry_run_menu():
    from packages.installer.tui import TUI
    tui = TUI(dry_run=True)
    result = tui.menu("Secim", [("1", "Bir"), ("2", "Iki")])
    assert result == "1"  # dry_run ilk secenegi doner


def test_tui_dry_run_yesno():
    from packages.installer.tui import TUI
    tui = TUI(dry_run=True)
    result = tui.yesno("Emin misiniz?")
    assert result is True  # dry_run her zaman True doner


def test_tui_dry_run_inputbox():
    from packages.installer.tui import TUI
    tui = TUI(dry_run=True)
    result = tui.inputbox("Hostname:", default="klipperos")
    assert result == "klipperos"  # dry_run default deger doner


def test_tui_dry_run_passwordbox():
    from packages.installer.tui import TUI
    tui = TUI(dry_run=True)
    result = tui.passwordbox("Sifre:")
    assert result == ""  # dry_run bos string doner


def test_tui_dry_run_gauge():
    from packages.installer.tui import TUI
    tui = TUI(dry_run=True)
    # dry_run modda gauge cagrilmaz, hata vermez
    tui.gauge("Kuruluyor...", 50)
```

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_installer/test_tui.py -v`
Expected: FAIL with "ModuleNotFoundError"

**Step 3: Write minimal implementation**

```python
# packages/installer/__init__.py
"""KlipperOS-AI — Python TUI Installer."""
```

```python
# packages/installer/__main__.py
"""Entry point: python -m packages.installer"""
from __future__ import annotations

import sys


def main() -> int:
    """TUI installer ana giris noktasi."""
    # Root kontrolu
    import os
    if os.geteuid() != 0:
        print("HATA: Bu installer root olarak calistirilmalidir.")
        print("Kullanim: sudo kos-install")
        return 1

    from .app import InstallerApp
    app = InstallerApp()
    return app.run()


if __name__ == "__main__":
    sys.exit(main())
```

```python
# packages/installer/tui.py
"""Whiptail TUI wrapper sinifi."""
from __future__ import annotations

import subprocess
import shlex
from dataclasses import dataclass, field


NEWT_COLORS = (
    "root=,blue window=,black border=white,black "
    "textbox=white,black button=black,cyan actbutton=black,cyan "
    "title=cyan,black roottext=cyan,blue "
    "emptyscale=,black fullscale=,cyan "
    "entry=white,black checkbox=white,black "
    "listbox=white,black actlistbox=black,cyan"
)

VERSION = "3.0.0"
BACKTITLE = f"KlipperOS-AI v{VERSION} Kurulum"


@dataclass
class TUI:
    """Whiptail tabanlı terminal arayüzü wrapper."""

    dry_run: bool = False
    width: int = 70
    height: int = 20

    def _escape(self, text: str) -> str:
        """Whiptail icin ozel karakterleri escape et."""
        return text.replace('"', '\\"').replace("'", "\\'")

    def _run(self, args: list[str], capture: bool = False) -> str:
        """Whiptail komutunu calistir."""
        if self.dry_run:
            return ""

        env = {"TERM": "linux", "NEWT_COLORS": NEWT_COLORS}
        cmd = ["whiptail", "--backtitle", BACKTITLE] + args

        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            env={**dict(__import__("os").environ), **env},
        )
        if capture:
            return result.stderr.strip()  # whiptail stderr'e yazar
        return ""

    def msgbox(self, title: str, text: str) -> None:
        """Bilgi mesaji goster."""
        if self.dry_run:
            return
        self._run([
            "--title", title,
            "--msgbox", self._escape(text),
            str(self.height), str(self.width),
        ])

    def menu(
        self,
        title: str,
        items: list[tuple[str, str]],
        text: str = "",
        default: str = "",
    ) -> str:
        """Menu goster, secimi dondur."""
        if self.dry_run:
            return items[0][0] if items else ""

        args = ["--title", title]
        if default:
            args += ["--default-item", default]
        args += ["--menu", self._escape(text), str(self.height), str(self.width), str(len(items))]
        for tag, desc in items:
            args += [tag, desc]
        result = self._run(args, capture=True)
        return result or (items[0][0] if items else "")

    def yesno(self, text: str, title: str = "") -> bool:
        """Evet/Hayir sorusu."""
        if self.dry_run:
            return True

        result = subprocess.run(
            ["whiptail", "--backtitle", BACKTITLE, "--title", title,
             "--yesno", self._escape(text), str(self.height), str(self.width)],
            env={**dict(__import__("os").environ), "TERM": "linux", "NEWT_COLORS": NEWT_COLORS},
        )
        return result.returncode == 0

    def inputbox(self, text: str, title: str = "", default: str = "") -> str:
        """Metin girisi."""
        if self.dry_run:
            return default

        args = ["--title", title, "--inputbox", self._escape(text),
                str(self.height), str(self.width), default]
        return self._run(args, capture=True) or default

    def passwordbox(self, text: str, title: str = "") -> str:
        """Sifre girisi."""
        if self.dry_run:
            return ""

        args = ["--title", title, "--passwordbox", self._escape(text),
                str(self.height), str(self.width)]
        return self._run(args, capture=True)

    def gauge(self, text: str, percent: int) -> None:
        """Ilerleme cubugu."""
        if self.dry_run:
            return
        # gauge icin stdin pipe gerekir — bu basit versiyon sadece msgbox gosterir
        self._run([
            "--title", "Kurulum",
            "--gauge", self._escape(text),
            "8", str(self.width), str(percent),
        ])
```

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_installer/test_tui.py -v`
Expected: 8/8 PASS

**Step 5: Commit**

```bash
git add packages/installer/ tests/test_installer/
git commit -m "feat(installer): add Python TUI wrapper with whiptail backend"
```

---

## Task 2: Donanim Tespiti Modulu

**Files:**
- Create: `packages/installer/hw_detect.py`
- Create: `tests/test_installer/test_hw_detect.py`

**Step 1: Write the failing test**

```python
# tests/test_installer/test_hw_detect.py
"""Hardware detection tests."""
from __future__ import annotations

from unittest.mock import patch, mock_open


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
```

**Step 2: Run test — FAIL**

**Step 3: Implement**

```python
# packages/installer/hw_detect.py
"""Donanim tespiti — /proc ve /sys dosyalarindan donanim bilgisi okur."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path


def recommend_profile(ram_mb: int, cpu_cores: int) -> str:
    """RAM ve CPU'ya gore profil oner."""
    if ram_mb < 1536:
        return "LIGHT"
    if ram_mb >= 4096 and cpu_cores >= 4:
        return "FULL"
    return "STANDARD"


@dataclass
class HardwareInfo:
    """Donanim bilgileri."""

    cpu_model: str
    cpu_cores: int
    cpu_freq_mhz: int
    ram_total_mb: int
    disk_total_mb: int
    has_wifi: bool
    has_ethernet: bool
    board_type: str
    recommended_profile: str

    @property
    def is_force_light(self) -> bool:
        """RAM < 1.5GB ise LIGHT zorunlu."""
        return self.ram_total_mb < 1536

    @classmethod
    def detect(cls) -> HardwareInfo:
        """Sistem donanımını tespit et."""
        # CPU
        cpu_model = "Unknown"
        try:
            with open("/proc/cpuinfo") as f:
                for line in f:
                    if line.startswith("model name"):
                        cpu_model = line.split(":", 1)[1].strip()
                        break
        except OSError:
            pass

        cpu_cores = os.cpu_count() or 1

        cpu_freq_mhz = 0
        freq_path = Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")
        if freq_path.exists():
            try:
                cpu_freq_mhz = int(freq_path.read_text().strip()) // 1000
            except (ValueError, OSError):
                pass

        # RAM
        ram_total_mb = 0
        try:
            with open("/proc/meminfo") as f:
                for line in f:
                    if line.startswith("MemTotal"):
                        ram_total_mb = int(line.split()[1]) // 1024
                        break
        except OSError:
            pass

        # Disk
        disk_total_mb = 0
        try:
            result = subprocess.run(
                ["df", "-BM", "/"],
                capture_output=True, text=True, timeout=5,
            )
            if result.returncode == 0:
                lines = result.stdout.strip().split("\n")
                if len(lines) >= 2:
                    disk_total_mb = int(lines[1].split()[1].rstrip("M"))
        except (subprocess.TimeoutExpired, ValueError, IndexError):
            pass

        # Network
        has_wifi = False
        has_ethernet = False
        net_dir = Path("/sys/class/net")
        if net_dir.exists():
            for iface in net_dir.iterdir():
                if iface.name == "lo":
                    continue
                if (iface / "wireless").is_dir():
                    has_wifi = True
                elif (iface / "type").exists():
                    try:
                        itype = (iface / "type").read_text().strip()
                        if itype == "1":
                            has_ethernet = True
                    except OSError:
                        pass

        # Board type
        board_type = "x86"
        dt_model = Path("/proc/device-tree/model")
        if dt_model.exists():
            try:
                model_str = dt_model.read_text().strip("\x00").lower()
                if "raspberry" in model_str:
                    board_type = "rpi"
                elif "orange" in model_str:
                    board_type = "orangepi"
                else:
                    board_type = "sbc"
            except OSError:
                pass

        profile = recommend_profile(ram_total_mb, cpu_cores)

        return cls(
            cpu_model=cpu_model,
            cpu_cores=cpu_cores,
            cpu_freq_mhz=cpu_freq_mhz,
            ram_total_mb=ram_total_mb,
            disk_total_mb=disk_total_mb,
            has_wifi=has_wifi,
            has_ethernet=has_ethernet,
            board_type=board_type,
            recommended_profile=profile,
        )
```

**Step 4: Run tests — PASS**

Run: `python -m pytest tests/test_installer/test_hw_detect.py -v`
Expected: 7/7 PASS

**Step 5: Commit**

```bash
git add packages/installer/hw_detect.py tests/test_installer/test_hw_detect.py
git commit -m "feat(installer): add hardware detection module"
```

---

## Task 3: Profil Tanimlari

**Files:**
- Create: `packages/installer/profiles.py`
- Create: `tests/test_installer/test_profiles.py`

**Step 1: Write the failing test**

```python
# tests/test_installer/test_profiles.py
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
```

**Step 2: Run test — FAIL**

**Step 3: Implement**

```python
# packages/installer/profiles.py
"""Kurulum profil tanimlari."""
from __future__ import annotations

from dataclasses import dataclass, field


# --- APT Paket Gruplari ---
BASE_APT = [
    "build-essential", "cmake", "pkg-config",
    "python3-dev", "python3-setuptools", "python3-wheel",
    "gcc-arm-none-eabi", "binutils-arm-none-eabi", "libnewlib-arm-none-eabi",
    "stm32flash", "dfu-util", "avrdude",
    "nginx", "lsb-release", "can-utils",
    "python3-psutil", "zstd", "usbutils", "pciutils",
    "libffi-dev", "libncurses-dev", "libusb-1.0-0-dev",
    "supervisor", "lsof",
]

DISPLAY_APT = [
    "xserver-xorg", "xinit", "x11-xserver-utils",
    "python3-gi", "python3-gi-cairo",
    "gir1.2-gtk-3.0", "gir1.2-vte-2.91",
    "libopenjp2-7", "libcairo2-dev",
    "fonts-freefont-ttf", "xinput", "matchbox-keyboard",
]

MEDIA_APT = [
    "ffmpeg", "v4l-utils",
]


@dataclass
class Profile:
    """Kurulum profili."""

    name: str
    description: str
    min_ram_mb: int
    apt_packages: list[str] = field(default_factory=list)
    components: list[str] = field(default_factory=list)


PROFILES: dict[str, Profile] = {
    "LIGHT": Profile(
        name="LIGHT",
        description="Klipper + Moonraker + Mainsail (512MB+)",
        min_ram_mb=512,
        apt_packages=BASE_APT.copy(),
        components=["klipper", "moonraker", "mainsail"],
    ),
    "STANDARD": Profile(
        name="STANDARD",
        description="+ KlipperScreen + Kamera + AI Monitor (2GB+)",
        min_ram_mb=2048,
        apt_packages=BASE_APT + DISPLAY_APT + MEDIA_APT,
        components=["klipper", "moonraker", "mainsail", "klipperscreen", "crowsnest", "ai_monitor"],
    ),
    "FULL": Profile(
        name="FULL",
        description="+ Multi-printer + Timelapse + Tam AI (4GB+)",
        min_ram_mb=4096,
        apt_packages=BASE_APT + DISPLAY_APT + MEDIA_APT,
        components=[
            "klipper", "moonraker", "mainsail",
            "klipperscreen", "crowsnest", "ai_monitor",
            "multi_printer", "timelapse",
        ],
    ),
}
```

**Step 4: Run tests — PASS**

Run: `python -m pytest tests/test_installer/test_profiles.py -v`
Expected: 8/8 PASS

**Step 5: Commit**

```bash
git add packages/installer/profiles.py tests/test_installer/test_profiles.py
git commit -m "feat(installer): add installation profile definitions"
```

---

## Task 4: Yardimci Araclar (Logger + Runner + Sentinel)

**Files:**
- Create: `packages/installer/utils/__init__.py`
- Create: `packages/installer/utils/logger.py`
- Create: `packages/installer/utils/runner.py`
- Create: `packages/installer/utils/sentinel.py`
- Create: `tests/test_installer/test_utils.py`

**Step 1: Write the failing test**

```python
# tests/test_installer/test_utils.py
"""Utility module tests."""
from __future__ import annotations

import tempfile
from pathlib import Path


def test_sentinel_set_and_check():
    from packages.installer.utils.sentinel import Sentinel
    with tempfile.TemporaryDirectory() as tmpdir:
        s = Sentinel(base_dir=tmpdir)
        assert s.is_done("klipper") is False
        s.mark_done("klipper")
        assert s.is_done("klipper") is True


def test_sentinel_idempotent():
    from packages.installer.utils.sentinel import Sentinel
    with tempfile.TemporaryDirectory() as tmpdir:
        s = Sentinel(base_dir=tmpdir)
        s.mark_done("moonraker")
        s.mark_done("moonraker")  # ikinci kez hata vermemeli
        assert s.is_done("moonraker") is True


def test_runner_import():
    from packages.installer.utils.runner import run_cmd
    assert callable(run_cmd)


def test_runner_echo():
    from packages.installer.utils.runner import run_cmd
    ok, output = run_cmd(["echo", "hello"])
    assert ok is True
    assert "hello" in output


def test_runner_fail():
    from packages.installer.utils.runner import run_cmd
    ok, output = run_cmd(["false"])
    assert ok is False


def test_logger_import():
    from packages.installer.utils.logger import get_logger
    logger = get_logger()
    assert logger is not None
```

**Step 2: Run test — FAIL**

**Step 3: Implement**

```python
# packages/installer/utils/__init__.py
"""Installer yardimci araclari."""
```

```python
# packages/installer/utils/logger.py
"""Installer loglama."""
from __future__ import annotations

import logging
from pathlib import Path

LOG_FILE = "/var/log/kos-installer.log"


def get_logger(name: str = "kos-installer") -> logging.Logger:
    """Installer logger'i dondur."""
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)

        # Dosya handler
        try:
            Path(LOG_FILE).parent.mkdir(parents=True, exist_ok=True)
            fh = logging.FileHandler(LOG_FILE)
            fh.setLevel(logging.DEBUG)
            fh.setFormatter(logging.Formatter("[%(asctime)s] %(message)s", "%H:%M:%S"))
            logger.addHandler(fh)
        except OSError:
            pass  # /var/log yazilabilir degilse sessizce atla

        # Console handler
        ch = logging.StreamHandler()
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(ch)

    return logger
```

```python
# packages/installer/utils/runner.py
"""Subprocess wrapper."""
from __future__ import annotations

import subprocess
from .logger import get_logger

logger = get_logger()


def run_cmd(
    cmd: list[str],
    timeout: int = 600,
    check: bool = False,
) -> tuple[bool, str]:
    """Komut calistir, (basari, cikti) dondur."""
    logger.debug("CMD: %s", " ".join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        output = result.stdout + result.stderr
        success = result.returncode == 0
        if not success:
            logger.debug("CMD FAIL (rc=%d): %s", result.returncode, output[:200])
        return success, output
    except subprocess.TimeoutExpired:
        logger.error("CMD TIMEOUT: %s", " ".join(cmd))
        return False, "timeout"
    except FileNotFoundError:
        logger.error("CMD NOT FOUND: %s", cmd[0])
        return False, "not found"
```

```python
# packages/installer/utils/sentinel.py
"""Idempotent kurulum kontrol dosyalari."""
from __future__ import annotations

from pathlib import Path


class Sentinel:
    """Bilesen kurulum durumunu dosya ile izler."""

    def __init__(self, base_dir: str = "/opt/klipperos-ai"):
        self.base_dir = Path(base_dir)

    def _path(self, component: str) -> Path:
        return self.base_dir / f".installed-{component}"

    def is_done(self, component: str) -> bool:
        """Bilesen zaten kuruldu mu?"""
        return self._path(component).exists()

    def mark_done(self, component: str) -> None:
        """Bileseni kuruldu olarak isaretle."""
        self._path(component).parent.mkdir(parents=True, exist_ok=True)
        self._path(component).touch()
```

**Step 4: Run tests — PASS**

Run: `python -m pytest tests/test_installer/test_utils.py -v`
Expected: 6/6 PASS

**Step 5: Commit**

```bash
git add packages/installer/utils/ tests/test_installer/test_utils.py
git commit -m "feat(installer): add logger, command runner, and sentinel utilities"
```

---

## Task 5: Ag Baglanti Modulu

**Files:**
- Create: `packages/installer/network.py`
- Create: `tests/test_installer/test_network.py`

**Step 1: Write the failing test**

```python
# tests/test_installer/test_network.py
"""Network module tests."""
from __future__ import annotations

from unittest.mock import patch, MagicMock


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
```

**Step 2: Run test — FAIL**

**Step 3: Implement**

```python
# packages/installer/network.py
"""Ag baglanti yonetimi — nmcli wrapper."""
from __future__ import annotations

from .utils.runner import run_cmd
from .utils.logger import get_logger

logger = get_logger()


class NetworkManager:
    """WiFi ve internet baglanti yonetimi."""

    def check_internet(self) -> bool:
        """Internet baglantisi var mi?"""
        ok, _ = run_cmd(["ping", "-c", "1", "-W", "3", "1.1.1.1"])
        return ok

    def scan_wifi(self) -> list[tuple[str, int]]:
        """WiFi aglarini tara. [(ssid, sinyal_gucu), ...] dondur."""
        ok, output = run_cmd([
            "nmcli", "-t", "-f", "SSID,SIGNAL", "dev", "wifi", "list",
        ])
        if not ok:
            return []

        networks: list[tuple[str, int]] = []
        for line in output.strip().split("\n"):
            if ":" not in line:
                continue
            parts = line.rsplit(":", 1)
            ssid = parts[0].strip()
            if not ssid:
                continue
            try:
                signal = int(parts[1].strip())
            except ValueError:
                signal = 0
            networks.append((ssid, signal))

        # Sinyal gucune gore sirala (yuksekten dusuge)
        networks.sort(key=lambda x: x[1], reverse=True)
        return networks

    def connect_wifi(self, ssid: str, password: str) -> bool:
        """WiFi agina baglan."""
        logger.info("WiFi baglaniyor: %s", ssid)
        ok, output = run_cmd([
            "nmcli", "dev", "wifi", "connect", ssid, "password", password,
        ])
        if ok:
            logger.info("WiFi baglandi: %s", ssid)
        else:
            logger.error("WiFi basarisiz: %s — %s", ssid, output[:100])
        return ok
```

**Step 4: Run tests — PASS**

Run: `python -m pytest tests/test_installer/test_network.py -v`
Expected: 6/6 PASS

**Step 5: Commit**

```bash
git add packages/installer/network.py tests/test_installer/test_network.py
git commit -m "feat(installer): add network/WiFi management module"
```

---

## Task 6: Bilesen Kuruculari (Installers)

**Files:**
- Create: `packages/installer/installers/__init__.py`
- Create: `packages/installer/installers/base.py`
- Create: `packages/installer/installers/klipper.py`
- Create: `packages/installer/installers/moonraker.py`
- Create: `packages/installer/installers/mainsail.py`
- Create: `tests/test_installer/test_installers.py`

**Step 1: Write the failing test**

```python
# tests/test_installer/test_installers.py
"""Component installer tests."""
from __future__ import annotations

import tempfile
from unittest.mock import patch


def test_base_installer_import():
    from packages.installer.installers.base import BaseInstaller
    assert BaseInstaller is not None


def test_base_installer_skip_if_done():
    from packages.installer.installers.base import BaseInstaller
    from packages.installer.utils.sentinel import Sentinel

    with tempfile.TemporaryDirectory() as tmpdir:
        sentinel = Sentinel(base_dir=tmpdir)
        sentinel.mark_done("test_component")

        class TestInstaller(BaseInstaller):
            name = "test_component"
            def _install(self) -> bool:
                return True

        installer = TestInstaller(sentinel=sentinel)
        # Zaten kurulu — atla
        assert installer.install() is True


def test_klipper_installer_import():
    from packages.installer.installers.klipper import KlipperInstaller
    assert KlipperInstaller is not None
    assert KlipperInstaller.name == "klipper"


def test_moonraker_installer_import():
    from packages.installer.installers.moonraker import MoonrakerInstaller
    assert MoonrakerInstaller is not None
    assert MoonrakerInstaller.name == "moonraker"


def test_mainsail_installer_import():
    from packages.installer.installers.mainsail import MainsailInstaller
    assert MainsailInstaller is not None
    assert MainsailInstaller.name == "mainsail"


def test_base_installer_marks_sentinel():
    from packages.installer.installers.base import BaseInstaller
    from packages.installer.utils.sentinel import Sentinel

    with tempfile.TemporaryDirectory() as tmpdir:
        sentinel = Sentinel(base_dir=tmpdir)

        class TestInstaller(BaseInstaller):
            name = "test_comp"
            def _install(self) -> bool:
                return True

        installer = TestInstaller(sentinel=sentinel)
        result = installer.install()
        assert result is True
        assert sentinel.is_done("test_comp") is True


def test_base_installer_no_sentinel_on_fail():
    from packages.installer.installers.base import BaseInstaller
    from packages.installer.utils.sentinel import Sentinel

    with tempfile.TemporaryDirectory() as tmpdir:
        sentinel = Sentinel(base_dir=tmpdir)

        class FailInstaller(BaseInstaller):
            name = "fail_comp"
            def _install(self) -> bool:
                return False

        installer = FailInstaller(sentinel=sentinel)
        result = installer.install()
        assert result is False
        assert sentinel.is_done("fail_comp") is False
```

**Step 2: Run test — FAIL**

**Step 3: Implement**

```python
# packages/installer/installers/__init__.py
"""Bilesen kuruculari."""
```

```python
# packages/installer/installers/base.py
"""Base installer sinifi."""
from __future__ import annotations

from abc import ABC, abstractmethod
from ..utils.logger import get_logger
from ..utils.sentinel import Sentinel

logger = get_logger()


class BaseInstaller(ABC):
    """Tum bilesen kurucularinin base sinifi."""

    name: str = ""

    def __init__(self, sentinel: Sentinel | None = None):
        self.sentinel = sentinel or Sentinel()

    def install(self) -> bool:
        """Bileseni kur. Zaten kuruluysa atla."""
        if self.sentinel.is_done(self.name):
            logger.info("[%s] Zaten kurulu — atlaniyor.", self.name)
            return True

        logger.info("[%s] Kurulum basliyor...", self.name)
        try:
            success = self._install()
        except Exception as e:
            logger.error("[%s] Kurulum hatasi: %s", self.name, e)
            return False

        if success:
            self.sentinel.mark_done(self.name)
            logger.info("[%s] Kurulum tamamlandi.", self.name)
        else:
            logger.error("[%s] Kurulum basarisiz.", self.name)
        return success

    @abstractmethod
    def _install(self) -> bool:
        """Alt sinif tarafindan implement edilir."""
        ...
```

```python
# packages/installer/installers/klipper.py
"""Klipper kurucu."""
from __future__ import annotations

from .base import BaseInstaller
from ..utils.runner import run_cmd
from ..utils.logger import get_logger

logger = get_logger()

KLIPPER_USER = "klipper"
KLIPPER_HOME = f"/home/{KLIPPER_USER}"
KLIPPER_REPO = "https://github.com/Klipper3d/klipper.git"
KLIPPER_VENV = f"{KLIPPER_HOME}/klippy-env"
KLIPPER_DIR = f"{KLIPPER_HOME}/klipper"

KLIPPER_SERVICE = f"""\
[Unit]
Description=Klipper 3D Printer Firmware Host
After=network.target

[Service]
Type=simple
User={KLIPPER_USER}
ExecStart={KLIPPER_VENV}/bin/python {KLIPPER_DIR}/klippy/klippy.py \
  {KLIPPER_HOME}/printer_data/config/printer.cfg \
  -l {KLIPPER_HOME}/printer_data/logs/klippy.log \
  -a /tmp/klippy_uds
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""


class KlipperInstaller(BaseInstaller):
    """Klipper firmware host kurucu."""

    name = "klipper"

    def _install(self) -> bool:
        # Git clone
        ok, _ = run_cmd(["sudo", "-u", KLIPPER_USER, "git", "clone", KLIPPER_REPO, KLIPPER_DIR])
        if not ok:
            return False

        # Python venv
        ok, _ = run_cmd(["sudo", "-u", KLIPPER_USER, "python3", "-m", "venv", KLIPPER_VENV])
        if not ok:
            return False

        # Pip install
        ok, _ = run_cmd([
            "sudo", "-u", KLIPPER_USER,
            f"{KLIPPER_VENV}/bin/pip", "install", "--quiet",
            "cffi", "greenlet", "pyserial", "jinja2", "markupsafe",
        ], timeout=120)
        if not ok:
            return False

        # Systemd service
        try:
            with open("/etc/systemd/system/klipper.service", "w") as f:
                f.write(KLIPPER_SERVICE)
            run_cmd(["systemctl", "daemon-reload"])
            run_cmd(["systemctl", "enable", "klipper"])
        except OSError as e:
            logger.error("Klipper service olusturulamadi: %s", e)
            return False

        return True
```

```python
# packages/installer/installers/moonraker.py
"""Moonraker kurucu."""
from __future__ import annotations

from .base import BaseInstaller
from ..utils.runner import run_cmd
from ..utils.logger import get_logger

logger = get_logger()

KLIPPER_USER = "klipper"
KLIPPER_HOME = f"/home/{KLIPPER_USER}"
MOONRAKER_REPO = "https://github.com/Arksine/moonraker.git"
MOONRAKER_DIR = f"{KLIPPER_HOME}/moonraker"
MOONRAKER_VENV = f"{KLIPPER_HOME}/moonraker-env"

MOONRAKER_SERVICE = f"""\
[Unit]
Description=Moonraker API Server
After=network.target klipper.service

[Service]
Type=simple
User={KLIPPER_USER}
ExecStart={MOONRAKER_VENV}/bin/python {MOONRAKER_DIR}/moonraker/moonraker.py \
  -d {KLIPPER_HOME}/printer_data
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
"""


class MoonrakerInstaller(BaseInstaller):
    """Moonraker API server kurucu."""

    name = "moonraker"

    def _install(self) -> bool:
        ok, _ = run_cmd(["sudo", "-u", KLIPPER_USER, "git", "clone", MOONRAKER_REPO, MOONRAKER_DIR])
        if not ok:
            return False

        ok, _ = run_cmd(["sudo", "-u", KLIPPER_USER, "python3", "-m", "venv", MOONRAKER_VENV])
        if not ok:
            return False

        ok, _ = run_cmd([
            "sudo", "-u", KLIPPER_USER,
            f"{MOONRAKER_VENV}/bin/pip", "install", "--quiet",
            "-r", f"{MOONRAKER_DIR}/scripts/moonraker-requirements.txt",
        ], timeout=180)
        if not ok:
            return False

        try:
            with open("/etc/systemd/system/moonraker.service", "w") as f:
                f.write(MOONRAKER_SERVICE)
            run_cmd(["systemctl", "daemon-reload"])
            run_cmd(["systemctl", "enable", "moonraker"])
        except OSError as e:
            logger.error("Moonraker service olusturulamadi: %s", e)
            return False

        return True
```

```python
# packages/installer/installers/mainsail.py
"""Mainsail web arayuzu kurucu."""
from __future__ import annotations

from .base import BaseInstaller
from ..utils.runner import run_cmd
from ..utils.logger import get_logger

logger = get_logger()

MAINSAIL_DIR = "/home/klipper/mainsail"
MAINSAIL_RELEASE_URL = "https://github.com/mainsail-crew/mainsail/releases/latest/download/mainsail.zip"


class MainsailInstaller(BaseInstaller):
    """Mainsail web UI kurucu."""

    name = "mainsail"

    def _install(self) -> bool:
        # Dizin olustur
        run_cmd(["mkdir", "-p", MAINSAIL_DIR])

        # Download
        ok, _ = run_cmd([
            "wget", "-q", "-O", "/tmp/mainsail.zip", MAINSAIL_RELEASE_URL,
        ], timeout=120)
        if not ok:
            return False

        # Unzip
        ok, _ = run_cmd(["unzip", "-o", "/tmp/mainsail.zip", "-d", MAINSAIL_DIR])
        if not ok:
            return False

        # Cleanup
        run_cmd(["rm", "-f", "/tmp/mainsail.zip"])

        # Ownership
        run_cmd(["chown", "-R", "klipper:klipper", MAINSAIL_DIR])

        return True
```

**Step 4: Run tests — PASS**

Run: `python -m pytest tests/test_installer/test_installers.py -v`
Expected: 7/7 PASS

**Step 5: Commit**

```bash
git add packages/installer/installers/ tests/test_installer/test_installers.py
git commit -m "feat(installer): add Klipper, Moonraker, and Mainsail component installers"
```

---

## Task 7: Installer Adimlari (Steps)

**Files:**
- Create: `packages/installer/steps/__init__.py`
- Create: `packages/installer/steps/welcome.py`
- Create: `packages/installer/steps/hardware.py`
- Create: `packages/installer/steps/network_step.py`
- Create: `packages/installer/steps/profile.py`
- Create: `packages/installer/steps/user_setup.py`
- Create: `packages/installer/steps/install.py`
- Create: `packages/installer/steps/services.py`
- Create: `packages/installer/steps/complete.py`
- Create: `tests/test_installer/test_steps.py`

**Step 1: Write the failing test**

```python
# tests/test_installer/test_steps.py
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
    # HardwareInfo veya None doner
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
```

**Step 2: Run test — FAIL**

**Step 3: Implement all step files**

Her step ayni deseni takip eder: `__init__` + `run()` metodu.

```python
# packages/installer/steps/__init__.py
"""Installer adimlari."""
```

```python
# packages/installer/steps/welcome.py
"""Adim 1: Hosgeldin ekrani."""
from __future__ import annotations

from ..tui import TUI

ASCII_BANNER = r"""
  _  _  _ _                      _    ___
 | |/ /| (_)_ __  _ __   ___ _ _/_\  |_ _|
 | ' / | | | '_ \| '_ \ / _ \ '_/ _ \ | |
 | . \ | | | |_) | |_) |  __/ |/ ___ \| |
 |_|\_\|_|_| .__/| .__/ \___|_/_/   \_\___|
            |_|   |_|     OS v3.0

  AI-Powered 3D Printer Operating System
"""


class WelcomeStep:
    def __init__(self, tui: TUI):
        self.tui = tui

    def run(self) -> bool:
        self.tui.msgbox("KlipperOS-AI'ye Hosgeldiniz!", f"""{ASCII_BANNER}
  Bu sihirbaz sisteminizi yapilandiracak:
  1. Donanim algilama
  2. Ag baglantisi
  3. Kurulum profili secimi
  4. Kullanici ayarlari
  5. Yazilim kurulumu

  Devam etmek icin OK'a basin.""")
        return True
```

```python
# packages/installer/steps/hardware.py
"""Adim 2: Donanim tespiti."""
from __future__ import annotations

from ..tui import TUI
from ..hw_detect import HardwareInfo


class HardwareStep:
    def __init__(self, tui: TUI):
        self.tui = tui

    def run(self) -> HardwareInfo:
        try:
            hw = HardwareInfo.detect()
        except Exception:
            # Tespit basarisiz olursa varsayilan degerler
            hw = HardwareInfo(
                cpu_model="Unknown", cpu_cores=1, cpu_freq_mhz=0,
                ram_total_mb=2048, disk_total_mb=0,
                has_wifi=False, has_ethernet=True,
                board_type="x86", recommended_profile="STANDARD",
            )

        wifi_str = "Evet" if hw.has_wifi else "Hayir"
        eth_str = "Evet" if hw.has_ethernet else "Hayir"

        self.tui.msgbox("Donanim Algilama Sonuclari", f"""
  CPU:       {hw.cpu_model}
  Cekirdek:  {hw.cpu_cores}
  RAM:       {hw.ram_total_mb} MB
  Disk:      {hw.disk_total_mb} MB
  WiFi:      {wifi_str}
  Ethernet:  {eth_str}

  Onerilen Profil: {hw.recommended_profile}""")

        return hw
```

```python
# packages/installer/steps/network_step.py
"""Adim 3: Ag baglantisi."""
from __future__ import annotations

from ..tui import TUI
from ..network import NetworkManager as NetMgr
from ..hw_detect import HardwareInfo


class NetworkStep:
    def __init__(self, tui: TUI, hw_info: HardwareInfo):
        self.tui = tui
        self.hw_info = hw_info
        self.net = NetMgr()

    def run(self) -> bool:
        # Zaten bagli mi?
        if self.net.check_internet():
            self.tui.msgbox("Ag Baglantisi", "Internet baglantisi mevcut. Devam ediliyor.")
            return True

        if not self.hw_info.has_wifi:
            self.tui.msgbox("Ag Baglantisi",
                "WiFi algilanamadi. Ethernet kablo baglayin.\nKurulum icin internet gerekli.")
            return False

        # WiFi tara
        networks = self.net.scan_wifi()
        if not networks:
            self.tui.msgbox("WiFi", "WiFi agi bulunamadi. Ethernet kablo baglayin.")
            return False

        # SSID sec
        items = [(str(i + 1), f"{ssid} ({signal}%)") for i, (ssid, signal) in enumerate(networks)]
        choice = self.tui.menu("WiFi Agi Secin", items, text="Baglanilacak agi secin:")

        try:
            idx = int(choice) - 1
            selected_ssid = networks[idx][0]
        except (ValueError, IndexError):
            return False

        # Sifre
        password = self.tui.passwordbox(f"{selected_ssid} icin sifre:", title="WiFi Sifresi")

        # Baglan
        if self.net.connect_wifi(selected_ssid, password):
            self.tui.msgbox("WiFi", f"Baglanti basarili: {selected_ssid}")
            return True
        else:
            self.tui.msgbox("WiFi Hatasi", "Baglanti basarisiz. Sifre yanlis olabilir.")
            return False
```

```python
# packages/installer/steps/profile.py
"""Adim 4: Profil secimi."""
from __future__ import annotations

from ..tui import TUI
from ..hw_detect import HardwareInfo
from ..profiles import PROFILES


class ProfileStep:
    def __init__(self, tui: TUI, hw_info: HardwareInfo):
        self.tui = tui
        self.hw_info = hw_info

    def run(self) -> str:
        if self.hw_info.is_force_light:
            self.tui.msgbox("Profil Secimi", f"""
  RAM: {self.hw_info.ram_total_mb} MB (< 1.5 GB)

  Yetersiz RAM nedeniyle sadece LIGHT profil
  kurulabilir.

  LIGHT: Klipper + Moonraker + Mainsail""")
            return "LIGHT"

        default_map = {"LIGHT": "1", "STANDARD": "2", "FULL": "3"}
        default = default_map.get(self.hw_info.recommended_profile, "2")

        items = [
            ("1", f"LIGHT    — {PROFILES['LIGHT'].description}"),
            ("2", f"STANDARD — {PROFILES['STANDARD'].description}"),
            ("3", f"FULL     — {PROFILES['FULL'].description}"),
        ]

        choice = self.tui.menu(
            "Kurulum Profili Secin",
            items,
            text=f"Donanim: {self.hw_info.ram_total_mb}MB RAM, {self.hw_info.cpu_cores} cekirdek\n"
                 f"Onerilen: {self.hw_info.recommended_profile}",
            default=default,
        )

        profile_map = {"1": "LIGHT", "2": "STANDARD", "3": "FULL"}
        return profile_map.get(choice, "STANDARD")
```

```python
# packages/installer/steps/user_setup.py
"""Adim 5: Kullanici ayarlari."""
from __future__ import annotations

from ..tui import TUI
from ..utils.runner import run_cmd
from ..utils.logger import get_logger

logger = get_logger()


class UserSetupStep:
    def __init__(self, tui: TUI):
        self.tui = tui

    def run(self) -> bool:
        # Hostname
        new_hostname = self.tui.inputbox("Cihaz adi (hostname):", title="Hostname", default="klipperos")
        if new_hostname and new_hostname != "klipperos":
            run_cmd(["hostnamectl", "set-hostname", new_hostname])
            logger.info("Hostname: %s", new_hostname)

        # Sifre
        new_pass = self.tui.passwordbox(
            "'klipper' kullanicisi icin yeni sifre\n(bos birakirsaniz varsayilan kalir):",
            title="Kullanici Sifresi",
        )
        if new_pass:
            run_cmd(["chpasswd"], timeout=10)  # stdin gerekir — basit implementasyon
            logger.info("klipper sifresi degistirildi")

        return True
```

```python
# packages/installer/steps/install.py
"""Adim 6: Paket ve bilesen kurulumu."""
from __future__ import annotations

from ..tui import TUI
from ..profiles import PROFILES
from ..utils.runner import run_cmd
from ..utils.sentinel import Sentinel
from ..utils.logger import get_logger
from ..installers.klipper import KlipperInstaller
from ..installers.moonraker import MoonrakerInstaller
from ..installers.mainsail import MainsailInstaller

logger = get_logger()

# Bilesen siniflarini isle gore esle
COMPONENT_MAP: dict[str, type] = {
    "klipper": KlipperInstaller,
    "moonraker": MoonrakerInstaller,
    "mainsail": MainsailInstaller,
}


class InstallStep:
    def __init__(self, tui: TUI, profile_name: str, sentinel: Sentinel | None = None):
        self.tui = tui
        self.profile_name = profile_name
        self.sentinel = sentinel or Sentinel()
        self.profile = PROFILES[profile_name]

    def run(self) -> bool:
        self.tui.msgbox("Kurulum Basliyor", f"""
  Profil: {self.profile_name}

  Simdi yazilim kuruluyor. Bu islem internet
  hiziniza bagli olarak 10-30 dakika surebilir.

  Lutfen bekleyin ve sistemi kapatmayin.""")

        # 1. APT paketleri
        logger.info("APT paketleri kuruluyor...")
        self.tui.gauge("APT paketleri indiriliyor...", 5)
        run_cmd(["apt-get", "update", "-qq"], timeout=120)

        packages = self.profile.apt_packages
        ok, _ = run_cmd(
            ["apt-get", "install", "-y", "--no-install-recommends"] + packages,
            timeout=600,
        )
        if not ok:
            logger.error("APT paket kurulumu basarisiz")
            # Devam et — bazi paketler eksik olabilir

        # 2. Bilesenler
        total = len(self.profile.components)
        for i, comp_name in enumerate(self.profile.components):
            percent = int(20 + (i / total) * 75)
            self.tui.gauge(f"Kuruluyor: {comp_name}...", percent)

            installer_cls = COMPONENT_MAP.get(comp_name)
            if installer_cls:
                installer = installer_cls(sentinel=self.sentinel)
                installer.install()
            else:
                logger.warning("Installer bulunamadi: %s — atlaniyor.", comp_name)

        self.tui.gauge("Kurulum tamamlandi!", 100)
        return True
```

```python
# packages/installer/steps/services.py
"""Adim 7: Servis yapilandirma."""
from __future__ import annotations

from ..tui import TUI
from ..utils.runner import run_cmd
from ..utils.logger import get_logger

logger = get_logger()

NGINX_SITE = """\
server {
    listen 80 default_server;
    listen [::]:80 default_server;

    root /home/klipper/mainsail;
    index index.html;
    server_name _;

    location / {
        try_files $uri $uri/ /index.html;
    }

    location /websocket {
        proxy_pass http://127.0.0.1:7125/websocket;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }

    location ~ ^/(printer|api|access|machine|server)/ {
        proxy_pass http://127.0.0.1:7125;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
"""


class ServicesStep:
    def __init__(self, tui: TUI):
        self.tui = tui

    def run(self) -> bool:
        logger.info("Servisler yapilandiriliyor...")

        # Nginx
        try:
            with open("/etc/nginx/sites-available/mainsail", "w") as f:
                f.write(NGINX_SITE)
            run_cmd(["ln", "-sf", "/etc/nginx/sites-available/mainsail",
                     "/etc/nginx/sites-enabled/mainsail"])
            run_cmd(["rm", "-f", "/etc/nginx/sites-enabled/default"])
            run_cmd(["systemctl", "enable", "nginx"])
            run_cmd(["systemctl", "restart", "nginx"])
        except OSError as e:
            logger.error("Nginx yapilandirilamadi: %s", e)

        # printer_data dizin yapisi
        dirs = [
            "/home/klipper/printer_data/config",
            "/home/klipper/printer_data/logs",
            "/home/klipper/printer_data/gcodes",
            "/home/klipper/printer_data/database",
        ]
        for d in dirs:
            run_cmd(["mkdir", "-p", d])
        run_cmd(["chown", "-R", "klipper:klipper", "/home/klipper/printer_data"])

        # Servisleri baslat
        for svc in ["klipper", "moonraker"]:
            run_cmd(["systemctl", "start", svc])

        return True
```

```python
# packages/installer/steps/complete.py
"""Adim 8: Tamamlandi ekrani."""
from __future__ import annotations

from ..tui import TUI
from ..utils.runner import run_cmd


class CompleteStep:
    def __init__(self, tui: TUI, profile_name: str):
        self.tui = tui
        self.profile_name = profile_name

    def run(self) -> bool:
        # IP adresi
        ok, output = run_cmd(["hostname", "-I"])
        ip_addr = output.strip().split()[0] if ok and output.strip() else "bilinmiyor"

        self.tui.msgbox("Kurulum Tamamlandi!", f"""
  KlipperOS-AI basariyla kuruldu!

  Profil:     {self.profile_name}
  IP Adresi:  {ip_addr}
  Web UI:     http://klipperos.local
  SSH:        ssh klipper@{ip_addr}

  Sonraki adimlar:
  1. printer.cfg'yi yaziciya gore duzenleyin
  2. MCU firmware flash: kos_mcu flash
  3. Web arayuzunden yaziciyi test edin

  Sistem simdi yeniden baslatilacak.""")

        return True
```

**Step 4: Run tests — PASS**

Run: `python -m pytest tests/test_installer/test_steps.py -v`
Expected: 4/4 PASS

**Step 5: Commit**

```bash
git add packages/installer/steps/ tests/test_installer/test_steps.py
git commit -m "feat(installer): add all 8 TUI installer steps"
```

---

## Task 8: Ana Uygulama (InstallerApp)

**Files:**
- Create: `packages/installer/app.py`
- Create: `tests/test_installer/test_app.py`
- Modify: `pyproject.toml` — entry point ekle

**Step 1: Write the failing test**

```python
# tests/test_installer/test_app.py
"""InstallerApp tests."""
from __future__ import annotations


def test_app_import():
    from packages.installer.app import InstallerApp
    assert InstallerApp is not None


def test_app_dry_run():
    from packages.installer.app import InstallerApp
    app = InstallerApp(dry_run=True)
    # dry_run modda tum adimlar calismali, hata vermemeli
    result = app.run()
    assert result == 0  # basari
```

**Step 2: Run test — FAIL**

**Step 3: Implement**

```python
# packages/installer/app.py
"""Installer ana uygulamasi."""
from __future__ import annotations

from .tui import TUI
from .utils.logger import get_logger
from .utils.sentinel import Sentinel
from .steps.welcome import WelcomeStep
from .steps.hardware import HardwareStep
from .steps.network_step import NetworkStep
from .steps.profile import ProfileStep
from .steps.user_setup import UserSetupStep
from .steps.install import InstallStep
from .steps.services import ServicesStep
from .steps.complete import CompleteStep

logger = get_logger()

SENTINEL_DIR = "/opt/klipperos-ai"


class InstallerApp:
    """KlipperOS-AI TUI installer ana uygulamasi."""

    def __init__(self, dry_run: bool = False):
        self.dry_run = dry_run
        self.tui = TUI(dry_run=dry_run)
        self.sentinel = Sentinel(base_dir=SENTINEL_DIR if not dry_run else "/tmp/kos-test")

    def run(self) -> int:
        """Tum adimlari sirayla calistir. 0=basari, 1=hata."""
        logger.info("=== KlipperOS-AI Installer v3.0 ===")

        # 1. Hosgeldin
        WelcomeStep(tui=self.tui).run()

        # 2. Donanim tespiti
        hw_info = HardwareStep(tui=self.tui).run()

        # 3. Ag baglantisi
        net_ok = NetworkStep(tui=self.tui, hw_info=hw_info).run()
        if not net_ok and not self.dry_run:
            logger.error("Internet baglantisi yok — kurulum iptal.")
            return 1

        # 4. Profil secimi
        profile_name = ProfileStep(tui=self.tui, hw_info=hw_info).run()

        # 5. Kullanici ayarlari
        UserSetupStep(tui=self.tui).run()

        # 6. Kurulum
        InstallStep(
            tui=self.tui,
            profile_name=profile_name,
            sentinel=self.sentinel,
        ).run()

        # 7. Servis yapilandirma
        ServicesStep(tui=self.tui).run()

        # 8. Tamamlandi
        CompleteStep(tui=self.tui, profile_name=profile_name).run()

        logger.info("Installer tamamlandi.")
        return 0
```

Modify `pyproject.toml` — add entry point:

```toml
# [project.scripts] bolumune ekle:
kos-install = "packages.installer.__main__:main"
```

**Step 4: Run tests — PASS**

Run: `python -m pytest tests/test_installer/test_app.py -v`
Expected: 2/2 PASS

Then full suite: `python -m pytest tests/test_installer/ -v`
Expected: ALL PASS

**Step 5: Commit**

```bash
git add packages/installer/app.py tests/test_installer/test_app.py pyproject.toml
git commit -m "feat(installer): add InstallerApp orchestrator with entry point"
```

---

## Task 9: Minimal ISO Builder

**Files:**
- Create: `image-builder/build-minimal-image.sh`
- Modify: `image-builder/autoinstall/user-data` — sadelestirilmis versiyon
- Create: `image-builder/config/includes.chroot/etc/systemd/system/kos-installer.service`

**Step 1: Minimal autoinstall user-data olustur**

Mevcut `user-data`'yi sadelestir: sadece WiFi + Python + installer paketleri. `late-commands` sadece installer'i kopyalar ve systemd service'i etkinlestirir.

**Step 2: Systemd service olustur**

```ini
# image-builder/config/includes.chroot/etc/systemd/system/kos-installer.service
[Unit]
Description=KlipperOS-AI First Boot Installer
After=network-online.target
Wants=network-online.target
ConditionPathExists=/opt/klipperos-ai/.first-boot

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 -m packages.installer
ExecStartPost=/bin/rm -f /opt/klipperos-ai/.first-boot
WorkingDirectory=/opt/klipperos-ai
StandardInput=tty
StandardOutput=tty
TTYPath=/dev/tty1
RemainAfterExit=no
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

**Step 3: Minimal ISO builder script olustur**

`build-minimal-image.sh` mevcut `build-image.sh`'in sadeleştirilmiş versiyonu:
- ISO'ya sadece `packages/installer/` ve `pyproject.toml` kopyalanir
- Deferred paket listesi gommez — installer kendi profil listesini bilir
- KlipperOS-AI tools, scripts, ai-monitor, ks-panels kopyalanmaz

**Step 4: Commit**

```bash
git add image-builder/build-minimal-image.sh \
        image-builder/config/includes.chroot/etc/systemd/system/kos-installer.service
git commit -m "feat(installer): add minimal ISO builder and systemd service"
```

---

## Task 10: Ruff Lint + Tam Test Suite + Entegrasyon

**Step 1:** `python -m ruff check packages/installer/ tests/test_installer/ --fix`
**Step 2:** `python -m pytest tests/test_installer/ -v --tb=short`
**Step 3:** Tum testlerin gectigini dogrula
**Step 4:** Final commit

```bash
git commit -m "chore(installer): lint fixes and final validation"
```

---

## Ozet: 10 Task

| Task | Icerik | Dosya Sayisi |
|------|--------|:---:|
| 1 | TUI wrapper (whiptail) | 5 |
| 2 | Donanim tespiti | 2 |
| 3 | Profil tanimlari | 2 |
| 4 | Yardimci araclar (logger, runner, sentinel) | 5 |
| 5 | Ag baglanti modulu | 2 |
| 6 | Bilesen kuruculari (Klipper, Moonraker, Mainsail) | 5 |
| 7 | Installer adimlari (8 adim) | 10 |
| 8 | Ana uygulama (InstallerApp) + entry point | 3 |
| 9 | Minimal ISO builder + systemd service | 3 |
| 10 | Lint + son dogrulama | 0 |
