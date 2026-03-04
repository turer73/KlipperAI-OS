"""Whiptail TUI wrapper sinifi."""
from __future__ import annotations

import os
import shutil
import subprocess
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


def _detect_terminal_size() -> tuple[int, int]:
    """Terminal boyutunu oto-algila. (cols, rows) dondur."""
    cols, rows = shutil.get_terminal_size((80, 24))
    return cols, rows


@dataclass
class TUI:
    """Whiptail tabanli terminal arayuzu wrapper.

    Terminal boyutu otomatik algilanir. Kucuk ekranlar (netbook vb.)
    icin whiptail diyaloglari ekrana sigacak sekilde ayarlanir.
    """

    dry_run: bool = False
    width: int = field(default=0)
    height: int = field(default=0)

    def __post_init__(self):
        """Terminal boyutuna gore width/height ayarla."""
        if not self.dry_run and (self.width == 0 or self.height == 0):
            cols, rows = _detect_terminal_size()
            if self.width == 0:
                self.width = min(cols - 4, 76)
            if self.height == 0:
                self.height = min(rows - 2, 24)

    def _escape(self, text: str) -> str:
        """Whiptail icin ozel karakterleri escape et."""
        return text.replace('"', "").replace("'", "")

    def _run(self, args: list[str], capture: bool = False) -> str:
        """Whiptail komutunu calistir.

        capture=True olunca SADECE stderr pipe'lanir (secim degeri icin).
        stdout terminale gider ki whiptail arayuzu gorunsun.

        NOT: capture_output=True KULLANMA — stdout'u pipe'lar ve
        systemd servisi (controlling terminal yok) ortaminda whiptail
        arayuzu goruntulenemez.
        """
        if self.dry_run:
            return ""

        env = {**dict(os.environ), "TERM": "linux", "NEWT_COLORS": NEWT_COLORS}
        cmd = ["whiptail", "--backtitle", BACKTITLE] + args

        if capture:
            # Sadece stderr yakala (secim degeri) — stdout terminalde kalsin (UI)
            result = subprocess.run(
                cmd,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            return result.stderr.strip()

        # infobox/msgbox — hicbir sey yakalama
        subprocess.run(cmd, text=True, env=env)
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

        # Scroll alani: dialog yuksekligi - cerceve/baslik/buton (7 satir)
        menu_height = min(len(items), self.height - 7)
        menu_height = max(menu_height, 3)  # en az 3 satir gorsun

        args = ["--title", title]
        if default:
            args += ["--default-item", default]
        args += [
            "--menu", self._escape(text),
            str(self.height), str(self.width), str(menu_height),
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
