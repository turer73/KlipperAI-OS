"""
KlipperOS-AI — Smart Notification Manager
==========================================
Telegram Bot API + Discord Webhook ile akilli bildirim.

Provider pattern: yeni kanal eklemek icin NotificationProvider
alt sinifi yeterli.

Ozellikler:
    - Coklu kanal: Telegram, Discord (genisletilebilir)
    - Rate limiting: ayni mesajlar tekrar gonderilmez (cooldown)
    - Severity filtreleme: kanal bazli minimum severity
    - Thread-safe: Lock ile korunmus state
    - Retry: basarisiz gonderimde 1 tekrar

Kullanim:
    mgr = NotificationManager()
    mgr.add_provider(TelegramProvider(bot_token="...", chat_id="..."))
    mgr.add_provider(DiscordProvider(webhook_url="..."))
    mgr.notify(Notification(
        title="FlowGuard Uyari",
        message="Extruder sicakligi dusuyor",
        severity=Severity.WARNING,
        category="flowguard",
    ))

Yapilandirma dosyasi: /var/lib/klipperos-ai/notifications.json
"""

from __future__ import annotations

import json
import logging
import threading
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from pathlib import Path
from typing import Optional
from urllib.request import urlopen, Request
from urllib.error import URLError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Data Models
# ---------------------------------------------------------------------------

class Severity(IntEnum):
    """Bildirim onemi — sayisal olarak karsilastirilabilir."""
    INFO = 0
    NOTICE = 1
    WARNING = 2
    CRITICAL = 3


