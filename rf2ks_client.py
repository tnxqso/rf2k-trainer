import sys
import requests

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
            response = requests.get(f"{self.base_url}/info", timeout=3)
            response.raise_for_status()
            data = response.json()

            # Extract fields
            device = data.get("device", "N/A")
            name = data.get("custom_device_name", "N/A")
            fw_gui = data.get("software_version", {}).get("GUI", "N/A")
            fw_ctrl = data.get("software_version", {}).get("controller", "N/A")

            print("[RF2K-S] Amplifier Info:")
            print(f"  Device:     {device}")
            print(f"  Name:       {name}")
            print(f"  FW GUI:     {fw_gui}")
            print(f"  FW Ctrl:    {fw_ctrl}")
        except Exception as e:
            print(f"[ERROR] Could not fetch amplifier info: {e}")
            print("Aborting...")
            sys.exit(1)

    def set_operate_mode(self, mode):
        if not self.enabled:
            return

        mode = mode.upper()
        if mode not in ("OPERATE", "STANDBY"):
            print(f"[RF2K-S] Invalid mode '{mode}', must be OPERATE or STANDBY")
            return

        try:
            response = requests.put(
                f"{self.base_url}/operate-mode",
                json={"operate_mode": mode},
                headers={"Accept": "application/json", "Content-Type": "application/json"},
                timeout=3,
            )
            response.raise_for_status()
            print(f"[RF2K-S] Amplifier set to {mode} mode.")
        except Exception as e:
            print(f"[ERROR] Failed to set RF2K-S to {mode} mode: {e}")
            print("Aborting...")
            sys.exit(1)
