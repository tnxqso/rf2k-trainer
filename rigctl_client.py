# rigctl_client.py
import telnetlib
from radio_interface import BaseRadioClient, BaseRadioError
from loghandler import get_logger

logger = None

class RigctlClient(BaseRadioClient):
    def __init__(self, host="localhost", port=4532):
        global logger
        if logger is None:
            logger = get_logger()
        self.host = host
        self.port = port
        self.conn = None

    def connect(self):
        try:
            self.conn = telnetlib.Telnet(self.host, self.port, timeout=5)
            logger.info(f"Connected to rigctld at {self.host}:{self.port}")
        except Exception as e:
            raise BaseRadioError(f"Failed to connect to rigctld: {e}")

    def send(self, cmd: str) -> str:
        try:
            logger.debug(f"[rigctl] > {cmd}")
            self.conn.write(f"{cmd}\n".encode())
            response = self.conn.read_until(b"\n", timeout=2).decode().strip()
            logger.debug(f"[rigctl] < {response}")
            return response
        except Exception as e:
            raise BaseRadioError(f"Communication error with rigctld: {e}")

    def set_mode(self, mode: str):
        return self.send(f"M {mode.upper()} 2400")

    def set_frequency(self, freq_mhz: float):
        return self.send(f"F {int(freq_mhz * 1_000_000)}")

    def set_tune_power(self, rfpower: int):
        logger.warning("Tune power not supported via rigctl – skipping.")

    def start_tune(self):
        return self.send("T 1")

    def stop_tune(self):
        return self.send("T 0")

    def disconnect(self):
        if self.conn:
            self.conn.close()
            logger.info("Disconnected from rigctld")
