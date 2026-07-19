"""PyInstaller entry point for the portable Windows distribution."""

import ctypes
import sys

from cohortlint.cli import app


def _enable_utf8_console() -> None:
    """Keep Turkish and German output intact in the Windows console."""
    if sys.platform != "win32":
        return
    ctypes.windll.kernel32.SetConsoleCP(65001)
    ctypes.windll.kernel32.SetConsoleOutputCP(65001)
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")


if __name__ == "__main__":
    _enable_utf8_console()
    app()
