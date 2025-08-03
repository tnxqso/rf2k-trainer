import sys
import requests
from requests.exceptions import RequestException, HTTPError
from loghandler import get_logger
logger = get_logger()

class RF2KSClient:
    def __init__(self, config):
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
            if response.status_code != 200:
                logger.error(f"[RF2K-S] HTTP {response.status_code} - {response.reason}")
                raise ConnectionError(f"Failed to connect to RF2K-S at {self.base_url}")

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

        except requests.exceptions.Timeout:
            logger.error("[ERROR] Connection to RF2K-S timed out.")
            logger.error("Aborting...")
            sys.exit(1)

        except requests.exceptions.ConnectionError:
            logger.error("[ERROR] Could not connect to RF2K-S.")
            logger.error("Aborting...")
            sys.exit(1)

        except requests.exceptions.HTTPError as e:
            logger.error(f"[ERROR] HTTP error while fetching RF2K-S info: {e}")
            logger.error("Aborting...")
            sys.exit(1)

        except requests.exceptions.RequestException as e:
            logger.error(f"[ERROR] Unexpected error while communicating with RF2K-S: {e}")
            logger.error("Aborting...")
            sys.exit(1)

        except ValueError:
            logger.error("[ERROR] Failed to parse JSON response from RF2K-S.")
            logger.error("Aborting...")
            sys.exit(1)

        except Exception as e:
            logger.error(f"[ERROR] Unexpected exception: {e}")
            logger.error("Aborting...")
            sys.exit(1)

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
            return ""

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
            logger.error("Aborting...")
            sys.exit(1)
        except Exception as e:
            logger.error(f"[ERROR] Unexpected error while setting RF2K-S to {mode.upper()} mode: {e}")
            logger.error("Aborting...")
            sys.exit(1)
