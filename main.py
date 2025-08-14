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
import platform
import sys
import time
import yaml
import socket

from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple, Type

from radio_interface import BaseRadioError, BaseRadioClient
from rf2ks_client import RF2KSClient, RF2KSClientError
from config_validation import validate_rigctl_settings
from radio_registry import RADIO_CLIENTS
from rigctld_manager import RigctldManager, RigCtldManagerError

# On Windows terminals, force UTF-8 so icons and accents render OK.
if os.name == "nt":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

PROGRAM_NAME = "RF2K-Trainer"
VERSION = "0.9.201"
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


@dataclass
class AppContext:
    """Lightweight container for state shared across the run."""
    logger: Any
    config: Dict[str, Any]
    debug_mode: bool
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


def pretty_duration(seconds: float, style: str = "auto") -> str:
    """Format a duration in a human-friendly way.
    style="auto": '1h 02m 05s', '22m 03s', '3.40 s', '850 ms'
    style="clock": 'HH:MM:SS'
    """
    if seconds < 0:
        seconds = 0.0

    if style == "clock":
        total = int(round(seconds))
        h = total // 3600
        m = (total % 3600) // 60
        s = total % 60
        return f"{h:02d}:{m:02d}:{s:02d}"

    if seconds < 0.001:
        return "0 ms"
    if seconds < 1.0:
        return f"{seconds * 1000:.0f} ms"
    if seconds < 60.0:
        return f"{seconds:.2f} s"

    total = int(round(seconds))
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60

    if h > 0:
        return f"{h}h {m}m {s:02d}s"
    return f"{m}m {s:02d}s"


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


# -------------------------
# Tuning grid math
# -------------------------
def calculate_tuning_frequencies(band_start_khz: float,
                                 band_end_khz: float,
                                 segment_size_khz: float,
                                 first_segment_center_khz: float) -> List[float]:
    """
    Compute tuning points that cover a band using a fixed segment width.

    All internal math is done in Hz (integers) to avoid rounding drift.
    Return values are floats in kHz to preserve 0.25/0.5/0.75 steps for printing.

    Parameters
    ----------
    band_start_khz : float
        Lower edge of the band (kHz), e.g. 5351.5 for 60 m WRC-15 start.
    band_end_khz : float
        Upper edge of the band (kHz), e.g. 5366.5 for 60 m WRC-15 end.
    segment_size_khz : float
        Segment width (kHz), e.g. 9.0 for 9 kHz segments.
    first_segment_center_khz : float
        A reference center on the segment grid (kHz). Full segments will be
        placed at c0 + n * step, n ∈ ℤ. The first full segment is the one whose
        left edge is >= band_start.

    Returns
    -------
    List[float]
        Tuning points in kHz (floats). These include:
        - all FULL segment centers that fit entirely inside the band, and
        - leading/trailing EDGE fillers at the center of any leftover gaps
          between the band edges and the nearest full segment edges.

        If no full segments fit at all, exactly two edge fillers are returned.
    """
    # Validate inputs
    if band_end_khz <= band_start_khz:
        return []

    # Convert everything to Hz (integers)
    bs = int(round(band_start_khz * 1000))
    be = int(round(band_end_khz * 1000))
    step = int(round(segment_size_khz * 1000))
    if step <= 0:
        raise ValueError("segment_size_khz must be > 0")

    c0 = int(round(first_segment_center_khz * 1000))
    half = step // 2  # integer half-width in Hz

    # Find the first grid center whose LEFT edge is >= band_start:
    #   c - half >= bs  =>  c >= bs + half
    #   c = c0 + k*step  =>  k >= (bs + half - c0)/step
    import math as _math
    k_right = _math.ceil((bs + half - c0) / step)
    c_right = c0 + k_right * step        # first candidate center
    left_edge_right = c_right - half     # its left edge

    points_hz: List[int] = []

    # Collect all full segments entirely within the band
    c = c_right
    while (c - half) >= bs and (c + half) <= be:
        points_hz.append(c)
        c += step

    if not points_hz:
        # No full segments fit: produce TWO edge fillers
        # Junction inside the band is at the left edge of the first would-be full segment.
        # Clamp defensively to [bs, be].
        L = max(bs, min(left_edge_right, be))

        # Degenerate guard (extremely narrow band): just return band center
        if L <= bs or L >= be:
            mid_hz = (bs + be) // 2
            return [mid_hz / 1000.0]  # kHz float

        lead = bs + (L - bs) // 2          # center of leading gap
        trail = be - (be - L) // 2         # center of trailing gap
        return [lead / 1000.0, trail / 1000.0]  # kHz floats

    # Edge fillers around the set of full segments (optional but recommended)
    # Leading gap: from band start to the left edge of the first full segment
    first_c = points_hz[0]
    first_left = first_c - half
    if first_left > bs:
        lead = bs + (first_left - bs) // 2
        points_hz.insert(0, lead)

    # Trailing gap: from the right edge of the last full segment to band end
    last_c = points_hz[-1]
    last_right = last_c + half
    if last_right < be:
        trail = be - (be - last_right) // 2
        points_hz.append(trail)

    # Return kHz as floats (no truncation)
    return [p / 1000.0 for p in points_hz]


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


