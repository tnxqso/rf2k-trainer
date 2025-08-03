import yaml
import os
import sys
from loghandler import setup_logging
from typing import Dict, Any, Tuple

# There are modules impoirted in main.py that use the logger, so we need to import them here
# E.g. rf2ks_client, flexradio_comm, rf2ks_logger

PROGRAM_NAME = "RF2K-Trainer"
VERSION = "0.7"
GIT_PROJECT_URL = "https://github.com/tnxqso/rf2k-trainer"

logger = None
tuner_log_path = None
debug_mode = False

def load_yaml_file(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    with open(file_path, "r") as f:
        return yaml.safe_load(f)

def load_rf2k_segment_alignment(file_path: str = "rf2k_segment_alignment.yml") -> Dict[str, Any]:
    data = load_yaml_file(file_path)
    return data["rf2k_segment_alignment"]

def load_combined_band_data(
    settings: Dict[str, Any],
    segment_alignment: Dict[str, Any]
) -> Dict[str, Dict[str, Any]]:
    region = settings.get("defaults", {}).get("iaru_region", 1)
    iaru_file = f"iaru_region_{region}.yml"
    iaru_data = load_yaml_file(iaru_file).get("bands", {})
    band_overrides = settings.get("bands", {})
    combined = {}

    for band, iaru_band_data in iaru_data.items():
        if band not in band_overrides:
            continue  # Skip bands not listed in settings

        override = band_overrides.get(band, {})
        if not override.get("enabled", False):
            continue

        iaru_start = iaru_band_data["band_start"]
        iaru_end = iaru_band_data["band_end"]

        # Use override or fall back to IARU values
        band_start = override.get("band_start", iaru_start)
        band_end = override.get("band_end", iaru_end)

        validate_band_overrides(band, iaru_band_data, override, segment_alignment)

        tune_power = override.get("tune_power", settings.get("defaults", {}).get("tune_power", 10))

        if not (4 <= tune_power <= 39):
            raise ValueError(
                f"[ERROR] tune_power for {band} is out of valid range (4–39 W): {tune_power}"
            )

        seg_cfg = segment_alignment.get(band, {})
        segment_size = seg_cfg.get("segment_size")
        ref_center = seg_cfg.get("first_segment_center")

        combined[band] = {
            "band_start": band_start,
            "band_end": band_end,
            "tune_power": tune_power,
            "segment_size": segment_size,
            "first_segment_center": calculate_first_segment_center(
                band_start=band_start,
                segment_size=segment_size,
                reference_center=ref_center
            )
        }

    return combined

def validate_band_overrides(
    band: str,
    iaru_band_data: Dict[str, Any],
    override: Dict[str, Any],
) -> None:
    """Validate band_start and band_end overrides against IARU defaults."""
    iaru_band_start = iaru_band_data["band_start"]
    iaru_band_end = iaru_band_data["band_end"]
    band_width = iaru_band_end - iaru_band_start

    band_start = override.get("band_start", iaru_band_start)
    band_end = override.get("band_end", iaru_band_end)

    # Ensure band_end > band_start with at least 600 Hz
    if band_end <= band_start + 0.6:
        raise ValueError(
            f"[ERROR] band_end for {band} must be at least 600 Hz above band_start. "
            f"Got band_start: {band_start}, band_end: {band_end}"
        )

    # Sanity check on frequency range (0–60000 kHz)
    for val, label in [(band_start, "band_start"), (band_end, "band_end")]:
        if not (0 <= val <= 60000):
            raise ValueError(
                f"[ERROR] {label} for {band} is out of valid range (0–60000): {val}"
            )

    # Check deviation from IARU band plan
    start_offset = abs(band_start - iaru_band_start)
    end_offset = abs(band_end - iaru_band_end)

    max_start_offset = 0.5 * band_width
    max_end_offset   = 0.5 * band_width

    if start_offset > max_start_offset:
        raise ValueError(
            f"[ERROR] band_start override for {band} deviates too far from IARU default. "
            f"Got {band_start}, expected around {iaru_band_start}"
        )

    if end_offset > max_end_offset:
        raise ValueError(
            f"[ERROR] band_end override for {band} deviates too far from IARU default. "
            f"Got {band_end}, expected around {iaru_band_end}"
        )
    

def calculate_tuning_frequencies(
    band_start: float,
    band_end: float,
    segment_size_khz: float,
    first_segment_center: float
) -> list[int]:
    """
    Calculate RF2K-S tuning points within a band.

    Returns a list of center frequencies (int, kHz) including any necessary
    gap coverage at the start or end of the band.
    """
    segment_size = float(segment_size_khz)
    half_segment = segment_size / 2.0

    tuning_points = []
    current = first_segment_center

    # Add main tuning points (fully covered segments within band)
    while current + half_segment <= band_end:
        if current - half_segment >= band_start:
            tuning_points.append(current)
        current += segment_size

    # Add start gap point if applicable
    first_covered = (
        tuning_points[0] - half_segment if tuning_points
        else first_segment_center - half_segment
    )
    if first_covered > band_start:
        gap_center = (band_start + first_covered) / 2.0
        tuning_points.insert(0, gap_center)

    # Add end gap point if applicable
    last_covered = (
        tuning_points[-1] + half_segment if tuning_points
        else first_segment_center + half_segment
    )
    if last_covered < band_end:
        gap_center = (last_covered + band_end) / 2.0
        tuning_points.append(gap_center)

    return tuning_points


def print_band_info(band_name: str, band_data: dict):
    """
    Pretty-print the band tuning information including extra tuning points, if any.

    Arguments:
        band_name: Name of the band (e.g., "40m")
        band_data: Dictionary with keys:
                   - 'segment_size' (float): size of each tuning segment in kHz
                   - 'band_start' (float): start of band in kHz
                   - 'band_end' (float): end of band in kHz
                   - 'first_segment_center' (int): first known good center frequency in kHz
    """
    segment_size = band_data["segment_size"]
    band_start = band_data["band_start"]
    band_end = band_data["band_end"]
    first_segment_center = band_data["first_segment_center"]

    tuning_freqs = calculate_tuning_frequencies(
        band_start, band_end, segment_size, first_segment_center
    )

    print(f"\n=== Band: {band_name} ===")
    print(f"Segment size: {segment_size:.0f} kHz")
    print(f"Band start: {band_start / 1000:.4f} MHz")
    print(f"Band end: {band_end / 1000:.4f} MHz")
    print(f"Band width: {band_end - band_start:.1f} kHz")
    print(f"Number of tuning points: {len(tuning_freqs)}")
    print("Tuning frequencies (MHz):")

    freq_lines = []
    for f in tuning_freqs:
        freq_lines.append(f"{f / 1000:.4f}")

    print("  " + ", ".join(freq_lines))

def main():
    global logger, tuner_log_path

    args = [arg.lower() for arg in sys.argv[1:]]
    debug_mode = "--debug" in args
    info_mode = "info" in args
    help_mode = "-h" in args or "--help" in args

    if help_mode:
        print("""
Usage: python main.py [--debug] [--clear-logs] [band1 band2 ... | info]

Arguments:
  --debug        Enables verbose debug logging
  --clear-logs   Deletes old log files on startup
  info           Show calculated tuning segments for all bands
  <band>         One or more bands to process, e.g. '60' or '60m'

If no arguments are given, all enabled bands will be tuned interactively.
""")
        return

    if info_mode:
        config = load_yaml_file("settings.yml")
        segment_config = load_rf2k_segment_alignment("rf2k_segment_alignment.yml")
        bands = load_combined_band_data(config, segment_config)
        print(f"{PROGRAM_NAME} - v{VERSION} - Band Information")

        for band_name, band_data in bands.items():
            if band_name not in segment_config:
                logger.error(f"[ERROR] No RF2K segment alignment defined for band: {band_name}")
                raise ValueError(f"[ERROR] No RF2K segment alignment defined for band: {band_name}")

            print_band_info(band_name, band_data)

        return

    # Setup logging only in interactive or tuning mode
    clear_old = "--clear-logs" in args or input("Do you want to delete old log files? (y/n): ").strip().lower() == 'y'
    logger, tuner_log_path = setup_logging(log_dir="logs", clear_old=clear_old, debug=debug_mode)

    # ✅ Logger is now initialized — safe to import modules that use it
    from flexradio_comm import FlexRadioClient
    from rf2ks_client import RF2KSClient
    from rf2ks_logger import log_tuner_data

    logger.info(f"""
    =================================================================
    {PROGRAM_NAME} - v{VERSION}
    Sequential HF Band Tuning Utility for RF2K-S Amplifiers
    Github repo: {GIT_PROJECT_URL}
    =================================================================
    """)

    config = load_yaml_file("settings.yml")
    segment_config = load_rf2k_segment_alignment("rf2k_segment_alignment.yml")
    bands = load_combined_band_data(config, segment_config)
    radio_settings = config.get("flexradio", {})
    amp_settings = config.get("rf2k_s", {})

    rf2ks_url = f"http://{amp_settings.get('host')}:{amp_settings.get('port')}"

    selected_bands = {arg if arg.endswith("m") else f"{arg}m"
                      for arg in args
                      if arg.isdigit() or arg.endswith("m")}

    if selected_bands:
        invalid = [b for b in selected_bands if b not in bands]
        if invalid:
            logger.error(f"[ERROR] The following bands were not found or not enabled: {', '.join(invalid)}")
            return
        bands = {k: v for k, v in bands.items() if k in selected_bands}

    host = radio_settings.get("host", "localhost")
    port = radio_settings.get("port", 4992)
    logger.info(f"\nConnecting to FlexRadio at {host}:{port}...")

    try:
        client = FlexRadioClient(host, port)
        client.connect()
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return

    logger.info("Connection to Flexradio established.\n")

    rf2ks = None
    if amp_settings.get("enabled", False):
        rf2ks = RF2KSClient(config)
        rf2ks.fetch_info()
        rf2ks.set_operate_mode("STANDBY")
    else:
        logger.warning("[RF2K-S] Amplifier is not enabled, skipping RF2K-S operations.")

    print("""
[INSTRUCTIONS]
Before proceeding with automatic tuning:

1. Ensure your RF2K-S amplifier is **not sleeping**.
2. Confirm that **'Operate' is NOT green** and **'Standby' is red** (we try to enforce STANDBY automatically).
3. During each tune cycle, manually press **'Tune & Store'** on the RF2K-S.
4. When tuning is complete on that frequency, press ENTER to stop.
""")
    input("Press ENTER to continue...")

    client.set_mode("CW")

    for band_name, band_data in bands.items():
        logger.info(f"\n=== Band: {band_name} ===")

        if band_name not in segment_config:
            logger.error(f"[ERROR] No RF2K segment alignment defined for band: {band_name}")
            continue

        segment_size = segment_config[band_name]["segment_size"]
        first_segment_center = segment_config[band_name]["first_segment_center"]
        
        band_start = band_data["band_start"]
        band_end = band_data["band_end"]
        tune_power = band_data["tune_power"]

        tuning_freqs, _ = calculate_tuning_frequencies(
            band_start,
            band_end,
            segment_size,
            first_segment_center
        )

        client.set_tune_power(tune_power)

        for freq in tuning_freqs:
            client.set_frequency(freq / 1000)
            user_input = input(f"\nFrequency {freq / 1000:.4f} MHz on {band_name} band, press ENTER to start tune or 's' to skip: ")
            if user_input.strip().lower() == 's':
                print("  -> Skipped")
                continue

            client.start_tune()
            input("  -> Tuning... press ENTER to stop.")
            client.stop_tune()

            # Log tuner data if RF2K-S is enabled
            if amp_settings.get("enabled", False):
                log_tuner_data(rf2ks_url)

    client.disconnect()


if __name__ == "__main__":
    main()
