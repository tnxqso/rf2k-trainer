import time as _time
import requests
from requests.exceptions import RequestException, HTTPError, Timeout, ConnectionError
from loghandler import get_logger, get_tuner_logger
from typing import Optional, Tuple

# Module-level loggers & header state
logger = None
tuner_logger = None
_header_written = False


class RF2KSClientError(Exception):
    """Custom exception class for RF2KSClient errors."""
    pass


class RF2KSClient:
    def __init__(self, config):
        """Initialize RF2K-S client and bind base_url from config."""
        global logger, tuner_logger
        if logger is None:
            logger = get_logger()
        if tuner_logger is None:
            tuner_logger = get_tuner_logger()

        amp_cfg = config.get("rf2k_s", {})
        self.enabled = amp_cfg.get("enabled", False)
        self.host = amp_cfg.get("host")
        self.port = amp_cfg.get("port", 8080)
        self.base_url = f"http://{self.host}:{self.port}"

    # -------------------------------------------------------------------------
    # Basic amplifier info & operate mode
    # -------------------------------------------------------------------------
    def fetch_info(self):
        """Fetch and log basic amplifier info (device/name/firmware)."""
        if not self.enabled:
            return
        try:
            response = requests.get(
                f"{self.base_url}/info",
                headers={"Accept": "application/json"},
                timeout=8
            )
            response.raise_for_status()
            data = response.json()

            device = data.get("device", "N/A")
            name = data.get("custom_device_name", "N/A")
            fw_gui = data.get("software_version", {}).get("GUI", "N/A")
            fw_ctrl = data.get("software_version", {}).get("controller", "N/A")

            logger.info("[RF2K-S] Amplifier Info:")
            logger.info(f"  Device:     {device}")
            logger.info(f"  Name:       {name}")
            logger.info(f"  FW GUI:     {fw_gui}")
            logger.info(f"  FW Ctrl:    {fw_ctrl}")

        except Timeout:
            logger.error("[ERROR] Connection to RF2K-S timed out.")
            raise RF2KSClientError("Connection to RF2K-S timed out.")
        except ConnectionError:
            logger.error("[ERROR] Could not connect to RF2K-S.")
            raise RF2KSClientError("Could not connect to RF2K-S.")
        except HTTPError as e:
            logger.error(f"[ERROR] HTTP error while fetching RF2K-S info: {e}")
            raise RF2KSClientError(f"HTTP error while fetching RF2K-S info: {e}")
        except RequestException as e:
            logger.error(f"[ERROR] Unexpected error while communicating with RF2K-S: {e}")
            raise RF2KSClientError(f"Unexpected communication error with RF2K-S: {e}")
        except ValueError:
            logger.error("[ERROR] Failed to parse JSON response from RF2K-S.")
            raise RF2KSClientError("Failed to parse JSON response from RF2K-S.")
        except Exception as e:
            logger.error(f"[ERROR] Unexpected exception: {e}")
            raise RF2KSClientError(f"Unexpected exception: {e}")

    def get_operate_mode(self) -> str:
        """Return current RF2K-S operate mode (e.g., 'OPERATE', 'STANDBY')."""
        try:
            response = requests.get(
                f"{self.base_url}/operate-mode",
                headers={"Accept": "application/json"},
                timeout=3,
            )
            response.raise_for_status()
            return response.json().get("operate_mode", "").upper()
        except RequestException as e:
            logger.warning(f"[RF2K-S] Could not retrieve operate mode: {e}")
            raise RF2KSClientError(f"Could not retrieve operate mode: {e}")

    def set_operate_mode(self, mode: str):
        """Set RF2K-S operate mode only if different from current."""
        try:
            current_mode = self.get_operate_mode()
            if current_mode == mode.upper():
                logger.info(f"[RF2K-S] Amplifier already in {mode.upper()} mode. No action needed.")
                return

            response = requests.put(
                f"{self.base_url}/operate-mode",
                json={"operate_mode": mode},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=3,
            )
            response.raise_for_status()
            logger.info(f"[RF2K-S] Amplifier successfully set to {mode.upper()} mode.")
        except HTTPError as e:
            logger.error(f"[ERROR] Failed to set RF2K-S to {mode.upper()} mode: {e}")
            raise RF2KSClientError(f"Failed to set RF2K-S to {mode.upper()} mode: {e}")
        except RequestException as e:
            logger.error(f"[ERROR] Request error while setting RF2K-S to {mode.upper()} mode: {e}")
            raise RF2KSClientError(f"Request error while setting RF2K-S to {mode.upper()} mode: {e}")
        except Exception as e:
            logger.error(f"[ERROR] Unexpected error while setting RF2K-S to {mode.upper()} mode: {e}")
            raise RF2KSClientError(f"Unexpected error while setting RF2K-S to {mode.upper()} mode: {e}")

    # -------------------------------------------------------------------------
    # Frequency verification (truncated kHz grid match)
    # -------------------------------------------------------------------------
    def verify_frequency_match(
        self,
        expected_freq_mhz: float,
        max_tries: int = 2,
        delay_s: float = 2
    ) -> None:
        """
        Poll RF2K-S /data until the reported frequency matches the radio's set
        frequency when truncated to the kHz boundary (no rounding).

        Success condition:
        truncate_kHz(amp_reported_hz) == truncate_kHz(expected_hz)

        Raises RF2KSClientError if no match within budget.
        """
        expected_hz = int(round(float(expected_freq_mhz) * 1_000_000))
        expected_trunc = _truncate_to_khz(expected_hz)

        last_seen: Optional[int] = None
        last_err: Optional[Exception] = None

        for _ in range(max_tries):
            try:
                r = requests.get(
                    f"{self.base_url}/data",
                    headers={"Accept": "application/json"},
                    timeout=1.5
                )
                r.raise_for_status()
                payload = r.json() or {}
                freq = payload.get("frequency") or {}
                hz = _normalize_hz(freq.get("value"), freq.get("unit"))
                if hz is not None:
                    last_seen = hz
                    if _truncate_to_khz(hz) == expected_trunc:
                        if logger:
                            logger.debug(
                                f"[RF2K-S] /data OK: amp={hz} Hz ~ radio={expected_hz} Hz (trunc kHz)."
                            )
                        return
            except Exception as e:
                last_err = e

            # Short backoff; the PA needs a brief moment to catch up with CAT
            _time.sleep(delay_s)

        msg = (
            f"/data did not report expected frequency (truncated kHz). "
            f"expected≈{expected_trunc} Hz, got={_truncate_to_khz(last_seen)} Hz "
            f"(raw last_seen={last_seen}); last_err={last_err!r}"
        )
        if logger:
            logger.error(f"[RF2K-S] {msg}")
        raise RF2KSClientError(msg)



    def read_tuner(self, timeout_s: float = 7.0) -> dict:
        """Fetch /tuner JSON; non-fatal. Returns {} on error."""
        try:
            url = f"{self.base_url.rstrip('/')}/tuner"
            resp = requests.get(url, headers={"Accept": "application/json"}, timeout=float(timeout_s))
            resp.raise_for_status()
            return resp.json() or {}
        except Exception as e:
            if logger:
                logger.error(f"[ERROR] Could not fetch tuner data: {e}")
            return {}

    # -------------------------------------------------------------------------
    # Post-unkey /power snapshot
    # -------------------------------------------------------------------------
    def read_power_post_unkey(
        self,
        delay_s: float = 0.2,
        timeout_s: float = 2.0
    ) -> Tuple[Optional[int], Optional[float]]:
        """
        Read RF2K-S /power exactly once shortly after unkey to capture PA's max values.

        Contract:
        - Sleeps `delay_s` before the request (default 0.2 s).
        - GET <base_url>/power (Accept: application/json), timeout `timeout_s`.
        - No retries (keeps PA HTTP load minimal).

        Returns:
          (drive_used_w, swr_final)
          drive_used_w : int|None = forward.max_value (W)
          swr_final    : float|None = swr.max_value

        On any error, returns (None, None) and logs at DEBUG.
        """
        try:
            _time.sleep(max(0.0, float(delay_s)))
            url = f"{self.base_url.rstrip('/')}/power"
            resp = requests.get(url, headers={"Accept": "application/json"}, timeout=float(timeout_s))
            resp.raise_for_status()
            payload = resp.json() or {}

            fwd = payload.get("forward") or {}
            swr = payload.get("swr") or {}

            drive_used_w: Optional[int] = None
            if fwd.get("max_value") is not None:
                try:
                    drive_used_w = int(fwd["max_value"])
                except Exception:
                    try:
                        drive_used_w = int(float(fwd["max_value"]))
                    except Exception:
                        drive_used_w = None

            swr_final: Optional[float] = None
            if swr.get("max_value") is not None:
                try:
                    swr_final = float(swr["max_value"])
                except Exception:
                    swr_final = None

            return drive_used_w, swr_final

        except Exception as e:
            if logger:
                logger.debug(f"/power read after unkey failed (ignored): {e}")
            return None, None

    # -------------------------------------------------------------------------
    # CSV logger
    # -------------------------------------------------------------------------
    def log_tuner_data(self, used_auto_ptt: bool) -> None:
        """
        Fetch tuner data from RF2K-S and append a CSV row via `tuner_logger`.

        Columns:
        freq_kHz,segment_size_kHz,mode,setup,L_nH,C_pF,drive_used_W,swr_final

        Behavior:
        - Always reads /tuner for the base fields.
        - If `used_auto_ptt` is True, performs ONE /power read ~0.2 s after unkey
        to capture forward.max_value (drive_used_W) and swr.max_value (swr_final).
        - If manual PTT, the final two columns are left blank.
        """
        global _header_written

        # Optional PA summary after unkey (one request; non-fatal)
        drive_used_w: Optional[int] = None
        swr_final: Optional[float] = None
        if used_auto_ptt:
            drive_used_w, swr_final = self.read_power_post_unkey(delay_s=0.2, timeout_s=2.0)

        # Base tuner snapshot
        data = self.read_tuner(timeout_s=7.0)

        tf = data.get("tuned_frequency") or {}
        ss = data.get("segment_size") or {}
        Ld = data.get("L") or {}
        Cd = data.get("C") or {}

        freq_kHz = tf.get("value")
        seg_size = ss.get("value")
        mode = data.get("mode", "")
        setup = data.get("setup", "")
        L = Ld.get("value", "N/A")
        C = Cd.get("value", "N/A")

        # Header once
        if not _header_written:
            tuner_logger.info("freq_kHz,segment_size_kHz,mode,setup,L_nH,C_pF,drive_used_W,swr_final")
            _header_written = True

        # Final columns (blank if manual PTT)
        dp = "" if drive_used_w is None else str(drive_used_w)
        swr = "" if swr_final is None else f"{swr_final:.2f}"

        tuner_logger.info(f"{freq_kHz},{seg_size},{mode},{setup},{L},{C},{dp},{swr}")


# --- Module level helpers -----------------------------------------------------

def _normalize_hz(value, unit) -> Optional[int]:
    """
    Convert a frequency {value, unit} pair to Hz (int).
    Accepts unit in {"Hz","kHz","MHz"} (any case). Returns None on failure.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except Exception:
        return None

    u = (unit or "").strip().lower()
    if u == "hz" or u == "":
        return int(round(v))
    if u == "khz":
        return int(round(v * 1e3))
    if u == "mhz":
        return int(round(v * 1e6))
    return None


def _truncate_to_khz(hz: Optional[int]) -> Optional[int]:
    """
    Truncate a Hz value down to the lower kHz boundary (no rounding).
    Example: 14,255,999 Hz -> 14,255,000 Hz.
    """
    if hz is None:
        return None
    if hz < 0:
        hz = 0
    return (hz // 1000) * 1000
