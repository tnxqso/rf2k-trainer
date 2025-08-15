# rigctl_client.py (a.k.a. your rigctl section in client.py)
import os
import socket
import telnetlib
import threading
import time
from typing import Optional, Tuple

from radio_interface import BaseRadioClient, BaseRadioError
from loghandler import get_logger

logger = None

class RigctlError(BaseRadioError):
    """Custom exception for RigctlClient-related errors."""
    pass


class RigctlClient(BaseRadioClient):
    """
    Hamlib rigctl network client with optional event-driven PTT.

    Design:
      - Transport: raw TCP on Windows (more reliable than telnetlib), telnetlib otherwise.
      - A lightweight background thread polls 't' at a modest interval and updates
        an internal PTT state machine guarded by a Condition. It enables event-driven
        waits (wait_for_tx/unkey) without busy-waiting in the main loop.
      - If rig/rigctld returns 'RPRT -11' for 't', we mark ptt_supported=False and
        stop the event thread so the app can switch to MANUAL mode.
      - On transient comm errors the thread attempts one reconnect. If that fails,
        it disables event mode cleanly and the app can fall back to polling.
    """

    # Capability flags consumed by the tuning loop
    supports_event_ptt: bool = False
    ptt_supported: bool = True  # may be flipped to False on RPRT -11

    def __init__(
        self,
        host: str = "localhost",
        port: int = 4532,
        label: str = "Radio via rigctl",
        debug: bool = False,
    ) -> None:
        global logger
        if logger is None:
            logger = get_logger()

        self.host = host
        self.port = int(port)
        self.label = label
        self.debug = bool(debug)

        # transport selection
        self._use_socket = (os.name == "nt")  # default to raw TCP on Windows
        self._sock: Optional[socket.socket] = None
        self._sock_buf: bytes = b""
        self.conn: Optional[telnetlib.Telnet] = None

        self.connected = False
        self.lock = threading.RLock()

        # cached snapshot
        self.mode: Optional[str] = None
        self.width: Optional[int] = None
        self.freq_hz: Optional[int] = None

        # --- Event PTT machinery ---
        # Condition protecting PTT booleans + edge notifications
        self._ptt_cond = threading.Condition()
        self._ptt_active = False
        self._ptt_last = False  # for edge detection
        self._evt_thread: Optional[threading.Thread] = None
        self._evt_stop = threading.Event()
        # Poll cadence is conservative to avoid overloading rigctld
        self._poll_idle_s = 0.10   # while RX (no TX)
        self._poll_tx_s = 0.05     # while TX (a bit faster for snappy unkey)
        self._reconnect_once = True  # single automatic reconnect attempt

    # ---------------------------------------------------------------------
    # Public interface expected by the app
    # ---------------------------------------------------------------------

    def get_description(self) -> str:
        return "Hamlib rigctld"

    def connect(self):
        """Establish connection to rigctld service and start PTT monitor thread."""
        self._connect()
        # Start event monitor thread; it will auto-disable if unsupported
        self._start_ptt_monitor()

    def _connect(self, timeout: float = 5.0):
        """Open connection to rigctld and take an initial snapshot."""
        try:
            if self._use_socket:
                self._sock = socket.create_connection((self.host, self.port), timeout=timeout)
                self._sock.settimeout(3.0)
                self._sock_buf = b""
            else:
                self.conn = telnetlib.Telnet(self.host, self.port, timeout=timeout)
                self.conn.timeout = 2.0
            self.connected = True
            logger.info(f"Connected to rigctld at {self.host}:{self.port}")
        except Exception as e:
            logger.error(
                "Failed to connect to rigctld at %s:%d. Is rigctld running? "
                "If you disabled auto_start_rigctld in config, start it manually "
                "or re-enable autostart. Error: %s",
                self.host, self.port, e
            )
            raise RigctlError(f"Failed to connect to rigctld: {e}")

        # Best-effort snapshot (never fail connect)
        try:
            self.snapshot_state()
        except Exception as e:
            if self.debug:
                logger.debug(f"[SNAPSHOT] failed: {e}")

    def set_mode(self, mode: str = "CW", width: int = 400):
        mode = (mode or "CW").upper()
        self._send(f"M {mode} {int(width)}", quiet=False, expect_value=False)
        self.mode, self.width = mode, int(width)
        logger.info(f"[MODE] Setting {mode} {width}")

    def set_frequency(self, freq_mhz: float):
        hz = int(round(freq_mhz * 1_000_000))
        self._send(f"F {hz}", quiet=False, expect_value=False)
        self.freq_hz = hz
        logger.info(f"[FREQ] Setting {freq_mhz:.4f} MHz")

    def get_ptt(self) -> bool:
        """
        One-shot PTT read (used by POLLING fallback).
        Marks ptt_supported=False if 'RPRT -11' is observed.
        """
        resp = self._send("t", quiet=False, expect_value=True).strip()
        if resp == "":
            return False

        r = resp.upper()
        if r.startswith("RPRT -11"):
            if self.ptt_supported:
                logger.debug("[PTT] Rig/rigctld does not support reading PTT (RPRT -11).")
            self.ptt_supported = False
            return False

        try:
            v = int(resp.split()[0])
            return v != 0
        except ValueError:
            if self.debug:
                logger.debug(f"[GET PTT] unexpected: '{resp}'")
            return False

    # ---- Event-driven waits (exposed to the tuning loop) ----

    def wait_for_tx(self, timeout: float = 90.0) -> bool:
        """Block until TX asserted or timeout. Returns True if TX started."""
        deadline = time.time() + max(0.0, timeout)
        with self._ptt_cond:
            while time.time() < deadline:
                if self._ptt_active:
                    return True
                left = deadline - time.time()
                self._ptt_cond.wait(timeout=min(0.25, max(0.0, left)))
            return self._ptt_active

    def wait_for_unkey(self, timeout: float = 300.0) -> bool:
        """Block until TX deasserted or timeout. Returns True if TX stopped."""
        deadline = time.time() + max(0.0, timeout)
        with self._ptt_cond:
            while time.time() < deadline:
                if not self._ptt_active:
                    return True
                left = deadline - time.time()
                self._ptt_cond.wait(timeout=min(0.25, max(0.0, left)))
            return not self._ptt_active

    def disconnect(self):
        self.shutdown(restore=False)

    def shutdown(self, restore: bool = True):
        """Stop monitor thread and close transports."""
        self._stop_ptt_monitor()

        with self.lock:
            if self._sock:
                try:
                    self._sock.close()
                except Exception:
                    pass
                self._sock = None
                self._sock_buf = b""
            if self.conn:
                try:
                    self.conn.close()
                except Exception:
                    pass
                self.conn = None
            self.connected = False
        logger.info("Disconnected from rigctld")

    def set_drive_power(self, rfpower: int):
        logger.warning("Drive power cannot be set portably via rigctl, configure TX power on the radio.")

    # ---------------------------------------------------------------------
    # Snapshot helpers
    # ---------------------------------------------------------------------

    def snapshot_state(self) -> None:
        """
        Lightweight rigctl snapshot of mode/width/frequency.
        Logs a single concise line for visibility.
        """
        mode, width = self._get_mode()
        if mode:
            self.mode = mode
        if width is not None:
            self.width = width

        freq_hz = self._get_freq()
        if freq_hz is not None:
            self.freq_hz = freq_hz

        def fmt_triplet(hz: int) -> str:
            mhz = hz // 1_000_000
            rem = hz % 1_000_000
            khz = rem // 1_000
            h   = rem % 1_000
            return f"{mhz}.{khz:03d}.{h:03d}"

        parts = ["[SNAPSHOT]"]
        parts.append(f"mode={self.mode}" if self.mode else "mode=unknown")
        if self.width is not None:
            parts.append(f"width={self.width}Hz")
        if self.freq_hz is not None:
            parts.append(f"freq={fmt_triplet(self.freq_hz)}")
        logger.info(" ".join(parts))

    def _get_mode(self) -> Tuple[Optional[str], Optional[int]]:
        resp = self._send("m", expect_value=True).strip()
        parts = resp.split()
        mode = parts[0].upper() if parts else None
        width: Optional[int] = None

        if len(parts) >= 2:
            try:
                width = int(parts[1])
            except ValueError:
                width = None
        else:
            # try read the next line for width
            try:
                if self._use_socket:
                    extra = self._readline_socket(timeout=0.5)
                else:
                    extra = self.conn.read_until(b"\n", timeout=0.5) if self.conn else b""
                s = extra.decode(errors="replace").strip() if extra else ""
                if s and not s.upper().startswith("RPRT"):
                    try:
                        width = int(s.split()[0])
                    except ValueError:
                        pass
            except Exception:
                pass

        if mode is None and self.debug:
            logger.debug(f"[GET MODE] unexpected: '{resp}'")
        return mode, width

    def _get_freq(self) -> Optional[int]:
        resp = self._send("f", expect_value=True).strip()
        if not resp:
            if self.debug:
                logger.debug("[GET FREQ] unexpected empty response")
            return None
        try:
            return int(resp.split()[0])
        except ValueError:
            if self.debug:
                logger.debug(f"[GET FREQ] unexpected: '{resp}'")
            return None

    # ---------------------------------------------------------------------
    # Transport
    # ---------------------------------------------------------------------

    def _reconnect(self, timeout: float = 5.0):
        """Reopen the transport, idempotent (used by event thread on error)."""
        with self.lock:
            try:
                if self._sock:
                    try: self._sock.close()
                    except Exception: pass
                    self._sock = None
                    self._sock_buf = b""
                if self.conn:
                    try: self.conn.close()
                    except Exception: pass
                    self.conn = None

                if self._use_socket:
                    self._sock = socket.create_connection((self.host, self.port), timeout=timeout)
                    self._sock.settimeout(3.0)
                    self._sock_buf = b""
                else:
                    self.conn = telnetlib.Telnet(self.host, self.port, timeout=timeout)
                    self.conn.timeout = 2.0

                self.connected = True
                logger.info(f"[rigctl] reconnected {self.host}:{self.port}")
            except Exception as e:
                self.connected = False
                raise RigctlError(f"Failed to reconnect to rigctld: {e}")

    def _readline_socket(self, timeout: float = 2.5) -> bytes:
        """Return one LF-terminated line from raw socket using a persistent buffer."""
        if self._sock is None:
            return b""

        end = time.time() + timeout

        if b"\n" in self._sock_buf:
            line, self._sock_buf = self._sock_buf.split(b"\n", 1)
            return line

        while time.time() < end:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    break
                self._sock_buf += chunk
                if b"\n" in self._sock_buf:
                    line, self._sock_buf = self._sock_buf.split(b"\n", 1)
                    return line
            except socket.timeout:
                break
            except Exception:
                break

        if self._sock_buf:
            line = self._sock_buf
            self._sock_buf = b""
            return line
        return b""

    def _send(self, cmd: str, quiet: bool = False, expect_value: bool = False) -> str:
        """Send a rigctl command, return first line, retry once on transport error."""
        if not quiet and self.debug:
            logger.debug(f"[rigctl] > {cmd}")

        with self.lock:
            try:
                data = (cmd + "\n").encode()
                if self._use_socket:
                    assert self._sock is not None
                    self._sock.sendall(data)
                    line = self._readline_socket(timeout=2.5)
                else:
                    assert self.conn is not None
                    self.conn.write(data)
                    line = self.conn.read_until(b"\n", timeout=2.0)
            except Exception as e:
                first_err = e
                if self.debug:
                    logger.debug(f"[rigctl] comm error, attempting reconnect: {e}")
                self._reconnect()
                try:
                    if self._use_socket:
                        assert self._sock is not None
                        self._sock.sendall((cmd + "\n").encode())
                        line = self._readline_socket(timeout=2.5)
                    else:
                        assert self.conn is not None
                        self.conn.write((cmd + "\n").encode())
                        line = self.conn.read_until(b"\n", timeout=2.0)
                except Exception:
                    raise RigctlError(f"Communication error with rigctld: {first_err}")

        first = line.decode(errors="replace").strip() if line else ""
        if not quiet and self.debug:
            logger.debug(f"[rigctl] < {first}")

        # Some builds echo "RPRT 0" first, then deliver the actual value next
        if expect_value and (first == "" or first.upper().startswith("RPRT")):
            try:
                if self._use_socket:
                    extra = self._readline_socket(timeout=0.3)
                else:
                    extra = self.conn.read_until(b"\n", timeout=0.3) if self.conn else b""
                extra_dec = extra.decode(errors="replace").strip() if extra else ""
                if extra_dec and not extra_dec.upper().startswith("RPRT"):
                    if self.debug:
                        logger.debug(f"[rigctl] << {extra_dec}")
                    return extra_dec
            except Exception:
                pass

        # Telnet: drain tail to avoid contaminating next call
        if not self._use_socket and self.conn:
            try:
                peek = self.conn.read_very_eager()
                if peek and self.debug:
                    tail = peek.decode(errors="replace").strip()
                    if tail:
                        logger.debug(f"[rigctl] (drained) {tail}")
            except Exception:
                pass

        return first

    # Optional, used by app when printing
    def get_label(self) -> str:
        return self.label

    # ---------------------------------------------------------------------
    # Event PTT background thread
    # ---------------------------------------------------------------------

    def _start_ptt_monitor(self):
        """Spawn the background PTT monitor if not already running."""
        if self._evt_thread and self._evt_thread.is_alive():
            return
        self._evt_stop.clear()
        self._reconnect_once = True
        self.supports_event_ptt = True  # optimistic; will auto-disable on RPRT -11
        self._evt_thread = threading.Thread(
            target=self._ptt_monitor_loop, name="rigctl-ptt", daemon=True
        )
        self._evt_thread.start()

    def _stop_ptt_monitor(self):
        """Stop the background PTT monitor if running."""
        self._evt_stop.set()
        t = self._evt_thread
        if t and t.is_alive():
            t.join(timeout=1.0)
        self._evt_thread = None
        # Do not flip supports_event_ptt here; keep last known state.

    def _ptt_monitor_loop(self):
        """
        Poll 't' with modest cadence and notify waiters on state edges.
        Handles:
          - RPRT -11 -> mark ptt_supported=False, disable event support.
          - Transport errors -> single reconnect attempt, then disable event support.
        """
        try:
            while not self._evt_stop.is_set():
                try:
                    resp = self._send("t", quiet=True, expect_value=True).strip()
                except Exception as e:
                    # Transport hiccup: single reconnect attempt
                    if self._reconnect_once:
                        if self.debug:
                            logger.debug(f"[PTT EVT] transport error: {e}, trying reconnect")
                        try:
                            self._reconnect()
                            self._reconnect_once = False
                            time.sleep(0.1)
                            continue
                        except Exception as e2:
                            logger.debug(f"[PTT EVT] reconnect failed: {e2}")
                    # Give up on event mode; keep app alive with polling
                    self._disable_event_mode("transport error")
                    return

                if resp.upper().startswith("RPRT -11"):
                    # No PTT capability -> MANUAL
                    self.ptt_supported = False
                    self._set_ptt_state(False)
                    self._disable_event_mode("RPRT -11 (no PTT support)")
                    return

                # Parse 't' value
                active = False
                try:
                    active = int(resp.split()[0]) != 0
                except Exception:
                    if self.debug:
                        logger.debug(f"[PTT EVT] unexpected 't' response: '{resp}'")

                self._set_ptt_state(active)

                # Cadence: slower when idle, slightly faster while TX
                time.sleep(self._poll_tx_s if active else self._poll_idle_s)

        finally:
            # On exit, leave supports_event_ptt as-is unless we explicitly disabled it.
            return

    def _set_ptt_state(self, active: bool):
        """Update PTT state and notify waiters on edges."""
        with self._ptt_cond:
            self._ptt_active = bool(active)
            if self._ptt_active != self._ptt_last:
                self._ptt_last = self._ptt_active
                self._ptt_cond.notify_all()

    def _disable_event_mode(self, reason: str):
        """Disable event-driven support; the app can fall back to polling or manual."""
        if self.supports_event_ptt:
            logger.debug(f"[PTT EVT] disabling event-driven mode: {reason}")
        self.supports_event_ptt = False
        # Do not flip ptt_supported here; that flag reflects capability of 't'.
