"""Tests for NotificationManager."""
import sys
import os
import json
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ai-monitor'))

import pytest
from unittest.mock import patch, MagicMock
from notification_manager import (
    NotificationManager, Notification, Severity,
    TelegramProvider, DiscordProvider, NotificationProvider,
)


class TestNotification:
    """Notification dataclass testleri."""

    def test_default_severity(self):
        n = Notification(title="Test", message="Merhaba")
        assert n.severity == Severity.INFO
        assert n.timestamp > 0

    def test_emoji_mapping(self):
        assert Notification(title="", message="", severity=Severity.CRITICAL).emoji == "🚨"
        assert Notification(title="", message="", severity=Severity.WARNING).emoji == "⚠️"
        assert Notification(title="", message="", severity=Severity.INFO).emoji == "ℹ️"

    def test_format_text(self):
        n = Notification(
            title="FlowGuard Uyari",
            message="Sicaklik dusuyor",
            severity=Severity.WARNING,
            category="flowguard",
        )
        text = n.format_text()
        assert "FlowGuard Uyari" in text
        assert "Sicaklik dusuyor" in text
        assert "flowguard" in text


class TestSeverity:
    """Severity karsilastirma testleri."""

    def test_ordering(self):
        assert Severity.INFO < Severity.NOTICE
        assert Severity.NOTICE < Severity.WARNING
        assert Severity.WARNING < Severity.CRITICAL

    def test_numeric_values(self):
        assert int(Severity.INFO) == 0
        assert int(Severity.CRITICAL) == 3


class FakeProvider(NotificationProvider):
    """Test icin sahte provider."""

    def __init__(self, name: str = "fake", succeed: bool = True,
                 min_sev: Severity = Severity.INFO):
        self._name = name
        self._succeed = succeed
        self._min_sev = min_sev
        self.sent: list[Notification] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def min_severity(self) -> Severity:
        return self._min_sev

    def send(self, notification: Notification) -> bool:
        self.sent.append(notification)
        return self._succeed


class TestNotificationManager:
    """NotificationManager testleri."""

    def test_add_provider(self):
        mgr = NotificationManager()
        mgr.add_provider(FakeProvider("test"))
        assert "test" in mgr.provider_names

    def test_remove_provider(self):
        mgr = NotificationManager()
        mgr.add_provider(FakeProvider("test"))
        assert mgr.remove_provider("test") is True
        assert "test" not in mgr.provider_names

    def test_notify_sends_to_all(self):
        mgr = NotificationManager()
        p1 = FakeProvider("p1")
        p2 = FakeProvider("p2")
        mgr.add_provider(p1)
        mgr.add_provider(p2)

        results = mgr.notify(Notification(
            title="Test", message="Hello",
        ))
        assert results == {"p1": True, "p2": True}
        assert len(p1.sent) == 1
        assert len(p2.sent) == 1

    def test_severity_filter(self):
        mgr = NotificationManager()
        p_warn = FakeProvider("warn_only", min_sev=Severity.WARNING)
        mgr.add_provider(p_warn)

        # INFO mesaji gonderilmemeli
        results = mgr.notify(Notification(
            title="Info", message="", severity=Severity.INFO,
        ))
        assert "warn_only" not in results
        assert len(p_warn.sent) == 0

        # WARNING mesaji gonderilmeli
        results = mgr.notify(Notification(
            title="Warn", message="", severity=Severity.WARNING,
            category="different",  # Cooldown'dan kacinmak icin farkli kategori
        ))
        assert results == {"warn_only": True}

    def test_cooldown(self):
        mgr = NotificationManager(cooldown_seconds=10)
        p = FakeProvider("test")
        mgr.add_provider(p)

        # Ilk bildirim gecmeli
        mgr.notify(Notification(title="1", message="", category="cat1"))
        assert len(p.sent) == 1

        # Ikinci bildirim cooldown icinde — atlanmali
        results = mgr.notify(Notification(title="2", message="", category="cat1"))
        assert results == {}
        assert len(p.sent) == 1

    def test_different_categories_no_cooldown(self):
        mgr = NotificationManager(cooldown_seconds=10)
        p = FakeProvider("test")
        mgr.add_provider(p)

        mgr.notify(Notification(title="1", message="", category="cat1"))
        mgr.notify(Notification(title="2", message="", category="cat2"))
        assert len(p.sent) == 2

    def test_empty_category_no_cooldown(self):
        mgr = NotificationManager(cooldown_seconds=10)
        p = FakeProvider("test")
        mgr.add_provider(p)

        mgr.notify(Notification(title="1", message=""))
        mgr.notify(Notification(title="2", message=""))
        assert len(p.sent) == 2

    def test_notify_simple(self):
        mgr = NotificationManager()
        p = FakeProvider("test")
        mgr.add_provider(p)

        results = mgr.notify_simple("Baslik", "Mesaj", Severity.WARNING, "test")
        assert results == {"test": True}
        assert p.sent[0].title == "Baslik"

    def test_history(self):
        mgr = NotificationManager()
        p = FakeProvider("test")
        mgr.add_provider(p)

        mgr.notify(Notification(title="H1", message="", category="c1"))
        mgr.notify(Notification(title="H2", message="", category="c2"))

        hist = mgr.history
        assert len(hist) == 2
        assert hist[0]["title"] == "H1"

    def test_failed_send_in_results(self):
        mgr = NotificationManager()
        p = FakeProvider("fail", succeed=False)
        mgr.add_provider(p)

        results = mgr.notify(Notification(title="X", message=""))
        assert results == {"fail": False}


class TestConfigIO:
    """Yapilandirma dosyasi testleri."""

    def test_save_and_load(self):
        with tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        ) as f:
            path = f.name

        mgr = NotificationManager(config_path=path)
        config = {
            "telegram": {
                "enabled": True,
                "bot_token": "123:ABC",
                "chat_id": "-100123",
                "min_severity": "warning",
            },
            "discord": {"enabled": False},
            "cooldown_seconds": 30,
        }
        assert mgr.save_config(config) is True

        # Yeni manager yukle
        mgr2 = NotificationManager(config_path=path)
        mgr2.load_config()
        assert "telegram" in mgr2.provider_names
        assert mgr2.cooldown_seconds == 30.0
        os.unlink(path)

    def test_load_nonexistent(self):
        mgr = NotificationManager(config_path="/tmp/nonexistent-notif.json")
        assert mgr.load_config() is False


class TestTelegramProvider:
    """TelegramProvider unit testleri."""

    def test_name(self):
        p = TelegramProvider("token", "chatid")
        assert p.name == "telegram"

    def test_unconfigured_returns_false(self):
        p = TelegramProvider("", "")
        n = Notification(title="Test", message="")
        assert p.send(n) is False

    def test_html_escape(self):
        assert TelegramProvider._escape_html("A<B>C&D") == "A&lt;B&gt;C&amp;D"


class TestDiscordProvider:
    """DiscordProvider unit testleri."""

    def test_name(self):
        p = DiscordProvider("https://hooks.example.com")
        assert p.name == "discord"

    def test_unconfigured_returns_false(self):
        p = DiscordProvider("")
        n = Notification(title="Test", message="")
        assert p.send(n) is False

    def test_color_mapping(self):
        assert DiscordProvider.COLORS[Severity.CRITICAL] == 0xE74C3C
        assert DiscordProvider.COLORS[Severity.INFO] == 0x3498DB
