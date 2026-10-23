"""Tests for the Garmin Connect Personal sensors."""

from unittest.mock import AsyncMock

from aio_garmin_personal import DailySummary
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import ACCOUNT_ID, load_json


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.parametrize(
    ("entity_id", "state", "unit"),
    [
        ("sensor.garmin_connect_total_calories", "655.0", "kcal"),
        ("sensor.garmin_connect_active_calories", "22.0", "kcal"),
        ("sensor.garmin_connect_steps", "418", "steps"),
        ("sensor.garmin_connect_distance", "0.327", "km"),
        ("sensor.garmin_connect_intensity_minutes", "8", "min"),
        ("sensor.garmin_connect_resting_heart_rate", "55", "bpm"),
        ("sensor.garmin_connect_body_battery", "72", None),
        ("sensor.garmin_connect_last_sync", "2026-10-23T06:12:48+00:00", None),
    ],
)
async def test_sensor_states(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_id: str,
    state: str,
    unit: str | None,
) -> None:
    """Test the state and unit of each enabled sensor."""
    await _setup(hass, mock_config_entry)

    sensor = hass.states.get(entity_id)

    assert sensor is not None
    assert sensor.state == state
    assert sensor.attributes.get("unit_of_measurement") == unit


@pytest.mark.parametrize(
    "entity_id",
    [
        "sensor.garmin_connect_resting_calories",
        "sensor.garmin_connect_floors_climbed",
        "sensor.garmin_connect_average_stress",
    ],
)
async def test_niche_sensors_disabled_by_default(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    entity_id: str,
) -> None:
    """Test that the niche sensors are disabled by default."""
    await _setup(hass, mock_config_entry)

    entry = entity_registry.async_get(entity_id)

    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    assert hass.states.get(entity_id) is None


async def test_daily_totals_reset_at_garmin_midnight(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that daily totals reset at midnight in the Garmin time zone."""
    await _setup(hass, mock_config_entry)

    calories = hass.states.get("sensor.garmin_connect_total_calories")
    body_battery = hass.states.get("sensor.garmin_connect_body_battery")

    assert calories is not None
    assert calories.attributes["state_class"] == "total"
    assert calories.attributes["last_reset"] == "2026-10-23T00:00:00+02:00"
    assert body_battery is not None
    assert "last_reset" not in body_battery.attributes


async def test_sensors_unknown_without_summary(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that sensors are unknown when there is no summary."""
    mock_client.async_get_daily_summary.return_value = None

    await _setup(hass, mock_config_entry)

    calories = hass.states.get("sensor.garmin_connect_total_calories")
    assert calories is not None
    assert calories.state == STATE_UNKNOWN
    assert calories.attributes.get("last_reset") is None


async def test_sensors_unknown_for_day_without_data(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that sensors are unknown for a day without data."""
    mock_client.async_get_daily_summary.return_value = DailySummary.from_dict(
        load_json("daily_summary_empty.json")
    )

    await _setup(hass, mock_config_entry)

    calories = hass.states.get("sensor.garmin_connect_total_calories")
    assert calories is not None
    assert calories.state == STATE_UNKNOWN
    assert calories.attributes["last_reset"] == "2026-10-24T00:00:00+02:00"
    assert hass.states.get("sensor.garmin_connect_steps").state == STATE_UNKNOWN
    assert (
        hass.states.get("sensor.garmin_connect_intensity_minutes").state
        == STATE_UNKNOWN
    )


async def test_intensity_minutes_unknown_without_either_value(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that intensity minutes are unknown without either value."""
    summary = load_json("daily_summary.json")
    del summary["moderateIntensityMinutes"], summary["vigorousIntensityMinutes"]
    mock_client.async_get_daily_summary.return_value = DailySummary.from_dict(summary)

    await _setup(hass, mock_config_entry)

    assert (
        hass.states.get("sensor.garmin_connect_intensity_minutes").state
        == STATE_UNKNOWN
    )


async def test_entities_share_one_service_device(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that all entities belong to one service device."""
    await _setup(hass, mock_config_entry)

    device = device_registry.async_get_device_by_identifier(
        ("garmin_connect_personal", ACCOUNT_ID), mock_config_entry.entry_id
    )

    assert device is not None
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.name == "Garmin Connect"
    entities = er.async_entries_for_device(
        entity_registry, device.id, include_disabled_entities=True
    )
    assert {e.unique_id for e in entities} >= {
        f"{ACCOUNT_ID}_total_calories",
        f"{ACCOUNT_ID}_active_calories",
    }
