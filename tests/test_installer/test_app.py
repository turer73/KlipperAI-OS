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
