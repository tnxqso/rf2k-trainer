import argparse
import math
import os
import platform
import sys
import time
import yaml

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set

from radio_interface import BaseRadioError, BaseRadioClient
from flexradio_client import FlexRadioClient
from rigctl_client import RigctlClient

from rf2ks_client import RF2KSClient, RF2KSClientError
from rf2ks_logger import log_tuner_data
from radio_registry import RADIO_CLIENTS
from rigctld_manager import RigctldManager, RigCtldManagerError


PROGRAM_NAME = "RF2K-Trainer"
VERSION = "0.9.003"
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
    radio_type: Optional[str] = None
    radio_label: Optional[str] = None
    radio_description: Optional[str] = None
    rigctld: Optional[Any] = None

def create_context(
    config: Dict[str, Any],
    segment_config: Dict[str, Any],
    bands_args: List[str],
    logger,
    tuner_log_path,
    debug_mode: bool,
    radio_settings: Dict[str, Any],
    radio_type: str,
    radio_label: str,
    radio_description: Optional[str],
    rigctld: Optional[Any]
) -> AppContext:
    bands = load_combined_band_data(config, segment_config)
    defaults = config.get("defaults", {})
    amp_settings = config.get("rf2k_s", {})
    selected_bands = {
        arg if arg.endswith("m") else f"{arg}m"
        for arg in bands_args
        if arg.isdigit() or arg.endswith("m")
    }

    ctx = AppContext(
        config=config,
        bands=bands,
        rf2ks_url=f"http://{amp_settings.get('host')}:{amp_settings.get('port')}",
        tuner_log_path=tuner_log_path,
        logger=logger,
        debug_mode=debug_mode,
        selected_bands=selected_bands,
        prompt_before_each_tune=defaults.get("prompt_before_each_tune", False),
        use_beep=defaults.get("use_beep", True),
        segment_config=segment_config,
        radio_settings=radio_settings,
        amp_settings=amp_settings,
        radio_type=radio_type,
        radio_label=radio_label,
        radio_description=radio_description,
        rigctld=rigctld
    )

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

def radio_setup(config: dict) -> tuple[dict, str, str, type[BaseRadioClient], Optional[str], Optional[RigctldManager]]:
    radio_settings = config.get("radio", {})
    radio_type = radio_settings.get("type", "flex").lower()

    if radio_type not in RADIO_CLIENTS:
        raise ConfigurationError(
            f"Invalid radio type '{radio_type}'. Valid options: {', '.join(RADIO_CLIENTS.keys())}"
        )

    radio_entry = RADIO_CLIENTS[radio_type]
    radio_label = radio_entry["label"]
    radio_class = radio_entry["class"]

    used_default_port = False
    port = radio_settings.get("port")
    if port is None:
        port = radio_entry["default_port"]
        used_default_port = True

    logger.info(
        f"Radio client initialized: {radio_label} (port {port}{' - default' if used_default_port else ''})"
    )

    radio_description = None
    rigctld = None

    if radio_type == "rigctl":
        if radio_settings.get("auto_start_rigctld", False):
            model = radio_settings.get("model") or radio_settings.get("rigctld_model")
            serial_port = radio_settings.get("serial_port") or radio_settings.get("rigctld_serial_port")
            rigctld_path = radio_settings.get("rigctld_path")

            if model is None or serial_port is None:
                raise ConfigurationError("Missing 'model' or 'serial_port' for rigctl configuration.")

            try:
                rigctld = RigctldManager(
                    model=model,
                    serial_port=serial_port,
                    port=port,
                    rigctld_path=rigctld_path
                )
                rigctld.start()
                radio_description = rigctld.get_description()
            except RigCtldManagerError as e:
                logger.error(f"[FATAL] Error starting rigctld: {e}")
                sys.exit(1)

    elif radio_type == "flex":
        radio_description = "FlexRadio (SmartSDR TCP/IP API)"

    return radio_settings, radio_type, radio_label, radio_class, radio_description, rigctld

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


