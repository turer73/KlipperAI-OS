"""Utility module tests."""
from __future__ import annotations

import tempfile


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
