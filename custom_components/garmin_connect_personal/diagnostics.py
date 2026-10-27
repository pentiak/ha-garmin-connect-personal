"""Diagnostics support for Garmin Connect Personal."""

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant

from . import GarminConnectPersonalConfigEntry

# The activity event list names the watch and the activities, and when they took place.
# No sensor reads it.
TO_REDACT = {
    CONF_API_KEY,
    "bodyBatteryActivityEventList",
    "displayName",
    "userProfileId",
    "userDailySummaryId",
    "uuid",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GarminConnectPersonalConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry, without the key or account identifiers."""
    coordinator = entry.runtime_data
    summary = coordinator.data.summary
    return {
        "entry": async_redact_data(entry.data, TO_REDACT),
        "time_zone": str(coordinator.time_zone),
        "last_update_success": coordinator.last_update_success,
        "summary": async_redact_data(dict(summary.raw), TO_REDACT) if summary else None,
    }
