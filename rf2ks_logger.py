# rf2ks_logger.py

import requests
from loghandler import get_logger, get_tuner_logger

logger = None
tuner_logger = None

_header_written = False

def log_tuner_data(api_url: str):
    """
    Fetches tuner data from RF2K-S and logs it in CSV format using the tuner logger.
    Format: freq_kHz,segment_size_kHz,mode,setup,L_nH,C_pF
    """

    global _header_written, logger, tuner_logger
    if logger is None:
        logger = get_logger()    
    if tuner_logger is None:
        tuner_logger = get_tuner_logger()

    tuner_endpoint = f"{api_url.rstrip('/')}/tuner"

    try:
        response = requests.get(tuner_endpoint, timeout=7)
        response.raise_for_status()
        data = response.json()

        logger.debug("Tuner API response received.")

        required_keys = ("tuned_frequency", "segment_size", "mode", "setup", "L", "C")
        if not all(k in data for k in required_keys):
            freq_kHz = data["tuned_frequency"]["value"]
            logger.info(f"RF2K-S decided to bypass the tuner for the frequency {freq_kHz} kHz.")
            freq_kHz = data["tuned_frequency"]["value"]
            seg_size = data["segment_size"]["value"]
            mode = data["mode"]
            setup = data["setup"]
            L = "N/A"
            C = "N/A"
        else:
            freq_kHz = data["tuned_frequency"]["value"]
            seg_size = data["segment_size"]["value"]
            mode = data["mode"]
            setup = data["setup"]
            L = data["L"]["value"]
            C = data["C"]["value"]

        if not _header_written:
            tuner_logger.info("freq_kHz,segment_size_kHz,mode,setup,L_nH,C_pF")
            _header_written = True

        tuner_logger.info(f"{freq_kHz},{seg_size},{mode},{setup},{L},{C}")

    except Exception as e:
        logger.error(f"[ERROR] Could not fetch tuner data: {e}")
