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
