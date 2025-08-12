import os
import glob
import logging
from datetime import datetime

_logger = None
_tuner_logger = None
tuner_result_file = None

def setup_logging(log_dir="logs", clear_old=False, debug=False):
    global _logger, _tuner_logger, tuner_result_file

    os.makedirs(log_dir, exist_ok=True)

    if clear_old:
        clear_old_logs(log_dir)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    general_log_file = os.path.join(log_dir, f"rf2k-trainer_{timestamp}.log")
    tuner_result_file = os.path.join(log_dir, f"tuning-results_{timestamp}.csv")

    # Main logger
    logging.basicConfig(
        level=logging.DEBUG if debug else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(general_log_file, encoding="utf-8"),
            logging.StreamHandler()
        ]
    )

    _logger = logging.getLogger()
    _logger.debug(f"Log file created: {general_log_file}")
    _logger.debug(f"Tuner results will be written to: {tuner_result_file}")
    _logger.debug(f"Logging level set to: {'DEBUG' if debug else 'INFO'}")

    # Tuner logger (no timestamps, file only)
    _tuner_logger = logging.getLogger("tuner")
    _tuner_logger.setLevel(logging.INFO)

    tuner_handler = logging.FileHandler(tuner_result_file, encoding="utf-8")
    tuner_handler.setFormatter(logging.Formatter('%(message)s'))  # No timestamp
    _tuner_logger.addHandler(tuner_handler)
    _tuner_logger.propagate = False  # Don't send to root logger

    return _logger, tuner_result_file

def get_logger():
    if _logger is None:
        raise RuntimeError("Logger has not been initialized. Call setup_logging() first.")
    return _logger

def get_tuner_logger():
    if _tuner_logger is None:
        raise RuntimeError("Tuner logger not initialized. Call setup_logging() first.")
    return _tuner_logger

def clear_old_logs(log_dir: str):
    if not os.path.exists(log_dir):
        return

    patterns = ["*.log", "*.csv"]
    deleted = 0

    for pattern in patterns:
        for file in glob.glob(os.path.join(log_dir, pattern)):
            try:
                os.remove(file)
                deleted += 1
            except Exception as e:
                print(f"Failed to delete {file}: {e}")

    print(f"Cleared {deleted} old log files.")
