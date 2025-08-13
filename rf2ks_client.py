import requests
from requests.exceptions import RequestException, HTTPError, Timeout, ConnectionError
from loghandler import get_logger

logger = None

class RF2KSClientError(Exception):
    """Custom exception class for RF2KSClient errors."""
    pass

class RF2KSClient:
    def __init__(self, config):
        global logger
        if logger is None:
            logger = get_logger()
        amp_cfg = config.get("rf2k_s", {})
        self.enabled = amp_cfg.get("enabled", False)
        self.host = amp_cfg.get("host")
        self.port = amp_cfg.get("port", 8080)
        self.base_url = f"http://{self.host}:{self.port}"

    def fetch_info(self):
        if not self.enabled:
            return

        try:
            response = requests.get(f"{self.base_url}/info", timeout=8)
            response.raise_for_status()

            data = response.json()

            # Extract fields
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

    def verify_frequency_match(self, expected_freq_mhz: float,
                               max_tries: int = 10, delay_s: float = 0.5) -> None:
        """Convenience wrapper around module-level verify_amp_frequency_match()."""
        verify_amp_frequency_match(
            base_url=self.base_url,
            expected_freq_mhz=expected_freq_mhz,
            max_tries=max_tries,
            delay_s=delay_s,
        )

# --- Module level Frequency verification helpers (PA /data) ------------------------------

def _normalize_hz(value, unit) -> int | None:
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


def _truncate_to_khz(hz: int) -> int:
    """
    Truncate a Hz value down to the lower kHz boundary (no rounding).
    Example: 14,255,999 Hz -> 14,255,000 Hz.
    """
    if hz is None:
        return None
    if hz < 0:
        hz = 0
    return (hz // 1000) * 1000


def verify_amp_frequency_match(base_url: str,
                               expected_freq_mhz: float,
                               max_tries: int = 10,
                               delay_s: float = 0.5) -> None:
    """
    Poll RF2K-S /data until the reported frequency matches the radio's set
    frequency when truncated to the kHz boundary (no rounding).

    Success condition:
      truncate_kHz(amp_reported_hz) == truncate_kHz(expected_hz)

    Raises:
      RF2KSClientError if a match is not observed within the attempt budget.
    """
    expected_hz = int(round(float(expected_freq_mhz) * 1_000_000))
    expected_trunc = _truncate_to_khz(expected_hz)

    last_seen = None
    last_err = None

    for _ in range(max_tries):
        try:
            r = requests.get(f"{base_url}/data",
                             headers={"Accept": "application/json"},
                             timeout=1.5)
            r.raise_for_status()
            payload = r.json() or {}
            freq = payload.get("frequency") or {}
            hz = _normalize_hz(freq.get("value"), freq.get("unit"))
            if hz is not None:
                last_seen = hz
                if _truncate_to_khz(hz) == expected_trunc:
                    if logger:
                        logger.debug(f"[RF2K-S] /data OK: amp={hz} Hz ~ radio={expected_hz} Hz (trunc kHz).")
                    return
        except Exception as e:
            last_err = e

        # Short backoff; the PA needs a brief moment to catch up with CAT
        import time as _t
        _t.sleep(delay_s)

    msg = (f"/data did not report expected frequency (truncated kHz). "
           f"expected≈{expected_trunc} Hz, got={_truncate_to_khz(last_seen)} Hz "
           f"(raw last_seen={last_seen}); last_err={last_err!r}")
    if logger:
        logger.error(f"[RF2K-S] {msg}")
    raise RF2KSClientError(msg)
