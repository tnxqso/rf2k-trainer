import argparse
import math
import os
import platform
import sys
import time
import yaml

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from flexradio_comm import FlexRadioClient, FlexRadioError
from rf2ks_client import RF2KSClient, RF2KSClientError

PROGRAM_NAME = "RF2K-Trainer"
VERSION = "0.9.1"
GIT_PROJECT_URL = "https://github.com/tnxqso/rf2k-trainer"

logger = None
tuner_log_path = None
debug_mode = False

class ConfigurationError(Exception):
    """Raised when the configuration is invalid or unsafe."""
    pass

@dataclass
class AppContext:
    logger: Any 
    config: Dict[str, Any]
    debug_mode: bool
    prompt_before_each_tune: bool
    use_beep: bool
    tuner_log_path: Optional[str]
    rf2ks_url: str
    segment_config: Dict[str, Any]
    bands: Dict[str, Dict[str, Any]]
    selected_bands: Set[str]
    radio_settings: Dict[str, Any]
    amp_settings: Dict[str, Any]

def create_context(config: Dict[str, Any], segment_config: Dict[str, Any], bands_args: List[str], logger, tuner_log_path, debug_mode: bool) -> AppContext:
    bands = load_combined_band_data(config, segment_config)
    selected_bands = {
        arg if arg.endswith("m") else f"{arg}m"
        for arg in bands_args
        if arg.isdigit() or arg.endswith("m")
    }

    ctx = AppContext(
        config=config,
        bands=bands,
        rf2ks_url=None,  # Will be set below
        tuner_log_path=tuner_log_path,
        logger=logger,
        debug_mode=debug_mode,
        selected_bands=selected_bands,
        prompt_before_each_tune=config.get("defaults", {}).get("prompt_before_each_tune", False),
        use_beep=config.get("defaults", {}).get("use_beep", True),
        segment_config=segment_config,
        radio_settings=config.get("flexradio", {}),
        amp_settings=config.get("rf2k_s", {})
    )

    ctx.rf2ks_url = f"http://{ctx.amp_settings.get('host')}:{ctx.amp_settings.get('port')}"

    if selected_bands:
        invalid = [b for b in selected_bands if b not in bands]
        if invalid:
            logger.error(f"[ERROR] The following bands were not found or not enabled: {', '.join(invalid)}")
            sys.exit(1)
        ctx.bands = {k: v for k, v in bands.items() if k in selected_bands}
        logger.info(f"Selected bands: {', '.join(ctx.bands.keys())}")
    else:
        logger.info(f"Using all enabled bands: {', '.join(ctx.bands.keys())}")

    return ctx

def beep(enabled=True):
    if not enabled:
        return
    if platform.system() == "Windows":
        import winsound
        winsound.Beep(1000, 300)
    else:
        print("\a", end="")

def countdown(seconds: int, message: str = "    →  Tuning next frequency") -> None:
    for i in range(seconds, 0, -1):
        print(f"{message} in {i} second(s)...", end="\r", flush=True)
        time.sleep(1)
    print(" " * 60, end="\r")  # Clear line

