"""Whiptail TUI wrapper sinifi."""
from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass


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
    """Whiptail tabanli terminal arayuzu wrapper."""

    dry_run: bool = False
    width: int = 70
    height: int = 20

    def _escape(self, text: str) -> str:
        """Whiptail icin ozel karakterleri escape et."""
        return text.replace('"', "").replace("'", "")

    def _run(self, args: list[str], capture: bool = False) -> str:
        """Whiptail komutunu calistir."""
        if self.dry_run:
            return ""

        env = {**dict(os.environ), "TERM": "linux", "NEWT_COLORS": NEWT_COLORS}
        cmd = ["whiptail", "--backtitle", BACKTITLE] + args

        result = subprocess.run(
            cmd,
            capture_output=capture,
            text=True,
            env=env,
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

    def infobox(self, title: str, text: str) -> None:
        """Butonsuz bilgi mesaji — hemen doner, arka plan islemi icin."""
        if self.dry_run:
            return
        self._run([
            "--title", title,
            "--infobox", self._escape(text),
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
        args += [
            "--menu", self._escape(text),
            str(self.height), str(self.width), str(len(items)),
        ]
        for tag, desc in items:
            args += [tag, desc]
        result = self._run(args, capture=True)
        return result or (items[0][0] if items else "")

    def yesno(self, text: str, title: str = "") -> bool:
        """Evet/Hayir sorusu."""
        if self.dry_run:
            return True

        env = {**dict(os.environ), "TERM": "linux", "NEWT_COLORS": NEWT_COLORS}
        result = subprocess.run(
            [
                "whiptail", "--backtitle", BACKTITLE, "--title", title,
                "--yesno", self._escape(text), str(self.height), str(self.width),
            ],
            env=env,
        )
        return result.returncode == 0

    def inputbox(self, text: str, title: str = "", default: str = "") -> str:
        """Metin girisi."""
        if self.dry_run:
            return default

        args = [
            "--title", title, "--inputbox", self._escape(text),
            str(self.height), str(self.width), default,
        ]
        return self._run(args, capture=True) or default

    def passwordbox(self, text: str, title: str = "") -> str:
        """Sifre girisi."""
        if self.dry_run:
            return ""

        args = [
            "--title", title, "--passwordbox", self._escape(text),
            str(self.height), str(self.width),
        ]
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
