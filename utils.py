# utils.py
# Small user-interface helpers and formatting utilities.

from __future__ import annotations
import platform

def pretty_duration(seconds: float, style: str = "auto") -> str:
    """Format duration as '1h 02m 05s' / '22m 03s' / '3.40 s' / '850 ms' or 'HH:MM:SS'."""
    if seconds < 0:
        seconds = 0.0

    if style == "clock":
        total = int(round(seconds))
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    if seconds < 0.001:
        return "0 ms"
    if seconds < 1.0:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60.0:
        return f"{seconds:.2f} s"

    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60

    if h > 0:
        return f"{h}h {m}m {s:02d}s"
    return f"{m}m {s:02d}s"


def beep(enabled: bool = True) -> None:
    """Short audible cue before each tuning step (optional)."""
    if not enabled:
        return
    if platform.system() == "Windows":
        try:
            import winsound
            winsound.Beep(1000, 300)
        except Exception:
            print("\a", end="")
    else:
        print("\a", end="")


def countdown(seconds: int, message: str = "    →  Tuning next frequency") -> None:
    """Simple countdown helper if we ever want a short delay between steps."""
    import sys, time
    for i in range(seconds, 0, -1):
        sys.stdout.write(f"{message} in {i} second(s)...\r")
        sys.stdout.flush()
        time.sleep(1)
    sys.stdout.write(" " * 80 + "\r")
    sys.stdout.flush()
    print()
