# main.py
import argparse
import math
import os
try:
    from pyfiglet import Figlet
except Exception:
    Figlet = None
    class FontNotFound(Exception):
        pass
import sys
import time
import yaml

from typing import Any, Dict, List, Optional, Tuple, Type

from radio_interface import BaseRadioError, BaseRadioClient
from rf2ks_client import RF2KSClient, RF2KSClientError
from config_validation import validate_rigctl_settings
from radio_registry import RADIO_CLIENTS
from rigctld_manager import RigctldManager, RigCtldManagerError
from band_math import calculate_tuning_frequencies
from tuning_loop import run_tuning_loop
from app_context import AppContext
import updater

# On Windows terminals, force UTF-8 so icons and accents render OK.
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROGRAM_NAME = "RF2K-Trainer"
CURRENT_VERSION = "0.9.315"
GIT_PROJECT_URL = "https://github.com/tnxqso/rf2k-trainer"
AMPLIFIER_NAME = "RF2K-S HF Power Amplifier"

# ANSI colors for terminal output
COLOR_CYAN = "\033[96m"
COLOR_YELLOW = "\033[93m"
COLOR_MAGENTA = "\033[95m"
COLOR_RESET = "\033[0m"

logger = None
tuner_log_path = None
debug_mode = False


class ConfigurationError(Exception):
    """Raised when the configuration is invalid or unsafe."""
    pass

def print_banner_safe(title: str = "RF2K-TRAINER"):
    """Print a nice banner, but never crash if pyfiglet/fonts are missing."""
    if os.getenv("NO_FIGLET") == "1" or Figlet is None:
        print("\n" + title + "\n")
        return
    try:
        for font in ("slant", "standard"):
            try:
                fig = Figlet(font=font, width=120)
                print(fig.renderText(title))
                return
            except Exception:
                continue
        print("\n" + title + "\n")
    except Exception:
        print("\n" + title + "\n")

# -------------------------
# Pretty printing / UX
# -------------------------
def show_banner_and_clear() -> None:
    """Banner at program start (kept slow for fun)."""
    print_banner_safe("RF2K-TRAINER")
    time.sleep(1.2)


def graceful_exit(
    radio_client: Optional[BaseRadioClient] = None,
    restore: bool = True,
    rigctld: Optional[Any] = None,
    exit_code: int = 0,
    show_banner: bool = True,
) -> None:
    """
    Cleanly shut down resources and exit the program.

    - Stop rigctld if we started it.
    - Ask radio client to shutdown(restore=...) if available, else disconnect().
    - Print a nice farewell banner.
    - Exit process with exit_code.
    """
    # 1) Stop rigctld only if we started it
    try:
        if rigctld and getattr(rigctld, "auto_started", True) and hasattr(rigctld, "stop"):
            rigctld.stop()
    except Exception as e:
        try:
            logger and logger.debug(f"rigctld stop raised: {e}")
        except Exception:
            pass

    # 2) Restore radio and disconnect
    try:
        if radio_client:
            if hasattr(radio_client, "shutdown"):
                radio_client.shutdown(restore=restore)
            else:
                radio_client.disconnect()
    except Exception as e:
        try:
            logger and logger.debug(f"Radio shutdown raised: {e}")
        except Exception:
            pass

    # 3) Friendly goodbye
    if show_banner:
        print("\n" + "=" * 80)
        print(f"{COLOR_YELLOW}📡  RF2K-TRAINER session completed.{COLOR_RESET}")
        print(f"{COLOR_CYAN}🙏  Thanks for using the trainer – may your SWR be low and your signal strong!{COLOR_RESET}")
        print(f"{COLOR_MAGENTA}🎙️  73 and good DX – de RF2K-TRAINER ✨{COLOR_RESET}")
        print("=" * 80 + "\n")

        # Safe banner (never crashes on missing figlet/font)
        try:
            print(COLOR_CYAN, end="")
            print_banner_safe("73 de RF2K-TRAINER")
        finally:
            print(COLOR_RESET, end="")


    sys.exit(exit_code)


