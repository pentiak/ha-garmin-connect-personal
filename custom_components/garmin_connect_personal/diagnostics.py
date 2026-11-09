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

# When the weight was entered. `samplePk` and `date` are timestamps too.
WEIGHT_TO_REDACT = {"date", "samplePk", "timestampGMT"}

# An activity carries its start and end coordinates, its name, which Garmin often makes
# from the place, its times and the owner. Only the fields the sensors read besides the
# name and start time are kept, so that a field Garmin adds later is left out too.
ACTIVITY_TO_KEEP = ("activityType", "duration", "distance", "calories", "averageHR")


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: GarminConnectPersonalConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry, without the key or account identifiers."""
    daily = entry.runtime_data.daily
    night = entry.runtime_data.sleep
    summary = daily.data.summary
    sleep = night.data.sleep
    hrv = night.data.hrv
    weight = entry.runtime_data.weight
    latest_weight = weight.data.latest
    activity = entry.runtime_data.activity
    latest_activity = activity.data.latest
    return {
        "entry": async_redact_data(entry.data, TO_REDACT),
        "time_zone": str(daily.time_zone),
        "last_update_success": daily.last_update_success,
        "summary": async_redact_data(dict(summary.raw), TO_REDACT) if summary else None,
        "sleep_last_update_success": night.last_update_success,
        "sleep": async_redact_data(dict(sleep.raw), SLEEP_TO_REDACT) if sleep else None,
        "hrv": async_redact_data(dict(hrv.raw), SLEEP_TO_REDACT) if hrv else None,
        "weight_last_update_success": weight.last_update_success,
        "weight": async_redact_data(dict(latest_weight.raw), WEIGHT_TO_REDACT)
        if latest_weight
        else None,
        "activity_last_update_success": activity.last_update_success,
        "activity": {
            key: latest_activity.raw[key]
            for key in ACTIVITY_TO_KEEP
            if key in latest_activity.raw
        }
        if latest_activity
        else None,
    }
