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
