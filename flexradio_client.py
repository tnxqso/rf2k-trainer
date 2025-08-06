import socket
import threading
import re
import os
from radio_interface import BaseRadioClient, BaseRadioError
from loghandler import get_logger

logger = None

class FlexRadioError(BaseRadioError):
    """Custom exception for FlexRadioClient-related errors."""
    pass

class FlexRadioClient(BaseRadioClient):
    def __init__(self, host, port, debug=False):
        global logger
        if logger is None:
            logger = get_logger()
        self.host = host
        self.port = port
        self.sock = None
        self.connected = False
        self.buffer = b""
        self.seq = 1
        self.lock = threading.Lock()
        self.active_slice_id = None
        self.nickname = None
        self.callsign = None
        self.debug = debug or os.getenv("FLEX_DEBUG") == "1"

    def connect(self, timeout=5):
        try:
            self.sock = socket.create_connection((self.host, self.port), timeout=timeout)
            self.connected = True
            logger.info(f"Connected to FlexRadio at {self.host}:{self.port}")
            self._initial_handshake()
        except Exception as e:
            logger.error(f"Connection error: {e}")
            raise FlexRadioError(f"Could not connect to FlexRadio: {e}")

    def _initial_handshake(self):
        seq = self._send_raw_command("sub slice all")
        while True:
            response = self._receive_line()

            if response.startswith("V") or response.startswith("H"):
                continue
            elif response.startswith("S"):
                if "nickname=" in response:
                    fields = response.split()
                    for field in fields:
                        if field.startswith("nickname="):
                            self.nickname = field.split("=", 1)[1]
                        elif field.startswith("callsign="):
                            self.callsign = field.split("=", 1)[1]
                    info = f"Connected radio : {self.nickname}"
                    if self.callsign:
                        info += f", callsign: {self.callsign}"
                    logger.info(info)
                if "slice " in response and "tx=1" in response:
                    slice_match = re.search(r"slice (\d+) .*tx=1", response)
                    if slice_match:
                        self.active_slice_id = slice_match.group(1)
                        logger.info(f"Active TX slice: {self.active_slice_id}")
            elif response.startswith("R"):
                match = re.match(r"^R(\d+)\|(.*)$", response)
                if match and int(match.group(1)) == seq:
                    break

    def send_command(self, command):
        if not self.connected:
            logger.error("send_command called while not connected")
            raise FlexRadioError("TCP socket is not connected")
        with self.lock:
            seq = self.seq
            self.seq += 1
        full_command = f"C{seq}|{command}\n"
        logger.debug(f"[SEND] {full_command.strip()}")
        self.sock.sendall(full_command.encode())

        while True:
            response = self._receive_line()
            if response.startswith(f"R{seq}|"):
                return response

    def _send_raw_command(self, command):
        if not self.connected:
            logger.error("_send_raw_command called while not connected")
            raise FlexRadioError("TCP socket is not connected")
        with self.lock:
            seq = self.seq
            self.seq += 1
        full_command = f"C{seq}|{command}\n"
        logger.debug(f"[SEND] {full_command.strip()}")
        self.sock.sendall(full_command.encode())
        return seq

    def _receive_line(self):
        while b"\n" not in self.buffer:
            chunk = self.sock.recv(4096)
            if not chunk:
                logger.error("Socket closed by FlexRadio")
                raise FlexRadioError("Socket connection closed by FlexRadio")
            self.buffer += chunk
        line, self.buffer = self.buffer.split(b"\n", 1)
        return line.decode().strip()

    def set_mode(self, mode="CW"):
        return self.send_command(f"slice set {self.active_slice_id} mode={mode}")

    def set_frequency(self, freq_mhz=14.070):
        return self.send_command(f"slice tune {self.active_slice_id} {freq_mhz:.4f}")

    def set_tune_power(self, rfpower):
        return self.send_command(f"transmit set tunepower={int(rfpower)}")

    def start_tune(self):
        return self.send_command("transmit tune on")

    def stop_tune(self):
        return self.send_command("transmit tune off")

    def disconnect(self):
        if self.sock:
            self.sock.close()
            self.connected = False
            logger.info("TCP connection closed")
