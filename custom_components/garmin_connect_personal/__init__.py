"""The Garmin Connect Personal integration."""

from datetime import date, datetime

from aio_garmin_personal import GarminPersonalClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .coordinator import (
    GarminConnectPersonalCoordinator,
    GarminConnectPersonalRuntimeData,
    GarminConnectPersonalSleepCoordinator,
)

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
    entry.runtime_data = GarminConnectPersonalRuntimeData(daily=daily, sleep=sleep)

    last_seen: tuple[date, datetime | None] | None = None
    if daily.data.summary is not None:
        last_seen = (daily.data.summary.calendar_date, daily.data.summary.last_sync)

    @callback
    def _async_refresh_sleep_after_sync() -> None:
        """Refresh sleep and HRV when the watch has synced or a new day has started."""
        nonlocal last_seen
        if (summary := daily.data.summary) is None:
            return
        seen = (summary.calendar_date, summary.last_sync)
        if seen != last_seen:
            last_seen = seen
            entry.async_create_background_task(
                hass, sleep.async_request_refresh(), "refresh sleep after sync"
            )

    entry.async_on_unload(daily.async_add_listener(_async_refresh_sleep_after_sync))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GarminConnectPersonalConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
