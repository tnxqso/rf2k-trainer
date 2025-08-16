# tuning_loop.py
# Core tuning loop extracted from main.py to keep main lean.
# Comments are in English by convention.

from __future__ import annotations
from typing import Optional, Set, Tuple, List
import time as _time

from band_math import calculate_tuning_frequencies
from utils import beep, pretty_duration
from ui_status import status_show, status_clear, BG_GREEN, BG_RED
from radio_interface import BaseRadioClient, BaseRadioError
from rf2ks_client import RF2KSClient
from app_context import AppContext

# Keep a local constant to avoid importing main
AMPLIFIER_NAME = "RF2K-S HF Power Amplifier"

class FatalFrequencyMismatch(Exception):
    """Raised when RF2K-S /data frequency doesn't match the expected truncated kHz."""
    pass

def _should_verify_freq(ctx: "AppContext", rf2ks: "RF2KSClient") -> bool:
    """
    Only verify /data frequency when:
    - RF2K-S control is enabled
    - RF2K-S operational interface is CAT
    - Radio is not rigctl Dummy (no RF/meaningful sync)
    """
    if not getattr(ctx, "amp_settings", {}).get("enabled", False):
        return False
    if not hasattr(rf2ks, "is_cat_iface") or not rf2ks.is_cat_iface():
        return False
    desc = (getattr(ctx, "radio_description", None) or "").lower()
    if "dummy" in desc:
        return False
    return True

def _wait_event_with_dots(wait_fn, total_timeout: float, waiting_label: str) -> bool:
    """Call a client's wait_* method in short steps to keep printing dots."""
    import time
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
            if "carrier" in waiting_label.lower():
                print(" detected.")
            else:
                print(" done.")
            return True
        print(".", end="", flush=True)
        dots += 1
        if dots % 10 == 0:
            print(" (still waiting)", end="", flush=True)