@dataclass
class Notification:
    """Tek bir bildirim mesaji."""
    title: str
    message: str
    severity: Severity = Severity.INFO
    category: str = ""           # flowguard, calibration, print, system
    timestamp: float = 0.0      # 0 ise otomatik atanir
    metadata: dict = field(default_factory=dict)

    def __post_init__(self):
        if self.timestamp == 0.0:
            self.timestamp = time.time()

    @property
    def emoji(self) -> str:
        """Severity'ye gore emoji."""
        return {
            Severity.INFO: "ℹ️",
            Severity.NOTICE: "📋",
            Severity.WARNING: "⚠️",
            Severity.CRITICAL: "🚨",
        }.get(self.severity, "📌")

    def format_text(self) -> str:
        """Duz metin formatla (Telegram/Discord icin)."""
        parts = [f"{self.emoji} {self.title}"]
        if self.message:
            parts.append(self.message)
        if self.category:
            parts.append(f"Kategori: {self.category}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Provider Interface
# ---------------------------------------------------------------------------

class NotificationProvider(ABC):
    """Bildirim kanali soyut sinifi."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Kanal adi (log icin)."""

    @abstractmethod
    def send(self, notification: Notification) -> bool:
        """Bildirim gonder. Basarili ise True."""

    @property
    def min_severity(self) -> Severity:
        """Bu kanalda gonderilebilecek minimum severity."""
        return Severity.INFO


# ---------------------------------------------------------------------------
# Telegram Provider
# ---------------------------------------------------------------------------

class TelegramProvider(NotificationProvider):
    """Telegram Bot API ile bildirim gonderici.

    Args:
        bot_token: Telegram Bot API token'i (@BotFather'dan)
        chat_id: Hedef chat/group ID (negatif sayi = grup)
        min_severity: Minimum bildirim onemi
        parse_mode: Mesaj formati (HTML, Markdown, None)
    """

    API_BASE = "https://api.telegram.org"

    def __init__(self, bot_token: str, chat_id: str,
                 min_severity: Severity = Severity.INFO,
                 parse_mode: str = "HTML"):
        self.bot_token = bot_token
        self.chat_id = chat_id
        self._min_severity = min_severity
        self.parse_mode = parse_mode

    @property
    def name(self) -> str:
        return "telegram"

    @property
    def min_severity(self) -> Severity:
        return self._min_severity

    def send(self, notification: Notification) -> bool:
        """Telegram mesaji gonder."""
        if not self.bot_token or not self.chat_id:
            logger.warning("Telegram yapilandirilmamis")
            return False

        text = self._format_html(notification)
        url = f"{self.API_BASE}/bot{self.bot_token}/sendMessage"
        payload = {
            "chat_id": self.chat_id,
            "text": text,
            "parse_mode": self.parse_mode,
            "disable_notification": notification.severity < Severity.WARNING,
        }
        return self._post_json(url, payload)

    def _format_html(self, n: Notification) -> str:
        """Telegram HTML format."""
        lines = [
            f"{n.emoji} <b>{self._escape_html(n.title)}</b>",
        ]
        if n.message:
            lines.append(self._escape_html(n.message))
        if n.category:
            lines.append(f"<i>#{n.category}</i>")
        return "\n".join(lines)

    @staticmethod
    def _escape_html(text: str) -> str:
        """HTML ozel karakterleri escape et."""
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;"))

    @staticmethod
    def _post_json(url: str, data: dict) -> bool:
        """JSON POST istegi gonder."""
        try:
            payload = json.dumps(data).encode()
            req = Request(url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=10) as resp:
                result = json.loads(resp.read().decode())
                return result.get("ok", False)
        except (URLError, OSError, json.JSONDecodeError) as exc:
            logger.error("Telegram gonderim hatasi: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Discord Provider
# ---------------------------------------------------------------------------

class DiscordProvider(NotificationProvider):
    """Discord Webhook ile bildirim gonderici.

    Args:
        webhook_url: Discord webhook URL'i
        username: Bot kullanici adi (Discord'da gorunecek)
        min_severity: Minimum bildirim onemi
    """

    # Discord embed renkleri (severity bazli)
    COLORS = {
        Severity.INFO: 0x3498DB,     # Mavi
        Severity.NOTICE: 0x2ECC71,   # Yesil
        Severity.WARNING: 0xF39C12,  # Turuncu
        Severity.CRITICAL: 0xE74C3C, # Kirmizi
    }

    def __init__(self, webhook_url: str, username: str = "KlipperOS-AI",
                 min_severity: Severity = Severity.INFO):
        self.webhook_url = webhook_url
        self.username = username
        self._min_severity = min_severity

    @property
    def name(self) -> str:
        return "discord"

    @property
    def min_severity(self) -> Severity:
        return self._min_severity

    def send(self, notification: Notification) -> bool:
        """Discord embed mesaji gonder."""
        if not self.webhook_url:
            logger.warning("Discord yapilandirilmamis")
            return False

        color = self.COLORS.get(notification.severity, 0x95A5A6)
        embed = {
            "title": f"{notification.emoji} {notification.title}",
            "description": notification.message,
            "color": color,
            "timestamp": time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime(notification.timestamp)
            ),
        }
        if notification.category:
            embed["footer"] = {"text": f"#{notification.category}"}

        payload = {
            "username": self.username,
            "embeds": [embed],
        }
        return self._post_json(self.webhook_url, payload)

    @staticmethod
    def _post_json(url: str, data: dict) -> bool:
        """JSON POST istegi gonder."""
        try:
            payload = json.dumps(data).encode()
            req = Request(url, data=payload, method="POST")
            req.add_header("Content-Type", "application/json")
            with urlopen(req, timeout=10) as resp:
                # Discord basarili gonderimde 204 No Content doner
                return resp.status in (200, 204)
        except (URLError, OSError, json.JSONDecodeError) as exc:
            logger.error("Discord gonderim hatasi: %s", exc)
            return False


# ---------------------------------------------------------------------------
# Notification Manager
# ---------------------------------------------------------------------------

class NotificationManager:
    """Merkezi bildirim yoneticisi.

    Args:
        cooldown_seconds: Ayni kategori icin tekrar gonderim bekleme suresi.
        config_path: Yapilandirma dosyasi yolu (JSON).
    """

    DEFAULT_CONFIG_PATH = "/var/lib/klipperos-ai/notifications.json"

    def __init__(self, cooldown_seconds: float = 60.0,
                 config_path: str | Path | None = None):
        self._providers: list[NotificationProvider] = []
        self._lock = threading.Lock()
        self._cooldowns: dict[str, float] = {}  # category -> last_sent
        self.cooldown_seconds = cooldown_seconds
        self._config_path = Path(config_path or self.DEFAULT_CONFIG_PATH)
        self._history: list[dict] = []
        self._max_history = 100

    def add_provider(self, provider: NotificationProvider) -> None:
        """Bildirim kanali ekle."""
        with self._lock:
            self._providers.append(provider)
            logger.info("Bildirim kanali eklendi: %s", provider.name)

    def remove_provider(self, name: str) -> bool:
        """Bildirim kanalini kaldir."""
        with self._lock:
            before = len(self._providers)
            self._providers = [p for p in self._providers if p.name != name]
            return len(self._providers) < before

    @property
    def provider_names(self) -> list[str]:
        """Aktif kanal isimleri."""
        with self._lock:
            return [p.name for p in self._providers]

    def notify(self, notification: Notification) -> dict[str, bool]:
        """Tum uygun kanallara bildirim gonder.

        Returns:
            {kanal_adi: basarili_mi} dict'i
        """
        # Cooldown kontrolu
        if self._is_cooldown(notification.category):
            logger.debug("Cooldown aktif: %s", notification.category)
            return {}

        results: dict[str, bool] = {}
        with self._lock:
            providers = list(self._providers)

        for provider in providers:
            if notification.severity < provider.min_severity:
                continue

            ok = self._send_with_retry(provider, notification)
            results[provider.name] = ok

        # Cooldown guncelle
        if results:
            self._set_cooldown(notification.category)

        # History kaydet
        self._add_history(notification, results)

        return results

    def notify_simple(self, title: str, message: str,
                      severity: Severity = Severity.INFO,
                      category: str = "") -> dict[str, bool]:
        """Basit bildirim gonder — Notification nesnesi olusturmadan."""
        return self.notify(Notification(
            title=title, message=message,
            severity=severity, category=category,
        ))

    @property
    def history(self) -> list[dict]:
        """Son bildirim gecmisi."""
        with self._lock:
            return list(self._history)

    def load_config(self) -> bool:
        """Yapilandirma dosyasindan provider'lari yukle.

        JSON formati:
        {
            "telegram": {
                "enabled": true,
                "bot_token": "123:ABC",
                "chat_id": "-1001234",
                "min_severity": "warning"
            },
            "discord": {
                "enabled": true,
                "webhook_url": "https://discord.com/api/webhooks/...",
                "min_severity": "info"
            },
            "cooldown_seconds": 60
        }
        """
        if not self._config_path.exists():
            logger.info("Bildirim ayar dosyasi yok: %s", self._config_path)
            return False

        try:
            config = json.loads(self._config_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            logger.error("Bildirim ayar dosyasi okunamadi: %s", exc)
            return False

        if "cooldown_seconds" in config:
            self.cooldown_seconds = float(config["cooldown_seconds"])

        # Telegram
        tg = config.get("telegram", {})
        if tg.get("enabled") and tg.get("bot_token") and tg.get("chat_id"):
            sev = self._parse_severity(tg.get("min_severity", "info"))
            self.add_provider(TelegramProvider(
                bot_token=tg["bot_token"],
                chat_id=str(tg["chat_id"]),
                min_severity=sev,
            ))

        # Discord
        dc = config.get("discord", {})
        if dc.get("enabled") and dc.get("webhook_url"):
            sev = self._parse_severity(dc.get("min_severity", "info"))
            self.add_provider(DiscordProvider(
                webhook_url=dc["webhook_url"],
                min_severity=sev,
            ))

        logger.info("Bildirim ayarlari yuklendi: %s", self.provider_names)
        return True

    def save_config(self, config: dict) -> bool:
        """Yapilandirma dosyasina yaz (atomik)."""
        try:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._config_path.with_suffix(".tmp")
            with open(tmp, "w") as f:
                json.dump(config, f, indent=2)
            tmp.replace(self._config_path)
            return True
        except OSError as exc:
            logger.error("Bildirim ayar dosyasi yazilamadi: %s", exc)
            return False

    # -- Private --

    def _send_with_retry(self, provider: NotificationProvider,
                         notification: Notification,
                         max_retries: int = 2) -> bool:
        """Retry ile gonder."""
        for attempt in range(max_retries):
            try:
                if provider.send(notification):
                    return True
            except Exception as exc:
                logger.error("%s gonderim hatasi (deneme %d): %s",
                             provider.name, attempt + 1, exc)
            if attempt < max_retries - 1:
                time.sleep(1)
        return False

    def _is_cooldown(self, category: str) -> bool:
        """Kategori icin cooldown aktif mi?"""
        if not category:
            return False
        with self._lock:
            last = self._cooldowns.get(category, 0)
            return (time.time() - last) < self.cooldown_seconds

    def _set_cooldown(self, category: str) -> None:
        """Cooldown zamanlayicisini guncelle."""
        if category:
            with self._lock:
                self._cooldowns[category] = time.time()

    def _add_history(self, notification: Notification,
                     results: dict[str, bool]) -> None:
        """Bildirim gecmisine ekle."""
        entry = {
            "title": notification.title,
            "severity": notification.severity.name,
            "category": notification.category,
            "timestamp": notification.timestamp,
            "results": results,
        }
        with self._lock:
            self._history.append(entry)
            if len(self._history) > self._max_history:
                self._history = self._history[-self._max_history:]

    @staticmethod
    def _parse_severity(text: str) -> Severity:
        """Metin -> Severity donusumu."""
        mapping = {
            "info": Severity.INFO,
            "notice": Severity.NOTICE,
            "warning": Severity.WARNING,
            "critical": Severity.CRITICAL,
        }
        return mapping.get(text.lower(), Severity.INFO)
