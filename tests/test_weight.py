"""Tests for the weight sensors of Garmin Connect Personal."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, call

from aio_garmin_personal import (
    GarminPersonalAuthenticationError,
    GarminPersonalConnectionError,
    WeightRange,
)
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.garmin_connect_personal.const import DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant

WEIGHT = "sensor.garmin_connect_weight"
TOTAL_CALORIES = "sensor.garmin_connect_total_calories"
SLEEP_SCORE = "sensor.garmin_connect_sleep_score"


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


async def test_failed_first_weight_request_does_not_block_setup(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that setup goes on without weight, and weight appears once Garmin answers."""
    mock_client.async_get_weight.side_effect = GarminPersonalConnectionError

    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(TOTAL_CALORIES).state == "655.0"
    assert hass.states.get(SLEEP_SCORE).state == "81"
    assert hass.states.get(WEIGHT).state == STATE_UNAVAILABLE
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )
    assert diagnostics["weight"] is None
    assert diagnostics["weight_last_update_success"] is False

    mock_client.async_get_weight.side_effect = None
    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(WEIGHT).state == "68.35"


async def test_rejected_key_on_first_weight_request_starts_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that a rejected key on the first weight request starts reauthentication."""
    mock_client.async_get_weight.side_effect = GarminPersonalAuthenticationError("no")

    await _setup(hass, mock_config_entry)

    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_REAUTH
