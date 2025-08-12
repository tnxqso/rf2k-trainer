# rigctld_manager.py
import shutil
import subprocess
import time
import sys
import socket
import os
import platform
from typing import Optional, Any, List
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
        """
        Manage lifecycle of a local rigctld instance.

        Notes:
        - Model 1 (Dummy) must NOT receive '-r'; it's not a serial/network resource.
        - On Windows we force IPv4 bind via '-T 127.0.0.1' to avoid ::1-only binding.
        """
        global logger
        if logger is None:
            logger = get_logger()

        self.model = int(model)
        self.serial_port = serial_port
        self.port = int(port)
        self.context = context
        self.rigctld_path = rigctld_path or shutil.which("rigctld")
        self.rigctl_path: Optional[str] = shutil.which("rigctl")
        self.process: Optional[subprocess.Popen] = None
        self.rig_description: Optional[str] = None

        # Validate rigctld path (must be an actual file)
        if not self.rigctld_path or not os.path.isfile(self.rigctld_path):
            msg = (
                "The configured rigctld_path is invalid or not a file:\n"
                f"  {self.rigctld_path}\n\n"
                "💡 Please check that this path is correct and points to rigctld.exe (or rigctld on Linux)."
            )
            logger.error(msg)
            raise RigCtldManagerError(msg)

        # Try to locate rigctl.exe in same folder as rigctld_path (Windows),
        # or 'rigctl' next to 'rigctld' on POSIX.
        rigctl_candidate = (
            os.path.join(os.path.dirname(self.rigctld_path), "rigctl.exe")
            if platform.system() == "Windows"
            else os.path.join(os.path.dirname(self.rigctld_path), "rigctl")
        )
        if os.path.isfile(rigctl_candidate):
            self.rigctl_path = rigctl_candidate

        if not self.rigctl_path:
            msg = (
                "Could not locate rigctl executable.\n\n"
                f"Expected location: {rigctl_candidate}\n"
                "Or available via PATH.\n\n"
                "💡 Please ensure Hamlib is installed and rigctl is accessible."
            )
            logger.error(msg)
            raise RigCtldManagerError(msg)

        # Validate rig model ID before proceeding
        self.validate_model_id()

    # ---------------------------------------------------------------------
    # Internals
    # ---------------------------------------------------------------------

    def _port_is_occupied(self) -> bool:
        """Return True if something is listening on 127.0.0.1:<port>."""
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.5)
            result = sock.connect_ex(("127.0.0.1", self.port))
            return result == 0

    def _build_command(self) -> List[str]:
        """Build the rigctld command line with platform and model nuances."""
        cmd: List[str] = [
            self.rigctld_path,
            "-m", str(self.model),
            "-t", str(self.port),
        ]

        # Force IPv4 bind on Windows to avoid ::1-only listeners
        if platform.system() == "Windows":
            cmd += ["-T", "127.0.0.1"]

        # Only pass -r for real radios (NOT Dummy model 1)
        if self.model != 1 and self.serial_port:
            cmd += ["-r", self.serial_port]

        # Verbosity: go high in debug mode
        if self.context and getattr(self.context, "debug_mode", False):
            cmd += ["-vvvv"]

        return cmd

    # ---------------------------------------------------------------------
    # Public API
    # ---------------------------------------------------------------------

    def start(self):
        """Start rigctld if not already running and the port is free."""
        if self.is_running():
            logger.warning("rigctld is already running, skipping start.")
            return

        if self._port_is_occupied():
            logger.warning(f"Port {self.port} is already in use, assuming rigctld is running.")
            return

        cmd = self._build_command()
        logger.debug(f"Starting rigctld with command: {' '.join(cmd)}")

        try:
            # Start detached child, no stdout/stderr capture to keep behavior identical
            self.process = subprocess.Popen(cmd)

            # Wait for the port to become available
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
        """Terminate the rigctld process if we started it."""
        if self.process and self.process.poll() is None:
            logger.info("Terminating rigctld...")
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
                logger.info("rigctld terminated successfully.")
            except subprocess.TimeoutExpired:
                logger.warning("rigctld did not terminate in time, forcing kill...")
                self.process.kill()
            self.process = None

    def is_running(self) -> bool:
        """Return True if our child process handle is alive."""
        return self.process is not None and self.process.poll() is None

    def validate_model_id(self) -> None:
        """
        Validates that the rig model exists by running `rigctl -l`.
        If `rigctld_path` is specified, assume `rigctl` is in the same directory.
        """
        rigctl_bin = self.rigctl_path or "rigctl"

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
