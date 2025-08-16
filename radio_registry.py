# radio_registry.py
"""
Registry of available radio backends for RF2K-Trainer.
"""

from typing import Dict, Any

# Nya importvägar efter omstrukturering
from radios.flexradio import FlexRadioClient  # type: ignore

try:
    from radios.rigctl import RigctlClient  # type: ignore
except Exception:
    RigctlClient = None  # type: ignore

RADIO_CLIENTS: Dict[str, Dict[str, Any]] = {
    "flex": {
        "label": "FlexRadio",
        "class": FlexRadioClient,
        "description": "FlexRadio (SmartSDR TCP/IP API)",
        "default_port": 4992,
    },
}

if RigctlClient is not None:
    RADIO_CLIENTS["rigctl"] = {
        "label": "Radio via rigctl",
        "class": RigctlClient,
        "description": "Hamlib rigctld network protocol",
        "default_port": 4532,
    }

__all__ = ["RADIO_CLIENTS"]
