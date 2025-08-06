# radio_interface.py
from abc import ABC, abstractmethod

class BaseRadioError(Exception):
    """Generic radio communication error (superclass for all rig errors)."""
    pass

class BaseRadioClient(ABC):
    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def set_mode(self, mode: str): ...

    @abstractmethod
    def set_frequency(self, freq_mhz: float): ...

    @abstractmethod
    def set_tune_power(self, rfpower: int): ...

    @abstractmethod
    def start_tune(self): ...

    @abstractmethod
    def stop_tune(self): ...

    @abstractmethod
    def disconnect(self): ...
