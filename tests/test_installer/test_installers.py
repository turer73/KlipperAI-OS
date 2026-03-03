"""Component installer tests."""
from __future__ import annotations

import tempfile


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
