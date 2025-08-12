"""PTT wait logic with adaptive manual fallback.

This module centralizes the 'wait for carrier' logic, including:
- Immediate manual mode for rigctl dummy, or when force_manual_ptt is true, or when backend lacks PTT
- Hard deadline for PTT detection, then fallback to manual mode
- Clear user prompts for manual workflow
"""
from typing import Any, Optional


def wait_for_carrier_or_manual(
    radio_client: Any,
    ctx: Any,
    logger,
    amplifier_name: str,
    beep_func,
    base_radio_error_cls: Optional[type] = None,
) -> bool:
    """Wait for carrier using PTT sensing when available, otherwise switch to manual.

    Returns True if manual mode is engaged, otherwise False.

    The function prints user prompts and logs decisions.
    """
    # Defaults
    poll = 0.25
    max_no_ptt_secs = float((ctx.config.get('defaults') or {}).get('ptt_adaptive_fallback_after', 30.0))
    manual_switch = False
    found_ptt = False

    # Config flags
    defaults = ctx.config.get('defaults') or {}
    force_manual = bool(defaults.get('force_manual_ptt', False))

    # Backend capability flags
    backend_no_ptt = getattr(radio_client, 'ptt_supported', None) is False

    # Detect Hamlib Dummy model explicitly
    rs = ctx.radio_settings or {}
    rig_model = rs.get('rigctld_model', None)
    try:
        rig_model_num = int(rig_model) if rig_model is not None else None
    except Exception:
        rig_model_num = None
    is_dummy_model = (rig_model_num == 1) or (isinstance(rs.get('model'), str) and rs['model'].lower() == 'dummy')

    # Immediate MANUAL if any of these hold
    if force_manual or backend_no_ptt or is_dummy_model:
        reason = 'force_manual_ptt=true' if force_manual else ('backend has no PTT' if backend_no_ptt else 'rigctl dummy model')
        logger.warning(f"[PTT] Immediate MANUAL mode: {reason}. Using manual prompts for this and remaining segments.")
        manual_switch = True
    else:
        # Attempt PTT sensing up to a hard deadline
        print("[WAIT] Waiting for carrier", end="", flush=True)
        import time as _tmon
        deadline = _tmon.monotonic() + max_no_ptt_secs
        dots = 0
        while _tmon.monotonic() < deadline:
            try:
                if radio_client.get_ptt():
                    print(" detected.")
                    found_ptt = True
                    break
            except Exception as e:
                # If a specific BaseRadioError is provided, only log that class sparsely
                if base_radio_error_cls and isinstance(e, base_radio_error_cls):
                    print(" x", end="", flush=True)
                    logger.warning(f"[WAIT] radio error, retrying: {e}")
                else:
                    print(" x", end="", flush=True)
                    logger.warning(f"[WAIT] unexpected radio error, retrying: {e}")
            _tmon.sleep(poll)
            print(".", end="", flush=True)
            dots += 1
            # gentle 'still waiting' heartbeat every ~5 s
            if dots % int(max(1, round(5.0 / poll))) == 0:
                print(" (still waiting)", end="", flush=True)

        if not found_ptt:
            manual_switch = True
            # mark backend as unreliable for the rest of the session
            try:
                setattr(radio_client, 'ptt_supported', False)
            except Exception:
                pass
            logger.warning(f"[PTT] No PTT change detected within {max_no_ptt_secs:.1f}s. Falling back to MANUAL prompts for this and remaining segments.")

    # Manual prompts workflow
    if manual_switch:
        print("\n[PTT] Manual mode engaged.")
        print("     → This backend does not provide reliable PTT status.")
        print("     → When you are READY to key a steady carrier, press ENTER, then key down.")
        input("       Press ENTER to continue...")
        try:
            beep_func((ctx.config.get('defaults') or {}).get('use_beep', True))
        except Exception:
            pass
        print("\n→ Begin transmitting a steady carrier (key down).");
        print(f"→ Keep transmitting and tune/store on your {amplifier_name}.")
        input("  Press ENTER AFTER you have UNKEYED (stopped transmitting)...")
        print("\n[PTT] Carrier stopped (manual).");
        return True

    # Automatic PTT sensed
    print("\n[PTT] Carrier detected — radio is transmitting.")
    print(f"       → Tune your {amplifier_name} now.")
    print(f"       → Keep transmitting! **AFTER** you finish tuning your {amplifier_name}, unkey (stop transmitting).");
    return False
