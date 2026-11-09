"""Tests for the weight sensors of Garmin Connect Personal."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, call

from aio_garmin_personal import GarminPersonalConnectionError, WeightRange
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

WEIGHT = "sensor.garmin_connect_weight"
TOTAL_CALORIES = "sensor.garmin_connect_total_calories"


@pytest.fixture(autouse=True)
def morning(freezer: FrozenDateTimeFactory) -> None:
    """Run every test on the morning of the fixture day in Berlin."""
    freezer.move_to("2026-10-23T08:00:00+00:00")


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_weight_is_the_latest_entry(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that the weight sensor shows the most recent day's entry, in kilograms."""
    await _setup(hass, mock_config_entry)

    sensor = hass.states.get(WEIGHT)

    assert sensor is not None
    assert sensor.state == "68.35"
    assert sensor.attributes["unit_of_measurement"] == "kg"
    assert sensor.attributes["device_class"] == "weight"
    assert sensor.attributes["state_class"] == "measurement"
    assert mock_client.async_get_weight.await_args_list == [
        call(date(2025, 10, 23), date(2026, 10, 23))
    ]


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
@pytest.mark.parametrize(
    ("entity_id", "state", "unit"),
    [
        ("sensor.garmin_connect_bmi", "22.4", None),
        ("sensor.garmin_connect_body_fat", "18.6", "%"),
        ("sensor.garmin_connect_last_weigh_in", "2026-10-22T06:30:00+00:00", None),
    ],
)
async def test_body_composition_sensors(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_id: str,
    state: str,
    unit: str | None,
) -> None:
    """Test the BMI, body fat and weigh-in time of the latest entry."""
    await _setup(hass, mock_config_entry)

    sensor = hass.states.get(entity_id)

    assert sensor is not None
    assert sensor.state == state
    assert sensor.attributes.get("unit_of_measurement") == unit


@pytest.mark.parametrize(
    "entity_id",
    [
        "sensor.garmin_connect_bmi",
        "sensor.garmin_connect_body_fat",
        "sensor.garmin_connect_last_weigh_in",
    ],
)
async def test_body_composition_disabled_by_default(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    entity_id: str,
) -> None:
    """Test that BMI, body fat and the weigh-in time are disabled by default."""
    await _setup(hass, mock_config_entry)

    entry = entity_registry.async_get(entity_id)

    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_weight_unknown_without_entries(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that the weight is unknown when the last year has no entry."""
    mock_client.async_get_weight.return_value = WeightRange.from_dict({})

    await _setup(hass, mock_config_entry)

    assert hass.states.get(WEIGHT).state == STATE_UNKNOWN


async def test_weight_polls_hourly(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that the weight is fetched again after an hour, not on every daily poll."""
    await _setup(hass, mock_config_entry)

    freezer.tick(timedelta(minutes=50))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.async_get_weight.await_count == 1

    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert mock_client.async_get_weight.await_count == 2


async def test_failed_weight_poll_leaves_daily_sensors_available(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that a failing weight poll makes only the weight sensors unavailable."""
    await _setup(hass, mock_config_entry)
    mock_client.async_get_weight.side_effect = GarminPersonalConnectionError

    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(WEIGHT).state == STATE_UNAVAILABLE
    assert hass.states.get(TOTAL_CALORIES).state == "655.0"
