# ui_status.py
# Minimal one-line status bar with optional ANSI colors.
# Works in cmd/PowerShell/Windows Terminal without clearing the screen.

from typing import Optional
import os
import re
import sys

# ANSI sequences
RESET = "\033[0m"
BOLD = "\033[1m"
BG_RED = "\033[41m"
BG_GREEN = "\033[42m"

# Public export of the two background colors for convenience
__all__ = ["status_show", "status_clear", "BG_RED", "BG_GREEN"]

_status_active = False
_status_width = 0

# Allow turning colors off via env (useful for CI or legacy consoles)
_DISABLE_COLOR = os.getenv("NO_ANSI") == "1"

def _strip_ansi(s: str) -> str:
    """Strip ANSI sequences to compute printable width."""
    return re.sub(r"\x1b\[[0-9;]*m", "", s)

def _pad(s: str, width: int) -> str:
    """Right-pad with spaces so we fully overwrite older content."""
    raw_len = len(_strip_ansi(s))
    if raw_len < width:
        return s + (" " * (width - raw_len))
    return s

def _supports_color() -> bool:
    """Best-effort check; allow force-disable via NO_ANSI=1."""
    if _DISABLE_COLOR:
        return False
    # On Windows 10/11 modern terminals support ANSI; fall back to plain if redirected
    return sys.stdout.isatty()

def status_show(text: str, bg_color: str) -> None:
    """
    Render a one-line status in place using CR.
    Example:
        status_show("AUTO-PTT READY — press PTT", BG_GREEN)
        status_show("TX ACTIVE — keep carrier and tune", BG_RED)
    """
    global _status_active, _status_width
    if _supports_color():
        msg = f"{bg_color}{BOLD} {text} {RESET}"
    else:
        # Plain fallback without ANSI (keeps the UX semantics)
        msg = f" {text} "
    _status_width = max(_status_width, len(_strip_ansi(msg)))
    print("\r" + _pad(msg, _status_width), end="", flush=True)
    _status_active = True

def status_clear() -> None:
    """Erase the status line in-place without clearing the rest of the screen."""
    global _status_active, _status_width
    if _status_active:
        print("\r" + (" " * _status_width) + "\r", end="", flush=True)
        _status_active = False