# -------------------------
# Config loaders / validators
# -------------------------
def load_yaml_file(file_path: str) -> Dict[str, Any]:
    """Load a small YAML file into a dict; raise if not found."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Configuration file not found: {file_path}")
    with open(file_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_rf2k_segment_alignment(file_path: str = "rf2k_segment_alignment.yml") -> Dict[str, Any]:
    """Load the RF2K-S segment alignment table."""
    data = load_yaml_file(file_path)
    return data["rf2k_segment_alignment"]


def calculate_first_segment_center(
    band_start: float,
    segment_size: float,
    reference_center: float
) -> float:
    """
    Return the first RF2K-S segment center whose segment START is at or after band_start.
    """
    if segment_size <= 0:
        raise ValueError("segment_size must be positive")

    half = segment_size / 2.0
    ref_start = reference_center - half
    steps_forward = math.ceil((band_start - ref_start) / segment_size)
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

    # Ensure band_end > band_start with at least one segment_size
    if band_end < band_start + segment_size:
        raise ValueError(
            f"[ERROR] band_end for {band} must be at least {segment_size} Hz above band_start. "
            f"Got band_start: {band_start}, band_end: {band_end}"
        )

    # Sanity check (0–60000 kHz)
    for val, label in [(band_start, "band_start"), (band_end, "band_end")]:
        if not (0 <= val <= 60000):
            raise ValueError(
                f"[ERROR] {label} for {band} is out of valid range (0–60000): {val}"
            )

    # Check deviation from IARU band plan
    start_offset = abs(band_start - iaru_band_start)
    end_offset = abs(band_end - iaru_band_end)

    max_start_offset = 0.5 * band_width
    max_end_offset = 0.5 * band_width

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


def load_combined_band_data(settings: Dict[str, Any], segment_alignment: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Merge IARU band limits with user overrides and segment alignment table."""
    region = settings.get("defaults", {}).get("iaru_region", 1)
    iaru_file = f"iaru_region_{region}.yml"
    iaru_data = load_yaml_file(iaru_file).get("bands", {})
    band_overrides = settings.get("bands", {})
    combined: Dict[str, Dict[str, Any]] = {}

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

        drive_power = override.get("drive_power", settings.get("defaults", {}).get("drive_power", 13))

        segment_size = segment_alignment[band]["segment_size"]
        reference_center = segment_alignment[band]["first_segment_center"]

        combined[band] = {
            "band_start": band_start,
            "band_end": band_end,
            "drive_power": drive_power,
            "segment_size": segment_size,
            "first_segment_center": calculate_first_segment_center(
                band_start=band_start,
                segment_size=segment_size,
                reference_center=reference_center
            )
        }

    return combined


def validate_drive_power(band: str, power: float) -> None:
    """RF2K-S tuner needs 4–39 W; recommend >= 10 W."""
    if not (4 <= power <= 39):
        raise ConfigurationError(
            f"drive_power for '{band}' is set to {power} W — must be between 4 and 39 W as required by RF2K-S."
        )
    if power < 10:
        logger and logger.warning(
            f"[WARNING] drive_power for '{band}' is only {power} W — {AMPLIFIER_NAME} recommends at least 10 W for accurate tuning."
        )


def validate_all_drive_power(ctx: AppContext) -> None:
    """Run drive-power checks across defaults and all enabled bands."""
    global_drive_power = ctx.config.get("defaults", {}).get("drive_power", 13)
    validate_drive_power("global defaults", global_drive_power)

    for band_name, band_cfg in ctx.bands.items():
        drive_power = band_cfg.get("drive_power", global_drive_power)
        validate_drive_power(band_name, drive_power)


def print_band_info(band_name: str, band_data: dict, ctx: AppContext) -> int:
    """Pretty-print band tuning information and return # of points."""
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