# -------------------------
# rigctld availability helpers
# -------------------------
def is_tcp_port_open(host: str, port: int, timeout: float = 1.0, attempts: int = 2, backoff_s: float = 0.2) -> bool:
    """Return True if a TCP connection to host:port can be established within timeout."""
    for _ in range(max(1, attempts)):
        try:
            with socket.create_connection((host, int(port)), timeout=timeout):
                return True
        except Exception:
            time.sleep(backoff_s)
    return False


def ensure_rigctld_available(radio_settings: Dict[str, Any], port: int) -> None:
    """
    Validate that an externally-managed rigctld is reachable before continuing.
    Raises ConfigurationError with actionable instructions if not available.
    """
    host = radio_settings.get("host", "localhost")
    if is_tcp_port_open(host, port, timeout=1.0, attempts=3):
        return

    # Build actionable guidance
    model = radio_settings.get("model") or radio_settings.get("rigctld_model") or "<MODEL>"
    serial_port = radio_settings.get("serial_port") or radio_settings.get("rigctld_serial_port") or "<COMx/ttyUSBx>"
    rigctld_path = radio_settings.get("rigctld_path") or "rigctld"
    example = f'"{rigctld_path}" -m {model} -r {serial_port} -t {port}'

    msg = (
        f"rigctld is not reachable at {host}:{port} (auto_start_rigctld=false).\n"
        f"Start rigctld yourself, or set auto_start_rigctld: true in settings.yml.\n"
        f"Example command:\n  {example}"
    )
    raise ConfigurationError(msg)


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
            ensure_rigctld_available(radio_settings, port)
            radio_description = "Hamlib rigctld (external)"

    elif radio_type == "flex":
        radio_description = "FlexRadio (SmartSDR TCP/IP API)"

    return radio_settings, radio_type, radio_label, radio_class, radio_description, rigctld


def beep(enabled: bool = True) -> None:
    """Short audible cue before each tuning step (optional)."""
    if not enabled:
        return
    if platform.system() == "Windows":
        try:
            import winsound
            winsound.Beep(1000, 300)
        except Exception:
            print("\a", end="")
    else:
        print("\a", end="")


def countdown(seconds: int, message: str = "    →  Tuning next frequency") -> None:
    """Simple countdown helper if we ever want a short delay between steps."""
    for i in range(seconds, 0, -1):
        sys.stdout.write(f"{message} in {i} second(s)...\r")
        sys.stdout.flush()
        time.sleep(1)
    # Clear the line and add a clean newline so the next logger line won't collide
    sys.stdout.write(" " * 80 + "\r")
    sys.stdout.flush()
    print()


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


# --- Flex helper: wait on event with dotted progress ---
def _wait_event_with_dots(wait_fn, total_timeout: float, waiting_label: str) -> bool:
    """Calls a FlexRadioClient wait_* method in short steps to keep printing dots."""
    print(f"[WAIT] {waiting_label}", end="", flush=True)
    deadline = time.time() + total_timeout
    step = 0.5
    dots = 0
    while True:
        left = deadline - time.time()
        if left <= 0:
            print(" timeout.")
            return False
        if wait_fn(timeout=min(step, left)):
            # standardized ending: 'detected.' for carrier, 'done.' for unkey
            if "carrier" in waiting_label.lower():
                print(" detected.")
            else:
                print(" done.")
            return True
        print(".", end="", flush=True)
        dots += 1
        if dots % 10 == 0:
            print(" (still waiting)", end="", flush=True)


