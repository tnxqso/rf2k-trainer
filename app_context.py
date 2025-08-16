# app_context.py
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, Optional, Set

from typing import Protocol, Any
class LoggerLike(Protocol):
    def debug(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def info(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def warning(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def error(self, msg: str, *args: Any, **kwargs: Any) -> None: ...
    def exception(self, msg: str, *args: Any, **kwargs: Any) -> None: ...


@dataclass
class AppContext:
    """Lightweight container for state shared across the run."""
    logger: LoggerLike
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