def radio_setup(config: dict) -> Tuple[dict, str, str, Type[BaseRadioClient], Optional[str], Optional[RigctldManager]]:
    """
    Resolve radio class + runtime description, and (optionally) start rigctld.

    Returns:
        (radio_settings, radio_type, radio_label, radio_class, radio_description, rigctld_manager_or_None)
    """
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

    radio_description: Optional[str] = None
    rigctld: Optional[RigctldManager] = None

    if radio_type == "rigctl":
        auto_start = radio_settings.get("auto_start_rigctld", False)
        if auto_start:
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
                # Prefer a sane description; some rigs might return quirky names
                desc = rigctld.get_description() or "Hamlib rigctld"
                if "sigfox" in desc.lower():
                    desc = "Hamlib rigctld"
                radio_description = desc
            except RigCtldManagerError as e:
                logger.error(f"[FATAL] Error starting rigctld: {e}")
                sys.exit(1)
        else:
            # Externally managed rigctld: ensure it's reachable now
            RigctldManager.ensure_external_available(
                rigctld_host=radio_settings.get("host", "localhost"),
                port=port,
                model=radio_settings.get("model") or radio_settings.get("rigctld_model"),
                serial_port=radio_settings.get("serial_port") or radio_settings.get("rigctld_serial_port"),
                rigctld_path=radio_settings.get("rigctld_path"),
            )
            radio_description = "Hamlib rigctld (external)"

    elif radio_type == "flex":
        radio_description = "FlexRadio (SmartSDR TCP/IP API)"

    return radio_settings, radio_type, radio_label, radio_class, radio_description, rigctld


def create_context(
    config: Dict[str, Any],
    segment_config: Dict[str, Any],
    bands_args: List[str],
    logger_in,
    tuner_log_path_in,
    debug_mode_in: bool,
    radio_settings: Dict[str, Any],
    radio_type: str,
    radio_label: str,
    radio_description: Optional[str],
    rigctld: Optional[Any]
) -> AppContext:
    """Build a run context from config and runtime choices."""
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
        tuner_log_path=tuner_log_path_in,
        logger=logger_in,
        debug_mode=debug_mode_in,
        selected_bands=selected_bands,
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
            logger_in.error(f"[ERROR] The following bands were not found or not enabled: {', '.join(invalid)}")
            sys.exit(1)
        ctx.bands = {k: v for k, v in bands.items() if k in selected_bands}
        logger_in.info(f"Selected bands: {', '.join(ctx.bands.keys())}")
    else:
        logger_in.info(f"Using all enabled bands: {', '.join(ctx.bands.keys())}")

    return ctx


def show_instructions(ctx: AppContext) -> None:
    """Operator guidance for the current session."""
    print("\nINFO:\n")

    if ctx.amp_settings.get("enabled", False):
        print(f"{AMPLIFIER_NAME} is ENABLED for programmatic control.\n")
        print("  → The amplifier will be automatically switched to **Standby mode** during tuning.")
        print("  → After each segment tune, the amplifier's current L and C values")
        print("    will be **read and logged** for future reference.\n")
    else:
        print(f"{AMPLIFIER_NAME} is NOT under programmatic control.\n")
        print("  → You must manually switch the amplifier to Standby mode before each tune.")
        print("  → The program will NOT be able to read or log the L and C tuning values.\n")

    print("Radio connection settings:")
    print(f"  - Type:  {ctx.radio_type}")
    print(f"  - Label: {ctx.radio_label}")
    print(f"  - Desc:  {ctx.radio_description or 'N/A'}")
    print(f"  - Host:  {ctx.radio_settings.get('host')}")
    print(f"  - Port:  {ctx.radio_settings.get('port')}\n")

    def _fmt_freq_mhz(khz: float) -> str:
        return f"{khz / 1000:.4f} MHz"

    print("Bands selected for tuning:")
    for band in sorted(ctx.selected_bands) if ctx.selected_bands else sorted(ctx.bands.keys()):
        band_cfg = ctx.bands.get(band)
        if band_cfg:
            start_txt = _fmt_freq_mhz(band_cfg['band_start'])
            end_txt   = _fmt_freq_mhz(band_cfg['band_end'])
            print(f"  - {band}: {start_txt} to {end_txt}")
    print()

    if ctx.use_beep:
        print(f"\n🔔 A short **beep** will let you know when to **key your transmitter** to generate a steady carrier.")
    print("\n🛠️  Before you begin, double-check the following:\n")
    print("  ✅ The radio is powered on and properly connected to the network.")
    print(f"  ✅ Your {AMPLIFIER_NAME} is powered on and accessible.")
    print("  ✅ Antennas are connected correctly and are suitable for tuning.")
    print("  ✅ The radio must transmit a steady HF carrier during amplifier tuning:")
    print("     • CW with key down (manually or keyer)")
    print("     • RTTY/AM carrier with PTT held")
    print("     • Radio’s built-in TUNE carrier")
    print("     ⚠️  Keep the carrier active during the entire tuning step.")
    print("  🧭 Follow amateur radio best practice: listen first, avoid QSO/beacons, tune on a clear frequency.\n")
    print("=" * 112)

    if "rigctl" in (ctx.radio_label or "").lower():
        print("\n" + "=" * 112)
        print("⚠️  RIGCTL WARNING – Manual TX Power Required")
        print("\nYour radio is controlled via *rigctl*, which does **not** allow this program to set TX power levels.")
        print("You must configure the **transmit power manually** before proceeding.\n")
        print(f"✅ Recommended drive power: **13 watts**")
        print(f"✅ Safe range for {AMPLIFIER_NAME}: **4 to 39 watts**\n")
        print(f"❌ Exceeding 39 watts may cause **irreversible damage** to your {AMPLIFIER_NAME}.")
        print("❌ Such damage is **not covered by warranty**.\n")
        print("🔍 Please verify your TX power setting now before you continue.")
        print("=" * 112)

    input("\n  Press ENTER to continue...")


