"""Tests for the last activity sensors of Garmin Connect Personal."""

from datetime import timedelta
from unittest.mock import AsyncMock

from aio_garmin_personal import (
    DailySummary,
    GarminPersonalAuthenticationError,
    GarminPersonalConnectionError,
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

from .conftest import load_json

LAST_ACTIVITY = "sensor.garmin_connect_last_activity"
TOTAL_CALORIES = "sensor.garmin_connect_total_calories"
SLEEP_SCORE = "sensor.garmin_connect_sleep_score"
WEIGHT = "sensor.garmin_connect_weight"


@pytest.fixture(autouse=True)
def morning(freezer: FrozenDateTimeFactory) -> None:
    """Run every test on the morning of the fixture day in Berlin."""
    freezer.move_to("2026-10-23T08:00:00+00:00")


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_newest_activity_is_requested(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that the sensors show the first activity of Garmin's list."""
    await _setup(hass, mock_config_entry)

    assert hass.states.get(LAST_ACTIVITY).state == "Morning Run"
    mock_client.async_get_activities.assert_awaited_once_with(limit=1)


async def test_last_activity_unknown_without_activities(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that the sensors are unknown for an account without activities."""
    mock_client.async_get_activities.return_value = []

    await _setup(hass, mock_config_entry)

    assert hass.states.get(LAST_ACTIVITY).state == STATE_UNKNOWN


async def test_new_sync_refreshes_last_activity(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that the last activity is fetched again after a sync, and not without one."""
    await _setup(hass, mock_config_entry)

    await _poll(hass, freezer)

    assert mock_client.async_get_activities.await_count == 1

    mock_client.async_get_daily_summary.return_value = DailySummary.from_dict(
        load_json("daily_summary.json")
        | {"lastSyncTimestampGMT": "2026-10-23T08:05:00.0"}
    )
    await _poll(hass, freezer)

    assert mock_client.async_get_activities.await_count == 2


async def test_last_activity_polls_hourly_without_sync(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that the last activity is fetched every hour even when no sync is seen."""
    await _setup(hass, mock_config_entry)

    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert mock_client.async_get_activities.await_count == 2


async def test_failed_activity_poll_leaves_other_sensors_available(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that a failing activity poll makes only the activity sensors unavailable."""
    await _setup(hass, mock_config_entry)
    mock_client.async_get_activities.side_effect = GarminPersonalConnectionError

    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(LAST_ACTIVITY).state == STATE_UNAVAILABLE
    assert hass.states.get(TOTAL_CALORIES).state == "655.0"
    assert hass.states.get(SLEEP_SCORE).state == "81"
    assert hass.states.get(WEIGHT).state == "68.35"


async def test_failed_first_activity_request_does_not_block_setup(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that setup goes on without the last activity, which appears later."""
    mock_client.async_get_activities.side_effect = GarminPersonalConnectionError

    await _setup(hass, mock_config_entry)

    assert mock_config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get(TOTAL_CALORIES).state == "655.0"
    assert hass.states.get(LAST_ACTIVITY).state == STATE_UNAVAILABLE
    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )
    assert diagnostics["activity"] is None
    assert diagnostics["activity_last_update_success"] is False

    mock_client.async_get_activities.side_effect = None
    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(LAST_ACTIVITY).state == "Morning Run"


async def test_rejected_key_on_first_activity_request_starts_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that a rejected key on the first activity request starts reauthentication."""
    mock_client.async_get_activities.side_effect = GarminPersonalAuthenticationError(
        "no"
    )

    await _setup(hass, mock_config_entry)

    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_REAUTH
