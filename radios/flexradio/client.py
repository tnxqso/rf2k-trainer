import time
from typing import Optional, Dict, Any

from loghandler import get_logger
from radio_interface import BaseRadioClient, BaseRadioError

from .transport import FlexTransport
from .parser import FlexParser


class FlexRadioError(BaseRadioError):
    """Raised for FlexRadio client-specific errors."""
    pass


class FlexRadioClient(BaseRadioClient):
    """
    High-level FlexRadio client used by RF2K-Trainer.

    Composition:
      - FlexTransport: networking, ACKs, listener.
      - FlexParser: parses lines and reports updates via callbacks.

    Key features:
      - Event-driven PTT (interlock status).
      - One-time snapshot of the original slice/mode/frequency for restore().
      - No-op short-circuiting for mode/power/frequency to avoid redundant ACK waits.
      - Clear timeouts with explicit logs when an ACK does not arrive in time.
    """

    # Capability used by main tuning loop (Flex supports PTT read)
    ptt_supported: bool = True

    def __init__(self, host: str, port: int, debug: bool = False):
        self.logger = get_logger()
        self.host = host
        self.port = int(port)
        self.debug = debug

        # State mirroring
        self._slices: Dict[int, Dict[str, Any]] = {}
        self.tx_slice_id: Optional[int] = None
        self.nickname: Optional[str] = None
        self.callsign: Optional[str] = None

        # Interlock/PTT
        self.tx_state: str = "UNKNOWN"
        self._ptt_active = False

        # Power values reflected from 'transmit' updates
        self.rfpower_value: Optional[int] = None
        self.tunepower_value: Optional[int] = None

        # Original state snapshot (for restore)
        self._orig = {
            "taken": False,
            "slice_id": None,
            "mode": None,
            "freq_mhz": None,
            "rfpower": None,
            "tunepower": None,
        }

        # Build transport + parser
        self.transport = FlexTransport(
            host=self.host,
            port=self.port,
            connect_timeout=5.0,
            recv_timeout=0.5,
            ack_timeout=5.0,
            debug=self.debug,
            line_callback=self._on_line,
        )
        self.parser = FlexParser(
            on_identity=self._on_identity,
            on_slice=self._on_slice,
            on_interlock=self._on_interlock,
            on_transmit=self._on_transmit,
        )

    # ------------- Connect/Disconnect -------------

    def connect(self):
        self.transport.connect()
        self.logger.info(f"Connected to FlexRadio at {self.host}:{self.port}")

        # Post-connect handshake (soft attempts if unsupported)
        self._send_rc_soft("client program=rf2k-trainer")
        for cmd in ("sub slice all=1", "sub interlock all=1", "sub transmit all=1"):
            try:
                self._send_rc_checked(cmd)
            except Exception as e:
                self.logger.debug(f"[HANDSHAKE] '{cmd}' failed: {e}")
        self._send_rc_soft("status")  # optional on some fw

        # Let first slice updates flow in briefly
        t0 = time.time()
        while (time.time() - t0) < 1.0 and self.tx_slice_id is None:
            time.sleep(0.05)

        # First snapshot (may be partial; frequency can be backfilled later)
        self.snapshot_state(wait_s=1.0)
        self._dump_state("after-connect")
        self.logger.info("Connection to FlexRadio established.")

    def disconnect(self):
        self.transport.disconnect()
        self.logger.info("TCP connection closed")

    close = disconnect

    def shutdown(self, restore: bool = True):
        if restore:
            if not self._orig.get("taken"):
                self.logger.info("[RESTORE] skipped: no snapshot was taken earlier.")
            else:
                try:
                    self.restore_state()
                except Exception as e:
                    self.logger.warning(f"[RESTORE] failed: {e}")
        self.disconnect()

    # ------------- Parser callback bridge -------------

    def _on_line(self, line: str):
        """Bridges raw lines from transport into the parser."""
        self.parser.feed(line)

    def _on_identity(self, nickname: str, callsign: str):
        if nickname:
            self.nickname = nickname
        if callsign:
            self.callsign = callsign

    def _on_slice(self, sid: int, data: dict):
        # Merge into local slice state
        sl = self._slices.setdefault(sid, {})
        sl.update(data)

        # TX flag
        if "tx" in data and data["tx"] == 1 and self.tx_slice_id != sid:
            self.tx_slice_id = sid
            self.logger.info(f"[SLICE] TX slice now: {sid}")

        # First time we have BOTH mode and freq>0 — take the snapshot if not taken.
        if not self._orig["taken"]:
            mode = sl.get("mode")
            f = sl.get("freq_mhz")
            if mode and f and f > 0.0:
                self._orig.update(
                    {
                        "taken": True,
                        "slice_id": sid,
                        "mode": mode,
                        "freq_mhz": f,
                        "rfpower": self.rfpower_value,
                        "tunepower": self.tunepower_value,
                    }
                )
                # Triplet format: e.g. 5.354.800
                self.logger.info(f"[SNAPSHOT] slice={sid} mode={mode} freq={self._fmt_mhz_triplet(f)}")

        # If snapshot was taken without freq earlier, backfill when freq arrives.
        if self._orig["taken"] and self._orig.get("freq_mhz") is None and sl.get("freq_mhz"):
            self._orig["freq_mhz"] = sl["freq_mhz"]

    def _on_interlock(self, state: str):
        self.tx_state = state
        # Consider TX active on TRANSMITTING or any 'TX*' excluding NOT_*.
        active = (state == "TRANSMITTING") or (state.startswith("TX") and not state.startswith("NOT_"))
        self._ptt_active = active

    def _on_transmit(self, rfpower: Optional[int], tunepower: Optional[int]):
        if rfpower is not None:
            self.rfpower_value = rfpower
        if tunepower is not None:
            self.tunepower_value = tunepower

    # ------------- Public radio API -------------

    def get_ptt(self) -> bool:
        return bool(self._ptt_active)

    def wait_for_tx(self, timeout: float = 90.0) -> bool:
        end = time.time() + max(0.0, timeout)
        while time.time() < end:
            if self._ptt_active:
                return True
            time.sleep(0.03)
        return self._ptt_active

    def wait_for_unkey(self, timeout: float = 300.0) -> bool:
        end = time.time() + max(0.0, timeout)
        while time.time() < end:
            if not self._ptt_active:
                return True
            time.sleep(0.03)
        return not self._ptt_active

    def _choose_slice_id_for_commands(self) -> int:
        if self.tx_slice_id is not None:
            return self.tx_slice_id
        if self._slices:
            return sorted(self._slices.keys())[0]
        return 0

    def set_mode(self, mode: str = "CW", width: int = 400):
        sid = self._choose_slice_id_for_commands()
        current = (self._slices.get(sid) or {}).get("mode")
        if current and current.upper() == mode.upper():
            if self.debug:
                self.logger.debug(f"[MODE] already {mode} on slice {sid}; skipping")
            return
        self.logger.info(f"[MODE] Setting mode={mode} on slice {sid}")
        self._send_rc_checked(f"slice set {sid} mode={mode}")

    def set_frequency(self, freq_mhz: float):
        sid = self._choose_slice_id_for_commands()
        current = (self._slices.get(sid) or {}).get("freq_mhz")
        if current is not None and abs(current - float(freq_mhz)) < 0.00001:
            if self.debug:
                self.logger.debug(f"[TUNE] already at {freq_mhz:.4f} MHz on slice {sid}; skipping")
            return
        self.logger.info(f"[TUNE] Setting slice {sid} to {freq_mhz:.4f} MHz")
        self._send_rc_checked(f"slice tune {sid} {freq_mhz:.4f}")

    def set_drive_power(self, rfpower: int):
        target = int(rfpower)
        if self.rfpower_value == target and self.tunepower_value == target:
            if self.debug:
                self.logger.debug(f"[POWER] already {target}W (rf & tune); skipping")
            return
        self.logger.info(f"[POWER] Setting tunepower={target}W and rfpower={target}W")
        self._send_rc_checked(f"transmit set tunepower={target} rfpower={target}")

    def wait_for_slice_freq(self, target_mhz: float, tol_hz: float = 10.0, timeout_s: float = 1.5) -> bool:
        end = time.time() + max(0.0, timeout_s)
        tol_mhz = tol_hz / 1e6
        sid = self._choose_slice_id_for_commands()
        while time.time() < end:
            cur = (self._slices.get(sid) or {}).get("freq_mhz")
            if cur is not None and abs(cur - target_mhz) <= tol_mhz:
                return True
            time.sleep(0.03)
        return False

    def ensure_tx_slice_locked(self):
        """Re-assert snapshot TX slice if some external action changed it."""
        try:
            desired = self._orig.get("slice_id") or self._choose_slice_id_for_commands()
            current = self.tx_slice_id
            if current and desired and current != desired:
                self._send_rc_checked(f"slice set {desired} tx=1")
                self.logger.info(f"[SLICE] Re-assert TX slice {desired}")
        except Exception as e:
            if self.debug:
                self.logger.debug(f"[SLICE] ensure_tx_slice_locked skipped: {e}")

    def settle_after_tune(self, ms: int = 250):
        time.sleep(max(0, ms) / 1000.0)

    # ------------- Snapshot/Restore -------------

    def snapshot_state(self, wait_s: float = 1.5) -> None:
        """
        Take a one-time snapshot of the current TX slice (mode/frequency/power).
        For Flex we subscribe to slice/interlock/transmit and mirror state as it arrives.
        This method simply waits up to `wait_s` for the active slice to populate and
        persists the first complete snapshot. Subsequent calls are no-ops.
        """
        if self._orig["taken"]:
            return

        sid = self._choose_slice_id_for_commands()
        deadline = time.time() + max(0.0, float(wait_s))
        mode = None
        freq_mhz = None

        # Poll the mirrored slice dictionary until we have both fields or timeout.
        while time.time() < deadline:
            sl = self._slices.get(sid, {})
            if sl:
                mode = sl.get("mode") or mode
                f = sl.get("freq_mhz")
                if f:
                    freq_mhz = f
            if mode and freq_mhz:
                break
            time.sleep(0.03)

        # Persist whatever we have (even partial), so we don't repeat work.
        self._orig.update(
            {
                "taken": True,
                "slice_id": sid,
                "mode": mode,
                "freq_mhz": freq_mhz,
                "rfpower": self.rfpower_value,
                "tunepower": self.tunepower_value,
            }
        )

        # Friendly one-liner; omit frequency if still unknown.
        parts = [f"[SNAPSHOT] slice={sid}", f"mode={mode or 'unknown'}"]
        if freq_mhz:
            parts.append(f"freq={self._fmt_mhz_triplet(freq_mhz)}")
        self.logger.info(" ".join(parts))

    def restore_state(self):
        sid = self._orig.get("slice_id")
        if sid is None:
            self.logger.info("[RESTORE] skipped: no snapshot available (no slice_id).")
            return

        mode = self._orig.get("mode")
        if mode:
            self.logger.info(f"[RESTORE] mode={mode} on slice {sid}")
            self._send_rc_checked(f"slice set {sid} mode={mode}")

        f_mhz = self._orig.get("freq_mhz")
        if f_mhz is not None:
            self.logger.info(f"[RESTORE] freq={f_mhz:.4f} MHz on slice {sid}")
            self._send_rc_checked(f"slice tune {sid} {f_mhz:.4f}")
        else:
            self.logger.info("[RESTORE] freq is unknown; skipping frequency restore.")

        self.logger.info("[RESTORE] done")

    # ------------- Utilities -------------

    def _dump_state(self, tag: str):
        self.logger.info(
            f"[STATE:{tag}] tx_slice={self.tx_slice_id} tx_state={self.tx_state} "
            f"rfpower={self.rfpower_value} tunepower={self.tunepower_value}"
        )

    # ------------- Command helpers -------------

    def _send_rc_checked(self, command: str):
        """Send a command and raise FlexRadioError if rc != 0."""
        try:
            resp = self.transport.send_command(command)
        except TimeoutError as e:
            raise FlexRadioError(str(e)) from e
        # Parse rc
        rc = None
        try:
            rc = int(resp.split("|", 2)[1])
        except Exception:
            pass
        if rc not in (0, None):
            raise FlexRadioError(f"Command '{command}' failed rc={rc}")
        return resp

    def _send_rc_soft(self, command: str):
        """
        Send a command but silence ACK logging and never raise on nonzero/timeout.
        Useful for optional/firmware-dependent calls during handshake.
        """
        try:
            return self.transport.send_command(
                command,
                warn_on_nonzero=False,
                log_ack=False,
            )
        except Exception:
            return ""

    @staticmethod
    def _fmt_mhz_triplet(val_mhz: float) -> str:
        """Format 5.3548 MHz as '5.354.800' (MHz.KHz.Hz)."""
        total_hz = int(round(val_mhz * 1_000_000))
        mhz = total_hz // 1_000_000
        rem = total_hz % 1_000_000
        khz = rem // 1_000
        hz = rem % 1_000
        return f"{mhz}.{khz:03d}.{hz:03d}"