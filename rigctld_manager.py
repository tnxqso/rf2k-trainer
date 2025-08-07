import shutil
import subprocess
import time
import sys
import socket
import os
import platform
from typing import Optional, Any
from loghandler import get_logger

logger = None

class RigCtldManagerError(Exception):
    """Generic rigctld manager error (superclass for all rigctld manager errors)."""
    pass


class RigctldManager:
    def __init__(
        self,
        model: int,
        serial_port: str,
        port: int = 4532,
        rigctld_path: Optional[str] = None,
        context: Optional[Any] = None  # future-proof injection point (e.g., AppContext)
    ):
        global logger
        if logger is None:
            logger = get_logger()

        self.model = model
        self.serial_port = serial_port
        self.port = port
        self.context = context
        self.rigctld_path = rigctld_path or shutil.which("rigctld")
        self.rigctl_path: Optional[str] = shutil.which("rigctl")
        self.process: Optional[subprocess.Popen] = None
        self.rig_description: Optional[str] = None

        if not os.path.isfile(self.rigctld_path):
            msg = (
                f"The configured rigctld_path is invalid or not a file:\n"
                f"  {self.rigctld_path}\n\n"
                "💡 Please check that this path is correct and points to rigctld.exe (or rigctld on Linux)."
            )
            logger.error(msg)
            raise RigCtldManagerError(msg)

        # Validate rigctld path
        if not self.rigctld_path:
            msg = "Could not locate rigctld executable.\n\n"
            logger.error(msg)
            raise RigCtldManagerError(msg)


        # Try to locate rigctl.exe in same folder as rigctld_path
        rigctl_candidate = os.path.join(os.path.dirname(self.rigctld_path), "rigctl.exe")
        if os.path.isfile(rigctl_candidate):
            self.rigctl_path = rigctl_candidate

        # Validate rigctl
        if not self.rigctl_path:
            msg = (
                f"Could not locate rigctl executable.\n\n"
                f"Expected location: {rigctl_candidate}\n"
                f"Or available via PATH.\n\n"
                "💡 Please ensure Hamlib is installed and rigctl is accessible."
            )
            logger.error(msg)
            raise RigCtldManagerError(msg)

        # Validate rig model ID before proceeding
        self.validate_model_id()

    def _port_is_occupied(self) -> bool:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            result = sock.connect_ex(("127.0.0.1", self.port))
            return result == 0

    def start(self):
        if self.is_running():
            logger.warning("rigctld is already running (via process handle). Skipping start.")
            return

        if self._port_is_occupied():
            logger.warning(f"Port {self.port} is already in use. Assuming rigctld is running.")
            return

        verbosity_flag = "-v" if self.context and self.context.debug_mode else ""

        cmd = [
            self.rigctld_path,
            "-m", str(self.model),
            "-r", self.serial_port,
            "-t", str(self.port)
        ]

        if verbosity_flag:
            cmd.append(verbosity_flag)

        logger.debug(f"Starting rigctld with command: {' '.join(cmd)}")
        try:
            self.process = subprocess.Popen(cmd)

            timeout = 5.0
            interval = 0.2
            waited = 0.0
            while waited < timeout:
                if self._port_is_occupied():
                    break
                time.sleep(interval)
                waited += interval

            if not self._port_is_occupied():
                msg = "rigctld did not start correctly or failed to bind to the port."
                logger.error(msg)
                raise RigCtldManagerError(msg)

            logger.debug(f"rigctld started on port {self.port} with PID {self.process.pid}")

        except Exception as e:
            msg = f"Failed to start rigctld: {e}"
            logger.exception(msg)
            raise RigCtldManagerError(msg) from e

    def stop(self):
        if self.process and self.process.poll() is None:
            logger.info("Terminating rigctld...")
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
                logger.info("rigctld terminated successfully.")
            except subprocess.TimeoutExpired:
                logger.warning("rigctld did not terminate in time. Forcing kill...")
                self.process.kill()
            self.process = None

    def is_running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    def validate_model_id(self) -> None:
        """
        Validates that the rig model exists by running `rigctl -l`.
        If `rigctld_path` is specified, we assume `rigctl` is in the same directory.
        """
        rigctl_bin = "rigctl"

        if self.rigctld_path:
            rigctl_dir = os.path.dirname(self.rigctld_path)
            rigctl_bin = os.path.join(rigctl_dir, "rigctl.exe") if platform.system() == "Windows" else os.path.join(rigctl_dir, "rigctl")

        try:
            result = subprocess.run([rigctl_bin, "-l"], capture_output=True, text=True)
        except FileNotFoundError:
            raise RigCtldManagerError(
                f"rigctl not found at expected location: {rigctl_bin}\n\n"
                f"🔧 Configured rigctld_path in settings.yml:\n    {self.rigctld_path or '(not set)'}\n\n"
                "💡 Please ensure Hamlib is properly installed. If you're using Windows:\n"
                " - Verify that both rigctld.exe and rigctl.exe exist in the same folder\n"
                " - Check your rigctld_path setting under radio in settings.yml\n"
            )
        except Exception as e:
            raise RigCtldManagerError(f"Failed to execute '{rigctl_bin} -l': {e}")

        if result.returncode != 0:
            raise RigCtldManagerError(
                f"'{rigctl_bin} -l' failed with return code {result.returncode}:\n\n{result.stderr.strip()}"
            )

        output = result.stdout.strip()
        if not output:
            raise RigCtldManagerError(
                f"'{rigctl_bin} -l' executed successfully but returned no data.\n"
                "This may indicate a broken Hamlib installation or missing runtime dependencies.\n\n"
                f"🔧 rigctl path: {rigctl_bin}"
            )

        model_lines = output.splitlines()
        model_ids = set()

        for line in model_lines:
            parts = line.strip().split()
            if len(parts) >= 2 and parts[0].isdigit():
                model_ids.add(int(parts[0]))

        if self.model not in model_ids:
            sys.stdout.write(f"\n[!] Invalid rig model ID: {self.model}\n")
            sys.stdout.write("[i] Available rig models:\n\n")
            for line in model_lines:
                if line.strip().startswith("Rig #") or line.strip()[0].isdigit():
                    print("   " + line)
            print()
            sys.stdout.flush()

            raise RigCtldManagerError(
                f"Invalid rig model ID {self.model}. Please select a valid model ID from the list above "
                "and update settings.yml accordingly (radio.rigctld_model)."
            )
                # Extract manufacturer and model name for rig_description

        for line in model_lines:
            parts = line.strip().split()
            if len(parts) >= 3 and parts[0].isdigit() and int(parts[0]) == self.model:
                self.rig_description = f"{parts[1]} {parts[2]}"
                break

    def get_description(self) -> Optional[str]:
        return self.rig_description