def print_band_info(band_name: str, band_data: dict) -> int:
    """
    Pretty-print the band tuning information including extra tuning points, if any.

    Arguments:
        band_name: Name of the band (e.g., "40m")
        band_data: Dictionary with keys:
                   - 'segment_size' (float): size of each tuning segment in kHz
                   - 'band_start' (float): start of band in kHz
                   - 'band_end' (float): end of band in kHz
                   - 'first_segment_center' (int): first known good center frequency in kHz

    Returns:
        int: Number of tuning segments (frequency points)
    """
    segment_size = band_data["segment_size"]
    band_start = band_data["band_start"]
    band_end = band_data["band_end"]
    first_segment_center = band_data["first_segment_center"]

    tuning_freqs = calculate_tuning_frequencies(
        band_start, band_end, segment_size, first_segment_center
    )
    num_segments = len(tuning_freqs)

    print(f"\n=== Band: {band_name} ===")
    print(f"Segment size: {segment_size:.0f} kHz")
    print(f"Band start: {band_start / 1000:.4f} MHz")
    print(f"Band end: {band_end / 1000:.4f} MHz")
    print(f"Band width: {band_end - band_start:.1f} kHz")
    print(f"Number of tuning points: {num_segments}")
    print("Tuning frequencies (MHz):")
    print("  " + ", ".join(f"{f / 1000:.4f}" for f in tuning_freqs))

    return num_segments

def setup_rigctld_if_needed(settings) -> Optional[RigctldManager]:
    """
    Conditionally start rigctld based on settings.
    Returns the RigctldManager instance (if started), or None otherwise.
    """
    if settings.radio.type != "rigctl":
        return None

    rig_model = getattr(settings.radio, "model", None)
    rig_serial_port = getattr(settings.radio, "serial_port", None)

    if rig_model is None or rig_serial_port is None:
        raise ValueError("You must define 'model' and 'serial_port' in the radio section when using rigctl.")

    manager = RigctldManager(
        model=rig_model,
        serial_port=rig_serial_port,
        port=settings.radio.port
    )
    manager.start()
    return manager


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
    print(f"  - Type:  {ctx.radio_type}")
    print(f"  - Label: {ctx.radio_label}")
    print(f"  - Desc:  {ctx.radio_description or 'N/A'}")
    print(f"  - Host:  {ctx.radio_settings.get('host')}")
    print(f"  - Port:  {ctx.radio_settings.get('port')}\n")

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

    input("\n  Press ENTER to continue...")
    print("\n" + "=" * 112)
    print("⚠️  IMPORTANT SAFETY NOTICE:")
    print("During the tuning process, your radio will be instructed to change frequency and transmit (TUNE mode).")
    print("This is expected behavior during a tuning step.")

    print("\nHOWEVER, if the program is interrupted unexpectedly (e.g., user aborts, network failure, or crash),")
    print("the radio may remain in transmit (TX) mode unless manually stopped.")
    print("Always verify that the radio is no longer transmitting if the program exits abnormally.")
    print("=" * 112)

    if "rigctl" in ctx.radio_label.lower():
        print("\n" + "=" * 112)
        print("⚠️  IMPORTANT NOTICE FOR RIGCTL USERS")
        print()
        print("Your radio is controlled via rigctl, which does NOT support setting TX power levels programmatically.")
        print("This means it is YOUR responsibility to manually configure the radio's output power BEFORE tuning.")
        print()
        print("✅ The RF2K-S amplifier requires tuning power between **4 and 39 watts**.")
        print("👉 We strongly recommend setting your radio to **13 watts** – a safe and effective level for tuning.")
        print()
        print("⚠️  Transmitting above 39 watts during tuning can cause immediate and permanent damage to the amplifier.")
        print("⚠️  Such damage is NOT covered by any warranty.")
        print()
        print("🔍 Please double-check your TX power settings now before proceeding.")
        print("=" * 112)


    input("\n  Press ENTER to continue...")

def run_tuning_loop(radio_client: FlexRadioClient, ctx: AppContext):
    """
    Execute tuning loop per band and frequency, with logging and user prompts.
    """

    start_time = time.time()
    total_segments = 0

    radio_client.set_mode(mode="CW", width=400)

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

        radio_client.set_tune_power(tune_power)

        for freq in tuning_freqs:
            radio_client.set_frequency(freq / 1000)

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

            radio_client.start_tune()

            beep(ctx.use_beep)
            input(
                "\n  → The radio is now tune transmitting on the selected frequency.\n"
                "    Tune your RF2K-S amplifier (press 'Tune & Store' or make a manual tune and store it).\n"
                "    Once tuning is on RF2K-S is complete, press ENTER to continue..."
            )
            radio_client.stop_tune()
            total_segments += 1

            print()
            countdown(2, "    →  Waiting for RF2K-S to store tuning data")

            # Log tuner data if RF2K-S is enabled
            if ctx.amp_settings.get("enabled", False):
                log_tuner_data(ctx.rf2ks_url)

        elapsed = time.time() - start_time
        avg_per_segment = elapsed / total_segments if total_segments else 0

        print("\n=== Summary ===")
        print(f"  Bands tuned       : {len(ctx.bands)}")
        print(f"  Total segments    : {total_segments}")
        print(f"  Total duration    : {elapsed:.1f} seconds")
        print(f"  Avg time/segment  : {avg_per_segment:.2f} seconds")
        print("\nDone.\n")


    radio_client.disconnect()


