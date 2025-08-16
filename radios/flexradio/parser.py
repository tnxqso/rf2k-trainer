# radios/flexradio/parser.py
import re
from typing import Callable, Optional


class FlexParser:
    """
    Minimal line parser for SmartSDR 'H' / 'S' messages.

    It detects and dispatches:
      - Identity: 'H...' or any line containing 'radio nickname=... callsign=...'
      - Slice updates: '...|slice <id> ... RF_frequency=... mode=... tx=...'
      - Interlock/PTT: '...|interlock state=READY|TRANSMITTING|...'
      - Transmit power: '...|transmit rfpower=.. tunepower=..'

    Design choice:
      Instead of pre-filtering with brittle substring checks in feed(),
      we call all parsers on every line. Each parser quickly returns if
      its regex does not match. This avoids issues with small formatting
      differences (e.g., '|' immediately before keywords).
    """

    def __init__(
        self,
        on_identity: Optional[Callable[[str, str], None]] = None,
        on_slice: Optional[Callable[[int, dict], None]] = None,
        on_interlock: Optional[Callable[[str], None]] = None,
        on_transmit: Optional[Callable[[int, int], None]] = None,
    ):
        self._on_identity = on_identity
        self._on_slice = on_slice
        self._on_interlock = on_interlock
        self._on_transmit = on_transmit

    # Public entry point
    def feed(self, line: str):
        if not line:
            return
        # Try all parsers; each is a no-op if it doesn't match.
        self._parse_identity(line)
        self._parse_slice(line)
        self._parse_interlock(line)
        self._parse_transmit(line)

    # ----------- Parsers -----------

    def _parse_identity(self, line: str):
        """
        Matches identity lines:
          - 'H1|radio nickname=RemoteQTH callsign=SA6TUT'
          - Some firmwares emit identity as an 'S' line; we still look for the fields.
        """
        if not (line.startswith("H") or " radio " in line or "nickname=" in line or "callsign=" in line):
            return

        nick = None
        call = None

        m1 = re.search(r"\bnickname=([^\s]+)", line)
        if m1:
            nick = m1.group(1)
        m2 = re.search(r"\bcallsign=([^\s]+)", line)
        if m2:
            call = m2.group(1)

        if self._on_identity and (nick or call):
            self._on_identity(nick or "", call or "")

    def _parse_slice(self, line: str):
        """
        Matches slice updates like:
          'S...|slice 0 ... RF_frequency=7.090000 mode=LSB tx=1 ...'
        """
        m_id = re.search(r"\bslice\s+(\d+)\b", line)
        if not m_id:
            return
        sid = int(m_id.group(1))
        data = {}

        # Frequency can be 'RF_frequency' (MHz) or occasionally 'freq'
        mf = re.search(r"\bRF_frequency=([0-9.]+)", line)
        if not mf:
            mf = re.search(r"\bfreq=([0-9.]+)", line)
        if mf:
            try:
                data["freq_mhz"] = float(mf.group(1))
            except ValueError:
                pass

        mm = re.search(r"\bmode=([A-Za-z0-9]+)", line)
        if mm:
            data["mode"] = mm.group(1)

        mt = re.search(r"\btx=([01])\b", line)
        if mt:
            data["tx"] = int(mt.group(1))

        if self._on_slice:
            self._on_slice(sid, data)

    def _parse_interlock(self, line: str):
        """
        Matches interlock/PTT state lines like:
          'S...|interlock state=READY'
          'S...|interlock state=TRANSMITTING'
        """
        if "interlock" not in line:
            return
        ms = re.search(r"\bstate=([A-Z_]+)", line)
        if ms and self._on_interlock:
            self._on_interlock(ms.group(1))

    def _parse_transmit(self, line: str):
        """
        Matches transmit power lines like:
          'S...|transmit rfpower=13 tunepower=13'
        """
        if "transmit" not in line:
            return
        mr = re.search(r"\brfpower=([0-9]+)", line)
        mt = re.search(r"\btunepower=([0-9]+)", line)
        rf = int(mr.group(1)) if mr else None
        tp = int(mt.group(1)) if mt else None
        if self._on_transmit and (rf is not None or tp is not None):
            self._on_transmit(rf, tp)