def run_tuning_loop(radio_client: BaseRadioClient, rf2ks: RF2KSClient, ctx: AppContext) -> None:
    """
    RF2K-Trainer main tuning loop.

    Behavior
    --------
    - Per-band setup (once per band): set CW mode (optional) and drive power if the client supports it.
    - Per-segment: set frequency only, then wait for TX and UNKEY to let the operator tune the amplifier.
    - PTT:
        * Event-driven if the client exposes wait_for_tx()/wait_for_unkey() and ptt_supported is True.
        * Otherwise fall back to polling get_ptt().
        * If ptt_supported is False (e.g., rigctl Dummy), use MANUAL prompts (printed once per session).
    - Tuning plan: generated from ctx.bands using calculate_tuning_frequencies(),
      iterating bands in ctx.selected_bands order if available.
    """
    import time as _time
    from radio_interface import BaseRadioError as _BaseRadioError

    # ---------- Helpers ----------
    def _band_iter():
        """Yield (band_label, band_cfg) in the desired order."""
        if getattr(ctx, "selected_bands", None):
            for bname in ctx.selected_bands:
                cfg = ctx.bands.get(bname)
                if cfg:
                    yield bname, cfg
        else:
            for bname, cfg in ctx.bands.items():
                yield bname, cfg

    # ---------- Constants / defaults ----------
    auto_set_cw_mode = bool(ctx.config.get("defaults", {}).get("auto_set_cw_mode", True))
    default_drive = int(ctx.config.get("defaults", {}).get("drive_power", 13))

    total_segments = 0
    seen_bands: Set[str] = set()
    manual_mode_announced = False
    t0 = _time.time()

    # ---------- Build tuning plan (ordered by bands) ----------
    plan: List[Tuple[str, float]] = []  # list[(band_label, freq_mhz)]
    for band_label, b in _band_iter():
        pts_khz = calculate_tuning_frequencies(
            b["band_start"], b["band_end"], b["segment_size"], b["first_segment_center"]
        )
        # Convert kHz->MHz for execution/printing
        for k in pts_khz:
            plan.append((band_label, round(k / 1000.0, 4)))

    if not plan:
        logger.error("[FATAL] No tuning segments computed. Check band configuration.")
        return

    # ---------- Main loop ----------
    last_band: Optional[str] = None
    for band_label, freq_mhz in plan:
        # New band block?
        if band_label != last_band:
            print()
            logger.info(f"=== Band: {band_label} ===")
            seen_bands.add(band_label)

            # Per-band setup: mode + (if supported) drive power
            try:
                if auto_set_cw_mode:
                    radio_client.set_mode("CW", 400)  # once per band

                # Per-band drive: use band-specific override if present
                drive_w = int(ctx.bands[band_label].get("drive_power", default_drive))
                if hasattr(radio_client, "set_drive_power"):
                    radio_client.set_drive_power(drive_w)  # clients may internally skip if unchanged
            except _BaseRadioError as e:
                logger.error(f"[RADIO] Band prep failed for {band_label}: {e}")
                last_band = band_label
                continue

            last_band = band_label

        # Per-segment: set frequency only
        try:
            radio_client.set_frequency(freq_mhz)
        except _BaseRadioError as e:
            logger.error(f"[RADIO] freq set failed {band_label} @ {freq_mhz:.4f} MHz: {e}")
            continue

        # Give the amplifier controller a short moment to pick up the CAT change
        _time.sleep(0.3)

        # Verify PA sees the same (truncated kHz) frequency via /data
        if getattr(ctx, "amp_settings", {}).get("enabled", False):
            rf2ks.verify_frequency_match(expected_freq_mhz=freq_mhz)

        # Operator guidance for the segment
        print(f"""
=== Tuning {band_label} band @ {freq_mhz:.4f} MHz ===

→ Begin transmitting a steady carrier (key down).
→ While transmitting, tune and store match on your {AMPLIFIER_NAME}.
→ DO NOT unkey the transmitter until tuning is complete and stored.
""".rstrip())
        print()

        # Optional audible cue
        try:
            if getattr(ctx, "use_beep", False):
                beep(True)
        except Exception:
            pass

        # Decide PTT method for this segment
        ptt_supported = getattr(radio_client, "ptt_supported", True)
        used_auto_ptt = False

        if ptt_supported and hasattr(radio_client, "wait_for_tx") and hasattr(radio_client, "wait_for_unkey"):
            ok = _wait_event_with_dots(radio_client.wait_for_tx, total_timeout=180, waiting_label="Waiting for carrier")
            if not ok:
                logger.warning("[WAIT] Timeout waiting for carrier (event-driven). Skipping segment.")
                continue

            print("\n[PTT] Carrier detected — radio is transmitting.")
            print(f"       → Tune your {AMPLIFIER_NAME} now.")
            print(f"       → Keep transmitting! **AFTER** you finish tuning your {AMPLIFIER_NAME}, unkey (stop transmitting).")

            ok2 = _wait_event_with_dots(radio_client.wait_for_unkey, total_timeout=300, waiting_label="Still transmitting")
            if not ok2:
                logger.warning("[WAIT] Timeout waiting for unkey (event-driven). Continuing.")
            else:
                print("\n[PTT] Carrier stopped.")
                used_auto_ptt = True

        elif not ptt_supported:
            # Manual path (e.g., rigctl Dummy) — announce once
            if not manual_mode_announced:
                print("\n[PTT] This rig/rigctld does not report PTT (RPRT -11). Switching to MANUAL mode.")
                manual_mode_announced = True

            print("     → When you are READY to key a steady carrier, press ENTER, then key down.")
            input("       Press ENTER to confirm you are about to key...")

            print(f"\n       → Keep transmitting and tune/store on your {AMPLIFIER_NAME}.")
            input("       Press ENTER AFTER you have UNKEYED (stopped transmitting)...")
            print("\n[PTT] Carrier stopped (manual).")

        else:
            # Generic polling fallback
            poll = 0.25  # conservative default
            # Wait TX
            print("[WAIT] Waiting for carrier", end="", flush=True)
            dots = 0
            while True:
                try:
                    if radio_client.get_ptt():
                        print(" detected.")
                        break
                except _BaseRadioError as e:
                    print(" x", end="", flush=True)
                    logger.warning(f"[WAIT] radio error, retrying: {e}")
                _time.sleep(poll)
                print(".", end="", flush=True)
                dots += 1
                if dots % int(max(1, round(5.0 / poll))) == 0:
                    print(" (still waiting)", end="", flush=True)

            print("\n[PTT] Carrier detected — radio is transmitting.")
            print(f"       → Tune your {AMPLIFIER_NAME} now.")
            print(f"       → Keep transmitting! **AFTER** you finish tuning your {AMPLIFIER_NAME}, unkey (stop transmitting).")

            # Wait UNKEY
            print("[WAIT] Still transmitting", end="", flush=True)
            dots = 0
            while True:
                try:
                    if not radio_client.get_ptt():
                        print(" done.")
                        break
                except _BaseRadioError as e:
                    print(" ?", end="", flush=True)
                    logger.warning(f"[WAIT] radio error, retrying: {e}")
                _time.sleep(poll)
                print(".", end="", flush=True)
                dots += 1
                if dots % int(max(1, round(5.0 / poll))) == 0:
                    print(" (still waiting)", end="", flush=True)
            print("\n[PTT] Carrier stopped.")

        # Persist tuner data after each segment (if enabled)
        try:
            if getattr(ctx, "amp_settings", {}).get("enabled", False):
                rf2ks.log_tuner_data(used_auto_ptt)
        except Exception as e:
            logger and logger.debug(f"[LOG] log_tuner_data failed: {e}")

        total_segments += 1

    # ---------- Summary ----------
    elapsed = _time.time() - t0
    avg = (elapsed / total_segments) if total_segments else 0.0
    tot_str = pretty_duration(elapsed, style="auto")
    avg_str = pretty_duration(avg, style="auto")
    bands_count = len(seen_bands) if seen_bands else (len(getattr(ctx, "selected_bands", [])) or 1)

    print(f"""
    === TUNING COMPLETE ===
    Bands tuned      : {bands_count}
    Segments tuned   : {total_segments}
    Total time       : {tot_str}
    Avg time/segment : {avg_str}
    =========================================
    """.rstrip())


