"""Base entity for Garmin Connect Personal."""

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import GarminConnectPersonalCoordinator


class GarminConnectPersonalEntity(CoordinatorEntity[GarminConnectPersonalCoordinator]):
    """An entity of the Garmin account, grouped under one service device."""

    # Garmin's API brand guidelines require every view of its data to name Garmin.
    _attr_attribution = "Data provided by Garmin"
    _attr_has_entity_name = True

    def __init__(self, coordinator: GarminConnectPersonalCoordinator, key: str) -> None:
        """Initialize the entity."""
        super().__init__(coordinator)
        account_id = coordinator.config_entry.unique_id
        assert account_id is not None
        self._attr_unique_id = f"{account_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, account_id)},
            entry_type=DeviceEntryType.SERVICE,
            manufacturer="Garmin",
            model="Garmin Connect",
            name=coordinator.config_entry.title,
            configuration_url="https://connect.garmin.com/",
        )
