"""Configuration validation helpers for RF2K-TRAINER."""
from typing import Any


class ConfigValidationError(Exception):
    pass


def validate_rigctl_settings(ctx: Any, logger) -> None:
    """Validate rigctl specific settings early and loudly.

    - Require 'rigctld_model' for rigctl backends.
    - Hint how to get model IDs.
    """
    rs = getattr(ctx, 'radio_settings', {}) or {}
    radio_type = (rs.get('type') or 'flex').lower()
    if radio_type != 'rigctl':
        return

    model = rs.get('rigctld_model', None)
    if model in (None, '', 0):
        msg = (
            "Configuration error: 'rigctld_model' is required for rigctl backends.\n"
            "→ Set it in your settings.yml under the radio section.\n"
            "→ Example: rigctld_model: 1, Hamlib Dummy\n"
            "→ Use 'rigctl -l' to list supported model numbers for your radio."
        )
        logger.error(msg)
        raise ConfigValidationError(msg)
