# radio_interface.py

"""
RF2K-TRAINER radio interface contract — PTT variants and UX

This module defines the minimal interface a radio client must implement and
documents how Push-To-Talk (PTT) is handled by RF2K-TRAINER. There are three
distinct execution paths, selected at runtime based on client capabilities:

1) EVENT-DRIVEN PTT  (best UX)
   --------------------------------------------------------------
   What it is:
     The client exposes blocking waits:
       • wait_for_tx(timeout)     -> bool  (True when TX asserted)
       • wait_for_unkey(timeout)  -> bool  (True when TX deasserted)
     and sets a capability flag:
       • supports_event_ptt = True
     The client must also expose:
       • ptt_supported = True

   How to implement:
     - Native event source (e.g., Flex) should wire wait_* to the radio streams.
     - For Hamlib/rigctl you may emulate events with a small background thread
       that polls 't' and signals edges to waiters via a Condition/Event.
       Keep the poll cadence modest (e.g., 100–250 ms idle; 50–100 ms while TX).

   User-visible behavior:
     - RF2K-TRAINER shows GREEN banner: “AUTO-PTT READY — press PTT…”
     - On TX it shows RED banner: “TX ACTIVE — tune & store, then UNKEY”.
     - No “dot spam”; timeouts display clean warnings.

2) POLLING PTT  (solid fallback)
   --------------------------------------------------------------
   What it is:
     The client can read instantaneous PTT via get_ptt(), but does NOT implement
     wait_for_tx/unkey. Capability flags:
       • ptt_supported = True
       • supports_event_ptt = False  (default)

   How it’s used:
     RF2K-TRAINER loops on get_ptt() until TX/UNKEY with a short sleep.

   User-visible behavior:
     - Text “Waiting for carrier…” with dots; periodic “(still waiting)”.

3) MANUAL MODE  (last resort)
   --------------------------------------------------------------
   What it is:
     The client/radio cannot report PTT at all (e.g., Hamlib Dummy “RPRT -11”):
       • ptt_supported = False
       • supports_event_ptt = False

   How it’s used:
     RF2K-TRAINER prompts the operator to press ENTER to confirm key-down and
     ENTER again after unkey.

   User-visible behavior:
     - Clear step-by-step prompts; no auto-detection.

Selection logic (in tuning loop)
--------------------------------
if not ptt_supported:
    manual()
elif supports_event_ptt:
    event_driven()
else:
    polling()

Time-out semantics for wait_* (contract)
----------------------------------------
• wait_for_tx(timeout): return True as soon as TX is observed; False only if the
  timeout elapses with no TX.
• wait_for_unkey(timeout): return True as soon as TX clears; False only if the
  timeout elapses while still TX.
• These calls must never raise on normal timeouts; use internal logging instead.

Safety & load considerations
----------------------------
• Don’t hammer the radio: when emulating events, use conservative poll intervals.
• If a transport error occurs, it’s acceptable to attempt one reconnect; if that
  fails, disable event mode (supports_event_ptt=False). The app will automatically
  fall back to polling or manual as appropriate.

Developer checklist for new clients
-----------------------------------
[ ] Implement connect(), set_mode(), set_frequency(), get_ptt(), disconnect()
[ ] Provide set_drive_power() (no-op is acceptable when unsupported)
[ ] Set ptt_supported = False when the API cannot read TX (e.g., RPRT -11)
[ ] OPTIONAL: implement wait_for_tx()/wait_for_unkey() and set supports_event_ptt=True
[ ] Make wait_* respect the timeout and return booleans; do not raise on timeout
"""

from abc import ABC, abstractmethod

class BaseRadioError(Exception):
    """Generic radio communication error (superclass for all rig errors)."""
    pass

class BaseRadioClient(ABC):
    @abstractmethod
    def connect(self): ...

    @abstractmethod
    def set_mode(self, mode: str = "CW", width: int = 400): ...

    @abstractmethod
    def set_frequency(self, freq_mhz: float): ...

    @abstractmethod
    def set_drive_power(self, rfpower: int): ...

    @abstractmethod
    def disconnect(self): ...

    @abstractmethod
    def get_ptt(self) -> bool:
        """Return True if the radio is currently transmitting (PTT active), else False."""
    ...
    
    # ---- Event-driven PTT stubs (optional; subclasses may override) ----
    def wait_for_tx(self, timeout: float) -> bool:
        """
        Event-driven TX wait. Base stub returns False immediately.
        Subclasses with event-driven PTT must override and set supports_event_ptt=True.
        """
        return False

    def wait_for_unkey(self, timeout: float) -> bool:
        """
        Event-driven UNKEY wait. Base stub returns False immediately.
        Subclasses with event-driven PTT must override and set supports_event_ptt=True.
        """
        return False

    def shutdown(self, restore: bool = True):
        """Optional cleanup for background threads or listeners."""
        pass
