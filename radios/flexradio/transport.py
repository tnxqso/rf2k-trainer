import socket
import threading
import time
import queue
from typing import Optional, Callable

from loghandler import get_logger


class FlexTransport:
    """
    TCP transport for Flex SmartSDR's ASCII line-based API.

    Responsibilities:
      - Open/close the TCP socket with low-latency options.
      - Background listener that reads '\n'-terminated lines.
      - Delivers 'R...' ACK lines to an internal queue for send_command().
      - Delivers all lines (R/H/S/...) to a user callback for parsing/state.
      - Measures ACK round-trip time and logs it in a consistent format.

    This class is intentionally stateless regarding radio logic; it only
    knows sequences, ACKs and networking.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        connect_timeout: float = 5.0,
        recv_timeout: float = 0.5,
        ack_timeout: float = 5.0,
        debug: bool = False,
        line_callback: Optional[Callable[[str], None]] = None,
    ):
        self.host = host
        self.port = int(port)
        self.connect_timeout = float(connect_timeout)
        self.recv_timeout = float(recv_timeout)
        self.ack_timeout = float(ack_timeout)
        self.debug = debug

        self._logger = get_logger()
        self._sock: Optional[socket.socket] = None
        self._sock_lock = threading.Lock()
        self._connected = False

        self._seq = 1
        self._seq_lock = threading.Lock()

        self._resp_q: "queue.Queue[str]" = queue.Queue(maxsize=512)
        self._buffer = b""

        self._listener: Optional[threading.Thread] = None
        self._stop_evt = threading.Event()

        # Called for every received line (including 'R...' ACKs)
        self._line_cb = line_callback

    # ---------- Public properties ----------

    @property
    def connected(self) -> bool:
        return self._connected

    # ---------- TCP setup ----------

    def _apply_tcp_options(self, s: socket.socket):
        """Best-effort low-latency + keepalive socket options."""
        try:
            s.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError:
            pass
        for opt, val in (("TCP_KEEPIDLE", 30), ("TCP_KEEPINTVL", 10), ("TCP_KEEPCNT", 3)):
            if hasattr(socket, opt):
                try:
                    s.setsockopt(socket.IPPROTO_TCP, getattr(socket, opt), val)
                except OSError:
                    pass

    def connect(self):
        """Open the socket, start the listener thread."""
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._apply_tcp_options(s)
        s.settimeout(self.connect_timeout)
        try:
            s.connect((self.host, self.port))
        except socket.timeout:
            self._logger.error(
                f"[NET] Connect timeout after {self.connect_timeout:.1f}s to {self.host}:{self.port}."
            )
            raise
        except OSError as e:
            self._logger.error(f"[NET] Connect error to {self.host}:{self.port}: {e}")
            raise

        # Shorter read timeout for responsive listener.
        s.settimeout(self.recv_timeout)
        with self._sock_lock:
            self._sock = s
        self._connected = True

        self._stop_evt.clear()
        self._listener = threading.Thread(target=self._listener_loop, name="flex-transport", daemon=True)
        self._listener.start()

    def disconnect(self):
        """Stop the listener and close the socket."""
        self._stop_evt.set()
        if self._listener and self._listener.is_alive():
            self._listener.join(timeout=1.0)

        with self._sock_lock:
            try:
                if self._sock:
                    try:
                        self._sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self._sock.close()
            finally:
                self._sock = None
                self._connected = False

    close = disconnect

    # ---------- Line I/O ----------

    def _recv_line(self) -> str:
        """
        Receive one line (without trailing newline). Does not hold the
        socket lock while blocking — avoids artificial command latency.
        """
        start = time.time()
        while b"\n" not in self._buffer:
            if self._stop_evt.is_set():
                return ""
            # Soft guard to avoid infinite waits if server goes silent.
            if time.time() - start > 10:
                raise socket.timeout("Timeout receiving data")

            s = self._sock
            if s is None:
                return ""
            try:
                chunk = s.recv(4096)
            except socket.timeout:
                continue
            except OSError as e:
                raise OSError(f"Socket recv failed: {e}") from e

            if not chunk:
                raise ConnectionError("Socket closed by peer")
            self._buffer += chunk

        line, self._buffer = self._buffer.split(b"\n", 1)
        return line.decode(errors="replace").strip()

    def _listener_loop(self):
        """Read lines and dispatch: ACKs to queue, all lines to callback."""
        try:
            while not self._stop_evt.is_set():
                try:
                    line = self._recv_line()
                except socket.timeout:
                    continue
                except Exception as e:
                    if not self._stop_evt.is_set():
                        self._logger.error(f"[NET] Listener error: {e}. Closing connection.")
                    break

                if not line:
                    continue

                if self.debug:
                    self._logger.debug(f"[RECV] {line}")

                # ACKs always go to response queue (plus optional callback)
                if line.startswith("R"):
                    try:
                        self._resp_q.put_nowait(line)
                    except queue.Full:
                        self._logger.warning("[NET] response_queue full; dropping ACK")

                if self._line_cb:
                    try:
                        self._line_cb(line)
                    except Exception as e:
                        # Parser bugs should not kill the network loop.
                        self._logger.error(f"[PARSER] callback failed: {e}")

        finally:
            with self._sock_lock:
                if self._sock:
                    try:
                        self._sock.shutdown(socket.SHUT_RDWR)
                    except OSError:
                        pass
                    self._sock.close()
                self._sock = None
                self._connected = False

    # ---------- Commands/ACKs ----------

    def _next_seq(self) -> int:
        with self._seq_lock:
            s = self._seq
            self._seq += 1
            return s

    def send_command(
        self,
        command: str,
        *,
        warn_on_nonzero: bool = True,
        log_ack: bool = True,
        ack_timeout: Optional[float] = None,
    ) -> str:
        """
        Send 'C<seq>|<command>' and wait for 'R<seq>|<rc>'.

        Returns the raw 'R...' line on success, raises on timeout or send error.
        """
        if not self.connected or not self._sock:
            raise ConnectionError("Transport is not connected")

        seq = self._next_seq()
        full = f"C{seq}|{command}\n"
        t0 = time.time()

        # Send (protect with socket lock)
        try:
            with self._sock_lock:
                s = self._sock
                if not s:
                    raise ConnectionError("Socket is closed")
                if self.debug:
                    self._logger.debug(f"[SEND] {full.strip()}")
                s.sendall(full.encode())
        except Exception as e:
            self._logger.error(f"[NET] Failed to send command '{command}': {e}")
            raise

        # Wait for matching ACK
        timeout = self.ack_timeout if ack_timeout is None else float(ack_timeout)
        deadline = t0 + timeout
        while time.time() < deadline:
            try:
                resp = self._resp_q.get(timeout=0.1)
            except queue.Empty:
                continue

            if resp.startswith(f"R{seq}|"):
                ack_ms = int((time.time() - t0) * 1000)
                # Parse rc if present
                rc = None
                try:
                    rc = int(resp.split("|", 2)[1])
                except Exception:
                    pass

                if log_ack and rc is not None:
                    if rc == 0:
                        self._logger.debug(f"[ACK] rc=0 in {ack_ms} ms  cmd='{command}'")
                    else:
                        msg = f"[ACK] rc={rc} in {ack_ms} ms  cmd='{command}'  resp='{resp}'"
                        if warn_on_nonzero:
                            self._logger.warning(msg)
                        else:
                            self._logger.debug(msg)
                return resp

        waited_ms = int((time.time() - t0) * 1000)
        self._logger.error(
            f"[ACK] Timeout after {waited_ms} ms waiting for ACK of cmd='{command}'. "
            f"(ack_timeout={timeout:.1f}s)"
        )
        raise TimeoutError(f"ACK timeout for '{command}'")