def run_tuning_loop(
    radio_client: BaseRadioClient,
    rf2ks: Optional[RF2KSClient],
    ctx: AppContext,
) -> None:
    """
    RF2K-Trainer main tuning loop.

    Optimizations over previous version:
    - Read timeouts/steps from config with sane defaults.
    - Throttle colored status updates to avoid excessive redraws.
    - Cache frequently used flags/values locally.
    """

    # ---------- Local helpers ----------
    def _band_iter():
        if getattr(ctx, "selected_bands", None):
            for bname in ctx.selected_bands:
                cfg = ctx.bands.get(bname)
                if cfg:
                    yield bname, cfg
        else:
            for bname, cfg in ctx.bands.items():
                yield bname, cfg

    # Throttled status line to reduce flicker/CPU
    last_status_msg = None
    last_status_bg = None
    last_status_ts = 0.0

    def status_update(msg: str, bg) -> None:
        """Only redraw status line if message/bg changed or at least 100 ms passed."""
        nonlocal last_status_msg, last_status_bg, last_status_ts
        now = _time.time()
        if msg != last_status_msg or bg != last_status_bg or (now - last_status_ts) >= 0.10:
            status_show(msg, bg)
            last_status_msg = msg
            last_status_bg = bg
            last_status_ts = now

    def status_reset() -> None:
        """Clear and reset last status cache."""
        nonlocal last_status_msg, last_status_bg, last_status_ts
        status_clear()
        last_status_msg = None
        last_status_bg = None
        last_status_ts = 0.0

    # ---------- Config ----------
    defaults = ctx.config.get("defaults", {}) if ctx and ctx.config else {}
    auto_set_cw_mode = bool(defaults.get("auto_set_cw_mode", True))
    default_drive    = int(defaults.get("drive_power", 13))
    use_color_status = bool(defaults.get("use_color_status", True))
    guidance_mode    = str(defaults.get("guidance_mode", "compact")).lower()

    # Time constants (configurable)
    wait_tx_timeout   = float(defaults.get("wait_tx_timeout_s", 180.0))
    wait_unkey_timeout= float(defaults.get("wait_unkey_timeout_s", 300.0))
    event_step        = float(defaults.get("wait_step_s", 0.25))
    cat_settle_s      = float(defaults.get("cat_settle_s", 0.30))

    # Flags derived from context/args
    amp_enabled = bool(getattr(ctx, "amp_settings", {}).get("enabled", False) and rf2ks)
    use_beep    = bool(getattr(ctx, "use_beep", False))

    total_segments: int = 0
    seen_bands: Set[str] = set()
    manual_mode_announced = False
    _guidance_shown_once: Set[str] = set()
    t0 = _time.time()

    # ---------- Build plan ----------
    plan: List[Tuple[str, float]] = []
    for band_label, b in _band_iter():
        pts_khz = calculate_tuning_frequencies(
            b["band_start"], b["band_end"], b["segment_size"], b["first_segment_center"]
        )
        for k in pts_khz:  # kHz → MHz
            plan.append((band_label, round(k / 1000.0, 4)))

    if not plan:
        ctx.logger.error("[FATAL] No tuning segments computed. Check band configuration.")
        return

    # ---------- Loop ----------
    last_band: Optional[str] = None
    for band_label, freq_mhz in plan:
        # New band setup
        if band_label != last_band:
            print()
            ctx.logger.info(f"=== Band: {band_label} ===")
            seen_bands.add(band_label)
            try:
                if auto_set_cw_mode:
                    radio_client.set_mode("CW", 400)
                current_drive_w = int(ctx.bands[band_label].get("drive_power", default_drive))
                if hasattr(radio_client, "set_drive_power"):
                    radio_client.set_drive_power(current_drive_w)
            except BaseRadioError as e:
                ctx.logger.error(f"[RADIO] Band prep failed for {band_label}: {e}")
                last_band = band_label
                continue
            last_band = band_label

        # Set frequency
        try:
            radio_client.set_frequency(freq_mhz)
        except BaseRadioError as e:
            ctx.logger.error(f"[RADIO] freq set failed {band_label} @ {freq_mhz:.4f} MHz: {e}")
            continue

        # Verify RF2K-S /data frequency (truncated kHz) if PA API is enabled
        if amp_enabled and _should_verify_freq(ctx, rf2ks):

            # Let the PA's controller see the CAT change
            if rf2ks.is_cat_iface():
                _time.sleep(cat_settle_s)

            try:
                rf2ks.verify_frequency_match(
                    expected_freq_mhz=freq_mhz,
                    max_tries=2,      # allow a brief second chance
                    delay_s=2.0       # per-try wait window
                )
            except Exception as e:
                # Make this fatal: abort the whole run and signal non-zero exit upstream.
                msg = f"/data frequency check failed for {freq_mhz:.4f} MHz: {e}"
                ctx.logger.error(f"[RF2K-S] {msg}")
                raise FatalFrequencyMismatch(msg)


        # Operator guidance
        print(f"""
=== Tuning {band_label} band @ {freq_mhz:.4f} MHz ===

→ Begin transmitting a steady carrier (key down).
→ While transmitting, tune and store match on your {AMPLIFIER_NAME}.
→ DO NOT unkey the transmitter until tuning is complete and stored.
""".rstrip())
        print()

        # Optional beep
        try:
            if use_beep:
                beep(True)
        except Exception:
            pass

        # Decide PTT path
        ptt_supported = getattr(radio_client, "ptt_supported", True)
        used_auto_ptt = False

        # --- EVENT-DRIVEN ---
        is_event = getattr(radio_client, "ptt_supported", True) and getattr(radio_client, "supports_event_ptt", False)
        if is_event:
            if use_color_status:
                # Wait for TX with a throttled status line
                status_update("AUTO-PTT READY — press PTT to start carrier", BG_GREEN)
                deadline = _time.time() + wait_tx_timeout
                got_tx = False
                while _time.time() < deadline:
                    if radio_client.wait_for_tx(timeout=min(event_step, max(0.05, wait_tx_timeout))):
                        got_tx = True
                        break
                    status_update("AUTO-PTT READY — press PTT to start carrier", BG_GREEN)

                status_reset()
                if not got_tx:
                    ctx.logger.warning("[WAIT] Timeout waiting for carrier (event-driven). Skipping segment.")
                    continue

                # Verbose one-time guidance per band if requested
                show_verbose = (
                    guidance_mode == "verbose" or
                    (guidance_mode == "once_per_band" and band_label not in _guidance_shown_once)
                )
                if show_verbose:
                    print("\n[PTT] Carrier detected — radio is transmitting.")
                    print(f"       → Tune your {AMPLIFIER_NAME} now.")
                    print(f"       → Keep transmitting! **AFTER** you finish tuning your {AMPLIFIER_NAME}, unkey (stop transmitting).")
                    _guidance_shown_once.add(band_label)

                # Wait for UNKEY with a throttled status line
                status_update("TX ACTIVE — tune & store, then UNKEY", BG_RED)
                deadline2 = _time.time() + wait_unkey_timeout
                while _time.time() < deadline2:
                    if radio_client.wait_for_unkey(timeout=min(event_step, max(0.05, wait_unkey_timeout))):
                        used_auto_ptt = True
                        break
                    status_update("TX ACTIVE — tune & store, then UNKEY", BG_RED)

                status_reset()
                if not used_auto_ptt:
                    ctx.logger.warning("[WAIT] Timeout waiting for unkey (event-driven). Continuing.")
                else:
                    print("\n[PTT] Carrier stopped.")

            else:
                # Fallback dotted UX (unchanged)
                ok = _wait_event_with_dots(radio_client.wait_for_tx, total_timeout=wait_tx_timeout, waiting_label="Waiting for carrier")
                if not ok:
                    ctx.logger.warning("[WAIT] Timeout waiting for carrier (event-driven). Skipping segment.")
                    continue
                print("\n[PTT] Carrier detected — radio is transmitting.")
                print(f"       → Tune your {AMPLIFIER_NAME} now.")
                print(f"       → Keep transmitting! **AFTER** you finish tuning your {AMPLIFIER_NAME}, unkey (stop transmitting).")
                ok2 = _wait_event_with_dots(radio_client.wait_for_unkey, total_timeout=wait_unkey_timeout, waiting_label="Still transmitting")
                if not ok2:
                    ctx.logger.warning("[WAIT] Timeout waiting for unkey (event-driven). Continuing.")
                else:
                    print("\n[PTT] Carrier stopped.")
                used_auto_ptt = bool(ok2)

        # --- MANUAL (no PTT support) ---
        elif not ptt_supported:
            if not manual_mode_announced:
                print("\n[PTT] This rig/rigctld does not report PTT (RPRT -11). Switching to MANUAL mode.")
                manual_mode_announced = True

            print("     → When you are READY to key a steady carrier, press ENTER, then key down.")
            input("       Press ENTER to confirm you are about to key...")

            print(f"\n       → Keep transmitting and tune/store on your {AMPLIFIER_NAME}.")
            input("       Press ENTER AFTER you have UNKEYED (stopped transmitting)...")
            print("\n[PTT] Carrier stopped (manual).")

        # --- POLLING (get_ptt) ---
        else:
            poll = 0.25
            print("[WAIT] Waiting for carrier", end="", flush=True)
            dots = 0
            while True:
                try:
                    if radio_client.get_ptt():
                        print(" detected.")
                        break
                except BaseRadioError as e:
                    print(" x", end="", flush=True)
                    ctx.logger.warning(f"[WAIT] radio error, retrying: {e}")
                _time.sleep(poll)
                print(".", end="", flush=True)
                dots += 1
                if dots % int(max(1, round(5.0 / poll))) == 0:
                    print(" (still waiting)", end="", flush=True)

            print("\n[PTT] Carrier detected — radio is transmitting.")
            print(f"       → Tune your {AMPLIFIER_NAME} now.")
            print(f"       → Keep transmitting! **AFTER** you finish tuning your {AMPLIFIER_NAME}, unkey (stop transmitting).")

            print("[WAIT] Still transmitting", end="", flush=True)
            dots = 0
            while True:
                try:
                    if not radio_client.get_ptt():
                        print(" done.")
                        break
                except BaseRadioError as e:
                    print(" ?", end="", flush=True)
                    ctx.logger.warning(f"[WAIT] radio error, retrying: {e}")
                _time.sleep(poll)
                print(".", end="", flush=True)
                dots += 1
                if dots % int(max(1, round(5.0 / poll))) == 0:
                    print(" (still waiting)", end="", flush=True)
            print("\n[PTT] Carrier stopped.")
            used_auto_ptt = True

        # Log tuner/L/C (+ optional drive/swr if auto-PTT) via RF2K-S API
        try:
            if amp_enabled:
                rf2ks.log_tuner_data(used_auto_ptt)
        except Exception as e:
            ctx.logger and ctx.logger.debug(f"[LOG] log_tuner_data failed: {e}")

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
