import yaml
import os
import sys
from flexradio_comm import FlexRadioClient
from rf2ks_client import RF2KSClient
from typing import Dict, Any, Tuple

PROGRAM_NAME = "RF2K-Trainer"
VERSION = "0.7"
GIT_PROJECT_URL = "https://github.com/tnxqso/rf2k-trainer"

def load_yaml_file(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    with open(file_path, "r") as f:
        return yaml.safe_load(f)


def load_combined_band_data(settings: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
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

        # Always use segment_size from IARU file
        segment_size = iaru_band_data["segment_size"]
        iaru_start = iaru_band_data["band_start"]
        iaru_end = iaru_band_data["band_end"]

        # Use override or fall back to IARU values
        band_start = override.get("band_start", iaru_start)
        band_end = override.get("band_end", iaru_end)

        validate_band_overrides(band, iaru_band_data, override)

        # tune_power from override or default
        tune_power = override.get("tune_power", settings.get("defaults", {}).get("tune_power", 10))

        if not (4 <= tune_power <= 39):
            raise ValueError(
                f"[ERROR] tune_power for {band} is out of valid range (4–39 W): {tune_power}"
            )

        combined[band] = {
            "segment_size": segment_size,
            "band_start": band_start,
            "band_end": band_end,
            "tune_power": tune_power,
        }

    return combined

def validate_band_overrides(
    band: str,
    iaru_band_data: Dict[str, Any],
    override: Dict[str, Any]
) -> None:
    """Validate band_start and band_end overrides against IARU defaults."""
    segment_size = iaru_band_data["segment_size"]
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

    max_start_offset = max(0.1 * band_width, segment_size)       # Allow up to 10% deviation or 1 segment
    max_end_offset   = max(0.5 * band_width, segment_size * 2)   # Allow up to 50% deviation or 2 segments

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
    
    # Ensure band_start is aligned to segment_size steps
    start_offset = band_start - iaru_band_start
    if start_offset % segment_size != 0:
        raise ValueError(
            f"[ERROR] band_start for {band} must be aligned with segment_size steps of {segment_size} kHz.\n"
            f"Got: {band_start}, expected step size from IARU start {iaru_band_start}"
        )

def calculate_mid_segments(band_start: float, band_end: float, segment_size_khz: float) -> Tuple[list, float, bool]:
    segment_size = float(segment_size_khz)
    half_segment = segment_size / 2
    min_gap_for_extra_point = 0.6  # kHz
    start = float(band_start)
    end = float(band_end)

    mid_segments = []
    current = start + half_segment

    while current <= end:
        mid_segments.append(round(current, 4))
        current += segment_size

    extra_point = None
    was_extra_point_added = False
    covered_up_to = mid_segments[-1] + half_segment if mid_segments else start
    untuned_gap = end - covered_up_to

    if untuned_gap >= min_gap_for_extra_point:
        extra_point = round(covered_up_to + untuned_gap / 2, 4)
        mid_segments.append(extra_point)
        was_extra_point_added = True

    return mid_segments, extra_point, was_extra_point_added


def print_band_info(band_name, band_data):
    print(f"\n=== Band: {band_name} ===")
    segment_size = band_data["segment_size"]
    band_start = band_data["band_start"]
    band_end = band_data["band_end"]

    mid_segments, extra_point, was_extra_point_added = calculate_mid_segments(
        band_start, band_end, segment_size
    )

    print(f"Segment size: {segment_size} kHz")
    print(f"Mid segment span: {segment_size / 2:.1f} kHz")
    print(f"Band start: {band_start / 1000:.4f} MHz")
    print(f"Band end: {band_end / 1000:.4f} MHz")
    print(f"Band width: {band_end - band_start:.1f} kHz")
    print(f"Number of segments: {len(mid_segments)}")
    print("Mid segments (MHz):")
    print("  " + ", ".join(f"{f / 1000:.4f}" for f in mid_segments))

    if was_extra_point_added and extra_point is not None:
        print(f"  [!] Added extra tuning point at {extra_point / 1000:.4f} MHz to cover end gap")


def main():

    print(f"""
    =================================================================
    {PROGRAM_NAME} - v{VERSION}
    Sequential HF Band Tuning Utility for RF2K-S Amplifiers
    Github repo: {GIT_PROJECT_URL}
    =================================================================
    """)

    config = load_yaml_file("settings.yml")
    bands = load_combined_band_data(config)
    radio_settings = config.get("flexradio", {})

    args = [arg.lower() for arg in sys.argv[1:]]
    if any(arg in ("-h", "--help") for arg in args):
        print("""
Usage: python main.py [band1 band2 ... | info]

Arguments:
  info           Show calculated tuning segments for all bands
  <band>         One or more bands to process, e.g. '60' or '60m'

If no arguments are given, all enabled bands will be tuned interactively.
""")
        return

    info_mode = "info" in args
    selected_bands = set(arg if arg.endswith("m") else f"{arg}m" for arg in args if arg.isdigit() or arg.endswith("m"))

    if info_mode:
        print("=== Flex Amp Trainer INFO MODE ===")
        for band_name, band_data in bands.items():
            print_band_info(band_name, band_data)
        return

    if selected_bands:
        invalid = [b for b in selected_bands if b not in bands]
        if invalid:
            print(f"[ERROR] The following bands were not found or not enabled: {', '.join(invalid)}")
            return
        bands = {k: v for k, v in bands.items() if k in selected_bands}

    print("=== Flex Amp Trainer INTERACTIVE MODE ===")

    host = radio_settings.get("host", "localhost")
    port = radio_settings.get("port", 4992)
    print(f"\nConnecting to FlexRadio at {host}:{port}...")

    try:
        client = FlexRadioClient(host, port)
        client.connect()
    except Exception as e:
        print(f"Connection failed: {e}")
        return

    print("Connection to Flexradio established.\n")

    amp_settings = config.get("rf2k_s", {})
    rf2ks = None
    if amp_settings.get("enabled", False):
        rf2ks = RF2KSClient(config)
        rf2ks.fetch_info()
        rf2ks.set_operate_mode("STANDBY")
    else:
        print("[RF2K-S] Amplifier is not enabled, skipping RF2K-S operations.")

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
        print(f"\n=== Band: {band_name} ===")

        segment_size = band_data["segment_size"]
        band_start = band_data["band_start"]
        band_end = band_data["band_end"]
        tune_power = band_data["tune_power"]

        mid_segments, _, _ = calculate_mid_segments(band_start, band_end, segment_size)

        client.set_tune_power(tune_power)

        for freq in mid_segments:
            client.set_frequency(freq / 1000)
            user_input = input(f"\nFrequency {freq / 1000:.4f} MHz on {band_name} band, press ENTER to start tune or 's' to skip: ")
            if user_input.strip().lower() == 's':
                print("  -> Skipped")
                continue

            client.start_tune()
            input("  -> Tuning... press ENTER to stop.")
            client.stop_tune()

    client.disconnect()


if __name__ == "__main__":
    main()
