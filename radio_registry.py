# radio_registry.py
from flexradio_client import FlexRadioClient
from rigctl_client import RigctlClient

RADIO_CLIENTS = {
    "flex": {
        "label": "FlexRadio",
        "class": FlexRadioClient,
        "default_port": 4992
    },
    "rigctl": {
        "label": "Radio via rigctl",
        "class": RigctlClient,
        "default_port": 4532
    }
}