def main() -> None:
    show_banner_and_clear()

    global logger
    parser = argparse.ArgumentParser(description=f"RF2K-Trainer: Tune {AMPLIFIER_NAME} by band")
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

    if args.info:
        print(f"{PROGRAM_NAME} - v{VERSION} - Band Information")
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
    {PROGRAM_NAME} - v{VERSION}
    Sequential HF Band Tuning Utility for RF2K-S Amplifiers
    Github repo: {GIT_PROJECT_URL}
    =================================================================
    """)

    radio_client: Optional[BaseRadioClient] = None
    try:
        # Radio client setup and connect
        logger.info(f"\nConnecting to {ctx.radio_label} at {ctx.radio_settings.get('host')}:{ctx.radio_settings.get('port')}...")
        assert radio_class is not None, "radio_class not resolved"
        radio_client = radio_class(ctx.radio_settings.get("host"), ctx.radio_settings.get("port"))
        validate_rigctl_settings(ctx, logger)
        radio_client.connect()

        # --- One-time PTT capability detection (no delay at beep) ---
        if ctx.radio_type == "rigctl":
            if "dummy" in (ctx.radio_description or "").lower():
                # Hamlib Dummy has no PTT → go manual for the whole run
                setattr(radio_client, "ptt_supported", False)
                logger.debug("[PTT] Dummy rig detected -> manual mode for this session.")
            else:
                # One quick probe now so later flow won't block
                try:
                    _ = radio_client.get_ptt()
                    # get_ptt() will set radio_client.ptt_supported=False if RPRT -11
                    logger.debug(f"[PTT] capability: {getattr(radio_client, 'ptt_supported', True)}")
                except BaseRadioError as e:
                    logger.debug(f"[PTT] initial probe failed (ignored): {e}")

        # Amplifier setup
        if ctx.amp_settings.get("enabled", False):
            rf2ks = RF2KSClient(ctx.config)
            rf2ks.fetch_info()
            rf2ks.set_operate_mode("STANDBY")
        else:
            logger.warning(f"{AMPLIFIER_NAME} is not enabled, skipping {AMPLIFIER_NAME} operations.")

        show_instructions(ctx)
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
