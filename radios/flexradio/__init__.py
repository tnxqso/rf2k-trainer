# radios/flexradio/__init__.py
"""
FlexRadio SmartSDR client package.

Exports:
- FlexRadioClient (high-level client for RF2K-Trainer)
- FlexRadioParser  (line parser for SmartSDR messages)
- FlexRadioTransport (TCP transport with ACK/timeout handling)
"""

from .client import FlexRadioClient, FlexRadioError as FlexRadioClientError
from .parser import FlexParser as FlexRadioParser
from .transport import FlexTransport as FlexRadioTransport

DEFAULT_FLEXRADIO_PORT: int = 4992
__version__ = "1.0.0"

__all__ = [
    "FlexRadioClient",
    "FlexRadioClientError",
    "FlexRadioParser",
    "FlexRadioTransport",
    "DEFAULT_FLEXRADIO_PORT",
    "__version__",
]
