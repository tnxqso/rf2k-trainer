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

    def set_mode(self, mode: str, width: int = 400):
        logger.debug(f"rigctl: Setting mode to {mode.upper()}, width={width}")
        return self.send(f"M {mode.upper()} {width}")

    def set_frequency(self, freq_mhz: float):
        freq_hz = int(freq_mhz * 1_000_000)
        logger.debug(f"rigctl: Setting frequency to {freq_hz} Hz")
        return self.send(f"F {freq_hz}")

    def set_tune_power(self, rfpower: int):
        logger.warning("Tune power not supported via rigctl – skipping.")

    def start_tune(self):
        logger.debug("Sending PTT ON (T 1) to rigctl")
        return self.send("T 1")

    def stop_tune(self):
        logger.debug("Sending PTT OFF (T 0) to rigctl")
        return self.send("T 0")

    def disconnect(self):
        if self.conn:
            self.conn.close()
            logger.info("Disconnected from rigctld")
