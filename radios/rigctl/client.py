# rigctl_client.py
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
    Hamlib rigctl network client.

    On Windows, uses raw TCP sockets by default (more reliable than telnetlib).
    On other platforms, uses telnetlib unless you force sockets by flipping _use_socket.
    """

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
        self._sock_buf: bytes = b""  # persistent RX buffer for raw socket transport
        self.conn: Optional[telnetlib.Telnet] = None

        self.connected = False
        self.lock = threading.RLock()

        # cached snapshot
        self.mode: Optional[str] = None
        self.width: Optional[int] = None
        self.freq_hz: Optional[int] = None

        # capability hint (the app probes once; we maintain this flag)
        self.ptt_supported: bool = True

    # ---------------------------------------------------------------------
    # Public interface expected by the app
    # ---------------------------------------------------------------------

    def get_description(self) -> str:
        """Human-friendly description for UI/logs."""
        return "Hamlib rigctld"

    
    def connect(self):
        """Establish connection to rigctld service (satisfies BaseRadioClient)."""
        return self._connect()

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
            # Clear, actionable message
            logger.error(
                "Failed to connect to rigctld at %s:%d. Is rigctld running? "
                "If you disabled auto_start_rigctld in config, start it manually "
                "or re-enable autostart. Error: %s",
                self.host, self.port, e
            )
            raise RigctlError(f"Failed to connect to rigctld: {e}")

        # Best-effort snapshot, never fail connect on this
        try:
            self.snapshot_state()
        except Exception as e:
            if self.debug:
                logger.debug(f"[SNAPSHOT] failed: {e}")

    def set_mode(self, mode: str = "CW", width: int = 400):
        mode = (mode or "CW").upper()
        self._send(f"M {mode} {int(width)}", quiet=False, expect_value=False)
        # update cached snapshot
        self.mode, self.width = mode, int(width)
        logger.info(f"[MODE] Setting {mode} {width}")

    def set_frequency(self, freq_mhz: float):
        # rigctl expects Hz as integer
        hz = int(round(freq_mhz * 1_000_000))
        self._send(f"F {hz}", quiet=False, expect_value=False)
        # update cached snapshot
        self.freq_hz = hz
        logger.info(f"[FREQ] Setting {freq_mhz:.4f} MHz")

    def get_ptt(self) -> bool:
        """
        Returns True if the radio reports TX, else False.
        If the backend reports 'RPRT -11' (Feature not available), mark
        ptt_supported=False so caller can switch to MANUAL flow.
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

    def disconnect(self):
        self.shutdown(restore=False)

    def shutdown(self, restore: bool = True):
        """Close transports gracefully."""
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

    # Non portable in rigctl, keep method for API parity and warn user
    def set_drive_power(self, rfpower: int):
        logger.warning("Drive power cannot be set portably via rigctl, configure TX power on the radio.")

    # ---------------------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------------------

    def snapshot_state(self) -> None:
        """
        Lightweight rigctl snapshot.

        - Queries mode/width once via 'm' and frequency once via 'f'.
        - Updates local cache (self.mode, self.width, self.freq_hz).
        - Logs a single concise line:
            [SNAPSHOT] mode=CW width=400Hz freq=5.354.800
        (Width/frequency omitted if unknown.)
        """

        # Read mode/width
        mode, width = self._get_mode()
        if mode:
            self.mode = mode
        if width is not None:
            self.width = width

        # Read frequency (Hz)
        freq_hz = self._get_freq()
        if freq_hz is not None:
            self.freq_hz = freq_hz

        # Helper: Hz -> 'M.KKK.HHH'
        def fmt_triplet(hz: int) -> str:
            mhz = hz // 1_000_000
            rem = hz % 1_000_000
            khz = rem // 1_000
            h   = rem % 1_000
            return f"{mhz}.{khz:03d}.{h:03d}"

        # Build friendly one-liner
        parts = ["[SNAPSHOT]"]
        parts.append(f"mode={self.mode}" if self.mode else "mode=unknown")
        if self.width is not None:
            parts.append(f"width={self.width}Hz")
        if self.freq_hz is not None:
            parts.append(f"freq={fmt_triplet(self.freq_hz)}")

        logger.info(" ".join(parts))

    def _get_mode(self) -> Tuple[Optional[str], Optional[int]]:
        """
        Returns (mode, width). Some rigs (incl. Dummy) emit:
            MODE\\n
            WIDTH\\n
        so we read a potential second line from the buffer/conn.
        """
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
            # Try to read WIDTH from the next line (socket buffer or telnet)
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
        """Reopen the transport, idempotent."""
        with self.lock:
            try:
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
        """
        Return one LF-terminated line from raw socket.
        Uses a persistent buffer so extra data is preserved for the next read.
        """
        if self._sock is None:
            return b""

        end = time.time() + timeout

        # Serve from buffer if a full line is already present
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

        # Timeout without full line: return whatever we have
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
                # resend once
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
