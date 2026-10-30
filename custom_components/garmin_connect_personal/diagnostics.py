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

# When the night started and ended, and when it was scored, are as personal as the
# activity times above. The sleep `id` is the start time. No sensor reads any of them.
SLEEP_TO_REDACT = {
    "autoSleepEndTimestampGMT",
    "autoSleepStartTimestampGMT",
    "createTimeStamp",
    "dailyNapDTOS",
    "deviceId",
    "id",
    "sleepEndTimestampGMT",
    "sleepEndTimestampLocal",
    "sleepStartTimestampGMT",
    "sleepStartTimestampLocal",
    "timestampGmt",
    "userProfilePK",
    "userProfilePk",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GarminConnectPersonalConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry, without the key or account identifiers."""
    daily = entry.runtime_data.daily
    night = entry.runtime_data.sleep
    summary = daily.data.summary
    sleep = night.data.sleep
    hrv = night.data.hrv
    return {
        "entry": async_redact_data(entry.data, TO_REDACT),
        "time_zone": str(daily.time_zone),
        "last_update_success": daily.last_update_success,
        "summary": async_redact_data(dict(summary.raw), TO_REDACT) if summary else None,
        "sleep_last_update_success": night.last_update_success,
        "sleep": async_redact_data(dict(sleep.raw), SLEEP_TO_REDACT) if sleep else None,
        "hrv": async_redact_data(dict(hrv.raw), SLEEP_TO_REDACT) if hrv else None,
    }
