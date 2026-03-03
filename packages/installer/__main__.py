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
