"""The Garmin Connect Personal integration."""

from datetime import date, datetime

from aio_garmin_personal import GarminPersonalClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.recorder import get_instance

from .const import HISTORY_UPDATE_INTERVAL
from .coordinator import (
    GarminConnectPersonalActivityCoordinator,
    GarminConnectPersonalCoordinator,
    GarminConnectPersonalRuntimeData,
    GarminConnectPersonalSleepCoordinator,
    GarminConnectPersonalWeightCoordinator,
)
from .history import GarminConnectPersonalHistory, history_statistic_ids

PLATFORMS: list[Platform] = [Platform.SENSOR]

type GarminConnectPersonalConfigEntry = ConfigEntry[GarminConnectPersonalRuntimeData]


async def async_setup_entry(
    hass: HomeAssistant, entry: GarminConnectPersonalConfigEntry
) -> bool:
    """Set up Garmin Connect Personal from a config entry."""
    client = GarminPersonalClient(
        async_get_clientsession(hass), entry.data[CONF_API_KEY]
    )
    daily = GarminConnectPersonalCoordinator(hass, entry, client)
    await daily.async_config_entry_first_refresh()
    sleep = GarminConnectPersonalSleepCoordinator(hass, entry, client, daily.time_zone)
    await sleep.async_config_entry_first_refresh()
    weight = GarminConnectPersonalWeightCoordinator(
        hass, entry, client, daily.time_zone
    )
    activity = GarminConnectPersonalActivityCoordinator(hass, entry, client)
    # Weight and the last activity are the least needed; a failure leaves only their
    # sensors unavailable.
    await weight.async_refresh()
    await activity.async_refresh()
    entry.runtime_data = GarminConnectPersonalRuntimeData(
        daily=daily, sleep=sleep, weight=weight, activity=activity
    )

    last_seen: tuple[date, datetime | None] | None = None
    if daily.data.summary is not None:
        last_seen = (daily.data.summary.calendar_date, daily.data.summary.last_sync)

    @callback
    def _async_refresh_after_sync() -> None:
        """Refresh sleep, HRV and the last activity after a sync or at a new day."""
        nonlocal last_seen
        if (summary := daily.data.summary) is None:
            return
        seen = (summary.calendar_date, summary.last_sync)
        if seen != last_seen:
            last_seen = seen
            entry.async_create_background_task(
                hass, sleep.async_request_refresh(), "refresh sleep after sync"
            )
            entry.async_create_background_task(
                hass, activity.async_request_refresh(), "refresh activity after sync"
            )

    entry.async_on_unload(daily.async_add_listener(_async_refresh_after_sync))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    if "recorder" in hass.config.components:
        history = GarminConnectPersonalHistory(hass, entry, client, daily.time_zone)

        @callback
        def _async_import_history(_now: datetime | None = None) -> None:
            """Import the daily totals that are new or may have changed."""
            entry.async_create_background_task(
                hass, history.async_import(), "import history"
            )

        _async_import_history()
        entry.async_on_unload(
            async_track_time_interval(
                hass, _async_import_history, HISTORY_UPDATE_INTERVAL
            )
        )
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GarminConnectPersonalConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def async_remove_entry(
    hass: HomeAssistant, entry: GarminConnectPersonalConfigEntry
) -> None:
    """Remove the daily totals imported for the entry from long-term statistics."""
    if "recorder" in hass.config.components:
        get_instance(hass).async_clear_statistics(history_statistic_ids(entry))