def load_yaml_file(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    with open(file_path, "r") as f:
        return yaml.safe_load(f)

def load_rf2k_segment_alignment(file_path: str = "rf2k_segment_alignment.yml") -> Dict[str, Any]:
    data = load_yaml_file(file_path)
    return data["rf2k_segment_alignment"]

def load_combined_band_data(settings: Dict[str, Any], segment_alignment: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    region = settings.get("defaults", {}).get("iaru_region", 1)
    iaru_file = f"iaru_region_{region}.yml"
    iaru_data = load_yaml_file(iaru_file).get("bands", {})
    band_overrides = settings.get("bands", {})
    combined = {}

    for band, iaru_band_data in iaru_data.items():
        if band not in band_overrides:
            continue

        override = band_overrides.get(band, {})
        if not override.get("enabled", False):
            continue

        iaru_start = iaru_band_data["band_start"]
        iaru_end = iaru_band_data["band_end"]

        band_start = override.get("band_start", iaru_start)
        band_end = override.get("band_end", iaru_end)

        validate_band_overrides(band, iaru_band_data, override, segment_alignment)

        tune_power = override.get("tune_power", settings.get("defaults", {}).get("tune_power", 10))

        segment_size = segment_alignment[band]["segment_size"]
        reference_center = segment_alignment[band]["first_segment_center"]

        combined[band] = {
            "band_start": band_start,
            "band_end": band_end,
            "tune_power": tune_power,
            "segment_size": segment_size,
            "first_segment_center": calculate_first_segment_center(
                band_start=band_start,
                segment_size=segment_size,
                reference_center=reference_center
            )
        }

    return combined

def validate_tune_power(band: str, power: float):
    if not (4 <= power <= 39):
        raise ConfigurationError(
            f"tune_power for '{band}' is set to {power} W — "
            f"must be between 4 and 39 W as required by RF2K-S."
        )
    if power < 10:
        logger.warning(
            f"[WARNING] tune_power for '{band}' is only {power} W — "
            f"RF2K-S recommends at least 10 W for accurate tuning."
        )


def validate_all_tune_power(ctx: AppContext):
    global_tune_power = ctx.config.get("defaults", {}).get("tune_power", 0)
    validate_tune_power("global defaults", global_tune_power)

    for band_name, band_cfg in ctx.bands.items():
        if not band_cfg.get("enabled", False):
            continue
        tune_power = band_cfg.get("tune_power", global_tune_power)
        validate_tune_power(band_name, tune_power)

def calculate_first_segment_center(
    band_start: float,
    segment_size: float,
    reference_center: float
) -> float:
    """
    Return the first RF2K-S segment center frequency whose segment START is at or after band_start.

    Arguments:
        band_start: Lower limit of band (kHz)
        segment_size: Segment size in kHz
        reference_center: A known segment center aligned to the RF2K-S segment grid

    Returns:
        First segment center frequency (float)
    """
    if segment_size <= 0:
        raise ValueError("segment_size must be positive")

    half = segment_size / 2.0

    # This is the start of the segment corresponding to the reference center
    ref_start = reference_center - half

    # Step count forward to the first segment whose START is >= band_start
    steps_forward = math.ceil((band_start - ref_start) / segment_size)

    # New segment center
    first_center = reference_center + steps_forward * segment_size

    return round(first_center, 4)

def validate_band_overrides(
    band: str,
    iaru_band_data: Dict[str, Any],
    override: Dict[str, Any],
    segment_alignment: Dict[str, Any]
) -> None:
    """Validate band_start and band_end overrides against IARU defaults."""
    iaru_band_start = iaru_band_data["band_start"]
    iaru_band_end = iaru_band_data["band_end"]
    band_width = iaru_band_end - iaru_band_start

    band_start = override.get("band_start", iaru_band_start)
    band_end = override.get("band_end", iaru_band_end)

    segment_size = segment_alignment.get(band, {}).get("segment_size")
    if not segment_size:
        raise ValueError(f"[ERROR] segment_size missing in rf2k_segment_alignment for band: {band}")

    # Ensure band_end > band_start with at least one segment_size as defined in rf2k_segment_alignment.yml
    if band_end < band_start + segment_size:
        raise ValueError(
            f"[ERROR] band_end for {band} must be at least {segment_size} Hz above band_start. "
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
            tuning_points.append(round(current, 4))
        current += segment_size

    # Add start gap point if applicable
    first_covered = (
        tuning_points[0] - half_segment if tuning_points
        else first_segment_center - half_segment
    )
    if first_covered > band_start:
        gap_center = (band_start + first_covered) / 2.0
        tuning_points.insert(0, round(gap_center, 4))

    # Add end gap point if applicable
    last_covered = (
        tuning_points[-1] + half_segment if tuning_points
        else first_segment_center + half_segment
    )
    if last_covered < band_end:
        gap_center = (last_covered + band_end) / 2.0
        tuning_points.append(round(gap_center, 4))

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

def show_instructions(ctx: AppContext):
    """
    Display clear and detailed instructions for the tuning procedure,
    based on the current configuration context.
    """
    print("\nINSTRUCTIONS:\n")

    if ctx.amp_settings.get("enabled", False):
        print("Your RF2K-S amplifier is configured for programmatic control.")
        print("This means the amplifier will be switched to Standby mode automatically when needed.")
        print("However, due to RF2K-S API limitations, this program cannot switch the amplifier into Tune mode automatically.")
        print("You will be prompted to confirm each tuning step manually.")
        print("After each tuning segment, the amplifier's current L and C values will be queried and logged.\n")
    else:
        print("Programmatic control of your RF2K-S amplifier is DISABLED.")
        print("This means the program cannot switch the amplifier to Standby mode, nor can it read or log the resulting L and C values.\n")

    print("Radio connection settings:")
    print(f"  - Host: {ctx.radio_settings.get('host')}")
    print(f"  - Port: {ctx.radio_settings.get('port')}\n")

    print("Bands selected for tuning:")
    for band in sorted(ctx.selected_bands):
        band_cfg = ctx.bands.get(band)
        if band_cfg:
            print(f"  - {band}: {band_cfg['band_start']} Hz to {band_cfg['band_end']} Hz")
    print()

    if ctx.prompt_before_each_tune:
        print("You will be prompted to press ENTER before each tuning step begins.")
    else:
        print("Tuning will proceed automatically with a countdown between each step.")

    if ctx.use_beep:
        print("An audible beep will indicate when it's time to initiate the Tune function on your amplifier.")

    print("\nBefore starting, please ensure:")
    print("  - Your radio is powered on and connected to the network.")
    print("  - Your RF2K-S amplifier is powered on and connected.")
    print("  - Appropriate antennas are in place for tuning.")
    print("  - You are ready to monitor or interact with the equipment as prompted.")

    print("\n⚠️  IMPORTANT SAFETY NOTICE:")
    print("During the tuning process, your radio will be instructed to change frequency and transmit (TUNE mode).")
    print("This is expected behavior during a tuning step.")
    print("\nHOWEVER, if the program is interrupted unexpectedly (e.g., user aborts, network failure, or crash),")
    print("the radio may remain in transmit (TX) mode unless manually stopped.")
    print("Always verify that the radio is no longer transmitting if the program exits abnormally.")
    print("\nThis is not an issue during normal program completion – the radio will be returned to receive (RX) mode automatically.")


def run_tuning_loop(client: FlexRadioClient, ctx: AppContext):
    """
    Execute tuning loop per band and frequency, with logging and user prompts.
    """
    from rf2ks_logger import log_tuner_data  # Must be imported after logger setup

    client.set_mode("CW")

    for band_name, band_data in ctx.bands.items():
        ctx.logger.info(f"\n=== Band: {band_name} ===")

        band_start = band_data["band_start"]
        band_end = band_data["band_end"]
        tune_power = band_data["tune_power"]
        segment_size = band_data["segment_size"]
        first_segment_center = band_data["first_segment_center"]

        tuning_freqs = calculate_tuning_frequencies(
            band_start,
            band_end,
            segment_size,
            first_segment_center
        )

        client.set_tune_power(tune_power)
        print(f"Setting tune power to {tune_power} W for {band_name} band...")

        for freq in tuning_freqs:
            client.set_frequency(freq / 1000)

            if ctx.prompt_before_each_tune:
                user_input = input(
                    f"\nWe are about to tune frequency {freq / 1000:.4f} MHz on {band_name} band, "
                    "press ENTER to start or 's' to skip: "
                )
                if user_input.strip().lower() == 's':
                    print("  -> Skipped")
                    continue
            else:
                print(f"\nPreparing to tune {freq / 1000:.4f} MHz on {band_name} band...")
                countdown(4)

            client.start_tune()

            beep(ctx.use_beep)
            input(
                "\n  → The radio is now tune transmitting on the selected frequency.\n"
                "    Tune your RF2K-S amplifier (press 'Tune & Store' or make a manual tune and store it).\n"
                "    Once tuning is on RF2K-S is complete, press ENTER to continue..."
            )
            client.stop_tune()
            print()
            countdown(2, "    →  Waiting for RF2K-S to store tuning data")

            # Log tuner data if RF2K-S is enabled
            if ctx.amp_settings.get("enabled", False):
                log_tuner_data(ctx.rf2ks_url)

        print(f"\nDone.\n")

    client.disconnect()


def main():
    global logger
    parser = argparse.ArgumentParser(description="RF2K-Trainer: Tune RF2K-S amplifier by band")
    parser.add_argument("bands", nargs="*", help="Bands to tune, e.g. 20m 40m or 20 40")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--clear-logs", action="store_true", help="Delete old log files on startup")
    parser.add_argument("--info", action="store_true", help="Show band tuning information and exit")
    args = parser.parse_args()

    global debug_mode
    debug_mode = args.debug

    config = load_yaml_file("settings.yml")
    segment_config = load_rf2k_segment_alignment("rf2k_segment_alignment.yml")

    if not args.info:
        response = input("Do you want to delete old log files? (y/N): ").strip().lower() or "n"
    else:
        response = "n"

    clear_old = args.clear_logs or response == 'y'

    from loghandler import setup_logging
    logger, tuner_log_path = setup_logging(log_dir="logs", clear_old=clear_old, debug=debug_mode)

    ctx = create_context(
        config=config,
        segment_config=segment_config,
        bands_args=args.bands,
        logger=logger,
        tuner_log_path=tuner_log_path,
        debug_mode=debug_mode
    )

    logger.info(f"Logger is initialized")
    validate_all_tune_power(ctx)

    if args.info:
        print(f"{PROGRAM_NAME} - v{VERSION} - Band Information")

        for band_name, band_data in ctx.bands.items():
            print_band_info(band_name, band_data)

        return

    logger.info(f"""
    =================================================================
    {PROGRAM_NAME} - v{VERSION}
    Sequential HF Band Tuning Utility for RF2K-S Amplifiers
    Github repo: {GIT_PROJECT_URL}
    =================================================================
    """)

    host = ctx.radio_settings.get("host", "localhost")
    port = ctx.radio_settings.get("port", 4992)
    logger.info(f"\nConnecting to FlexRadio at {host}:{port}...")

    try:
        client = FlexRadioClient(host, port)
        client.connect()
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return

    logger.info("Connection to Flexradio established.\n")

    rf2ks = None
    if ctx.amp_settings.get("enabled", False):
        rf2ks = RF2KSClient(ctx.config)
        rf2ks.fetch_info()
        rf2ks.set_operate_mode("STANDBY")
    else:
        logger.warning("[RF2K-S] Amplifier is not enabled, skipping RF2K-S operations.")

    show_instructions(ctx)


    run_tuning_loop(client, ctx)


if __name__ == "__main__":
    try:
        main()
    except RF2KSClientError as e:
        logger.error(f"[FATAL] RF2K-S communication failed: {e}")
        sys.exit(1)
    except FlexRadioError as e:
        logger.error(f"[FATAL] FlexRadio communication failed: {e}")
        sys.exit(1)
    except ConfigurationError as e:
        logger.error(f"[CONFIG ERROR] {e}")
        sys.exit(1)        
    except Exception as e:
        logger.exception("[FATAL] Unexpected error occurred")
        sys.exit(1)
