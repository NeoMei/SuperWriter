"""Deterministic UTF-8 standard streams for SuperWriter command-line tools."""

from __future__ import annotations

import sys


def configure_utf8_stdio() -> None:
    """Use UTF-8 for redirected output even when the Windows locale is narrower."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="strict")