def main():
    global logger
    parser = argparse.ArgumentParser(description="RF2K-Trainer: Tune RF2K-S amplifier by band")
    parser.add_argument("bands", nargs="*", help="Bands to tune, e.g. 20m 40m or 20 40")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--clear-logs", action="store_true", help="Delete old log files and exit")
    parser.add_argument("--info", action="store_true", help="Show band tuning information and exit")
    args = parser.parse_args()

    global debug_mode
    debug_mode = args.debug

    if args.clear_logs:
        from loghandler import clear_old_logs
        clear_old_logs("logs")
        sys.exit(0)

    # Load configuration and segment alignment data
    config = load_yaml_file("settings.yml")
    segment_config = load_rf2k_segment_alignment("rf2k_segment_alignment.yml")

    # Prompt to clear logs if not using --info
    response = "n"
    if not args.info:
        response = input("Do you want to delete old log files? (y/N): ").strip().lower() or "n"

    clear_old = args.clear_logs or response == "y"

    from loghandler import setup_logging
    logger, tuner_log_path = setup_logging(log_dir="logs", clear_old=clear_old, debug=debug_mode)

    # Lazy-initialize radio-related values to None
    radio_settings = {}
    radio_type = None
    radio_label = None
    radio_description = None
    radio_class = None
    rigctld = None

    if not args.info:
        # Only initialize radio if not in info mode
        radio_settings, radio_type, radio_label, radio_class, radio_description, rigctld = radio_setup(config)
        logger.info(f"Radio description: {radio_description}")

    # Context must be created in both info and tuning modes
    ctx = create_context(
        config=config,
        segment_config=segment_config,
        bands_args=args.bands,
        logger=logger,
        tuner_log_path=tuner_log_path,
        debug_mode=debug_mode,
        radio_settings=radio_settings,
        radio_type=radio_type,
        radio_label=radio_label,
        radio_description=radio_description,
        rigctld=rigctld
    )

    logger.debug("Logger is initialized")

    if args.info:
        # Display only band tuning information
        print(f"{PROGRAM_NAME} - v{VERSION} - Band Information")

        total_segments = 0
        for band_name, band_data in ctx.bands.items():
            total_segments += print_band_info(band_name, band_data)

        est_seconds = total_segments * 12
        minutes, seconds = divmod(est_seconds, 60)

        print("\n===============================================")
        print(f"Total tuning segments: {total_segments}")
        print(f"Estimated total tuning time: {minutes} min {seconds} sec")
        print("===============================================")
        return

    validate_all_tune_power(ctx)

    # Start banner
    logger.info(f"""
    =================================================================
    {PROGRAM_NAME} - v{VERSION}
    Sequential HF Band Tuning Utility for RF2K-S Amplifiers
    Github repo: {GIT_PROJECT_URL}
    =================================================================
    """)

    # Radio client setup and connect
    logger.info(f"\nConnecting to {ctx.radio_label} at {ctx.radio_settings['host']}:{ctx.radio_settings['port']}...")
    radio_client = radio_class(ctx.radio_settings["host"], ctx.radio_settings["port"])

    try:
        radio_client.connect()
    except Exception as e:
        logger.error(f"Connection to {ctx.radio_label} failed: {e}")
        return

    logger.info(f"Connection to {ctx.radio_label} established.\n")

    # RF2K-S amplifier setup
    rf2ks = None
    if ctx.amp_settings.get("enabled", False):
        rf2ks = RF2KSClient(ctx.config)
        rf2ks.fetch_info()
        rf2ks.set_operate_mode("STANDBY")
    else:
        logger.warning("[RF2K-S] Amplifier is not enabled, skipping RF2K-S operations.")

    show_instructions(ctx)

    run_tuning_loop(radio_client, ctx)


if __name__ == "__main__":
    try:
        main()
    except RF2KSClientError as e:
        logger.error(f"[FATAL] RF2K-S communication failed: {e}")
        sys.exit(1)
    except BaseRadioError as e:
        logger.error(f"[FATAL] Radio communication failed: {e}")
        sys.exit(1)
    except ConfigurationError as e:
        logger.error(f"[CONFIG ERROR] {e}")
        sys.exit(1)
    except RigCtldManagerError as e:
        logger.error(f"[FATAL] rigctld startup failed: {e}")
        sys.exit(1)
    except Exception as e:
        logger.exception("[FATAL] Unexpected error occurred")
        sys.exit(1)