def main() -> None:
    show_banner_and_clear()

    global logger
    parser = argparse.ArgumentParser(description=f"RF2K-Trainer: Tune {AMPLIFIER_NAME} by band")
    parser.add_argument("bands", nargs="*", help="Bands to tune, e.g. 20m 40m or 20 40")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--clear-logs", action="store_true", help="Delete old log files and exit")
    parser.add_argument("--info", action="store_true", help="Show band tuning information and exit")
    # Update checks
    if os.name == "nt":
        parser.add_argument(
            "--check-updates",
            action="store_true",
            help="Check for a newer release and offer to download & install",
        )
        parser.add_argument(
            "--check-updates-auto",
            action="store_true",
            help="Non-interactive update check (exit code: 0 up-to-date, 1 newer available, 2 error)",
        )

    args = parser.parse_args()

    global debug_mode
    debug_mode = args.debug

    # --check-updates          -> interactive install (ask Y/n, installer runs silently)
    # --check-updates-auto     -> check only (no download/install, exit code only)

    if args.check_updates or args.check_updates_auto:
        if os.name != "nt":
            print("[update] Update check is only available on Windows builds.")
            sys.exit(0)

        mode = "check" if args.check_updates_auto else "interactive"
        rc = updater.check_for_updates(CURRENT_VERSION, mode=mode)
        # If the installer was launched, updater will os._exit(111) and we never reach here.
        # In "check" mode rc is 0 (up-to-date), 1 (newer available), or 2 (error). Normalize None -> 0.
        sys.exit(rc if isinstance(rc, int) else 0)

    # --clear-logs: purge old logs and exit without running anything else
    if args.clear_logs:
        from loghandler import clear_old_logs
        clear_old_logs("logs")
        print("[logs] Old logs deleted.")
        sys.exit(0)

    # Load configuration and segment alignment data
    config = load_yaml_file("settings.yml")
    segment_config = load_rf2k_segment_alignment("rf2k_segment_alignment.yml")

    # Optional prompt to clear logs unless --info
    response = "n"
    if not args.info:
        response = input("Do you want to delete old log files? (y/N): ").strip().lower() or "n"
    clear_old = args.clear_logs or response == "y"

    from loghandler import setup_logging
    logger_local, tuner_log_path_local = setup_logging(log_dir="logs", clear_old=clear_old, debug=debug_mode)

    # Bind globals used by helper funcs
    global tuner_log_path
    tuner_log_path = tuner_log_path_local
    global logger
    logger = logger_local

    # Radio (only if not --info)
    radio_settings: Dict[str, Any] = {}
    radio_type: Optional[str] = None
    radio_label: Optional[str] = None
    radio_description: Optional[str] = None
    radio_class: Optional[Type[BaseRadioClient]] = None
    rigctld: Optional[RigctldManager] = None

    if not args.info:
        radio_settings, radio_type, radio_label, radio_class, radio_description, rigctld = radio_setup(config)
        logger.info(f"Radio description: {radio_description}")

    # Build context (works for both --info and full run)
    ctx = create_context(
        config=config,
        segment_config=segment_config,
        bands_args=args.bands,
        logger_in=logger,
        tuner_log_path_in=tuner_log_path,
        debug_mode_in=debug_mode,
        radio_settings=radio_settings,
        radio_type=radio_type or "",
        radio_label=radio_label or "",
        radio_description=radio_description,
        rigctld=rigctld
    )

    logger.debug("Logger is initialized")
    restore = bool(config.get("defaults", {}).get("restore_state", True))

    # --info mode: just print band data and exit
    if args.info:
        print(f"{PROGRAM_NAME} - v{CURRENT_VERSION} - Band Information")
        total_segments = 0
        for band_name, band_data in ctx.bands.items():
            total_segments += print_band_info(band_name, band_data, ctx)

        est_seconds = total_segments * 12
        minutes, seconds = divmod(est_seconds, 60)

        print("\n===============================================")
        print(f"Total tuning segments: {total_segments}")
        print(f"Estimated total tuning time: {minutes} min {seconds} sec")
        print("===============================================")
        return

    validate_all_drive_power(ctx)

    # Start banner
    logger.info(f"""
    =================================================================
    {PROGRAM_NAME} - v{CURRENT_VERSION}
    Sequential HF Band Tuning Utility for RF2K-S Amplifiers
    Github repo: {GIT_PROJECT_URL}
    =================================================================
    """)

    radio_client: Optional[BaseRadioClient] = None
    rf2ks: Optional[RF2KSClient] = None  # <-- ensure defined even when PA is disabled

    try:
        # Radio client setup and connect
        logger.info(f"\nConnecting to {ctx.radio_label} at {ctx.radio_settings.get('host')}:{ctx.radio_settings.get('port')}...")
        assert radio_class is not None, "radio_class not resolved"
        radio_client = radio_class(ctx.radio_settings.get("host"), ctx.radio_settings.get("port"))
        validate_rigctl_settings(ctx, logger)
        radio_client.connect()

        # One-time PTT capability detection (rigctl)
        if ctx.radio_type == "rigctl":
            if "dummy" in (ctx.radio_description or "").lower():
                setattr(radio_client, "ptt_supported", False)
                logger.debug("[PTT] Dummy rig detected -> manual mode for this session.")
            else:
                try:
                    _ = radio_client.get_ptt()
                    logger.debug(f"[PTT] capability: {getattr(radio_client, 'ptt_supported', True)}")
                except BaseRadioError as e:
                    logger.debug(f"[PTT] initial probe failed (ignored): {e}")

        # Amplifier setup (optional)
        if ctx.amp_settings.get("enabled", False):
            rf2ks = RF2KSClient(ctx.config)
            rf2ks.fetch_info()
            rf2ks.set_operate_mode("STANDBY")
        else:
            logger.warning(f"{AMPLIFIER_NAME} is not enabled, skipping {AMPLIFIER_NAME} operations.")

        show_instructions(ctx)
        # Safe even if rf2ks is None
        run_tuning_loop(radio_client, rf2ks, ctx)

    finally:
        # Always clean up, restore state and exit nicely
        graceful_exit(radio_client=radio_client, restore=restore, rigctld=rigctld)


if __name__ == "__main__":
    try:
        main()
    except RF2KSClientError as e:
        logger and logger.error(f"[FATAL] {AMPLIFIER_NAME} communication failed: {e}")
        sys.exit(1)
    except BaseRadioError as e:
        logger and logger.error(f"[FATAL] Radio communication failed: {e}")
        sys.exit(1)
    except ConfigurationError as e:
        logger and logger.error(f"[CONFIG ERROR] {e}")
        sys.exit(1)
    except RigCtldManagerError as e:
        logger and logger.error(f"[FATAL] rigctld startup failed: {e}")
        sys.exit(1)
    except Exception as e:
        if logger:
            logger.exception("[FATAL] Unexpected error occurred")
        else:
            print(f"[FATAL] Unexpected error occurred: {e}")
        sys.exit(1)
