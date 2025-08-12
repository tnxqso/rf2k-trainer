# radio_interface.py
from abc import ABC, abstractmethod

class BaseRadioError(Exception):
    """Generic radio communication error (superclass for all rig errors)."""
    pass

class BaseRadioClient(ABC):
    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def set_mode(self, mode: str = "CW", width: int = 400): ...

    @abstractmethod
    def set_frequency(self, freq_mhz: float): ...

    @abstractmethod
    def set_drive_power(self, rfpower: int): ...

    @abstractmethod
    def disconnect(self): ...

    @abstractmethod
    def get_ptt(self) -> bool:
        """Return True if the radio is currently transmitting (PTT active), else False."""
    ...
    
    def shutdown(self, restore: bool = True):
        """Optional cleanup for background threads or listeners."""
        pass
