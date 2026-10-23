"""The Garmin Connect Personal integration."""

from aio_garmin_personal import GarminPersonalClient

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_API_KEY, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .coordinator import GarminConnectPersonalCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type GarminConnectPersonalConfigEntry = ConfigEntry[GarminConnectPersonalCoordinator]


async def async_setup_entry(
    hass: HomeAssistant, entry: GarminConnectPersonalConfigEntry
) -> bool:
    """Set up Garmin Connect Personal from a config entry."""
    client = GarminPersonalClient(
        async_get_clientsession(hass), entry.data[CONF_API_KEY]
    )
    coordinator = GarminConnectPersonalCoordinator(hass, entry, client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: GarminConnectPersonalConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
