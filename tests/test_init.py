"""Tests for setting up and polling Garmin Connect Personal."""

from datetime import date, timedelta
from unittest.mock import AsyncMock

from aio_garmin_personal import (
    GarminPersonalAuthenticationError,
    GarminPersonalConnectionError,
    GarminPersonalRateLimitError,
    UserSettings,
)
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.garmin_connect_personal.const import DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH, ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant

TOTAL_CALORIES = "sensor.garmin_connect_total_calories"


async def test_setup_and_unload(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test setting up and unloading an entry."""
    mock_config_entry.add_to_hass(hass)

    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.LOADED

    assert await hass.config_entries.async_unload(mock_config_entry.entry_id)
    assert mock_config_entry.state is ConfigEntryState.NOT_LOADED


async def test_rejected_key_starts_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that a rejected key during setup starts reauthentication."""
    mock_client.async_get_user_settings.side_effect = GarminPersonalAuthenticationError(
        "no"
    )
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    assert mock_config_entry.state is ConfigEntryState.SETUP_ERROR
    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_REAUTH


async def test_unreachable_garmin_retries_setup(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that a connection error during setup retries later."""
    mock_client.async_get_daily_summary.side_effect = GarminPersonalConnectionError(
        "down"
    )
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    assert mock_config_entry.state is ConfigEntryState.SETUP_RETRY


@pytest.mark.parametrize(
    ("time_zone", "now", "expected_day"),
    [
        ("Europe/Warsaw", "2026-10-22T22:30:00+00:00", date(2026, 10, 23)),
        ("America/Chicago", "2026-10-23T03:00:00+00:00", date(2026, 10, 22)),
        ("gmt", "2026-10-22T23:30:00+00:00", date(2026, 10, 22)),
    ],
)
async def test_day_follows_garmin_time_zone(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    time_zone: str,
    now: str,
    expected_day: date,
) -> None:
    """Test that the requested day is today in the Garmin time zone."""
    await hass.config.async_set_time_zone("Pacific/Auckland")
    freezer.move_to(now)
    mock_client.async_get_user_settings.return_value = UserSettings.from_dict(
        {"timeZone": time_zone}
    )
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    mock_client.async_get_daily_summary.assert_awaited_once_with(expected_day)


async def test_missing_time_zone_uses_home_assistant_zone(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that a profile without a time zone uses the Home Assistant zone."""
    await hass.config.async_set_time_zone("Pacific/Auckland")
    freezer.move_to("2026-10-22T12:00:00+00:00")
    mock_client.async_get_user_settings.return_value = UserSettings.from_dict({})
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    mock_client.async_get_daily_summary.assert_awaited_once_with(date(2026, 10, 23))
    assert "Unknown Garmin time zone" not in caplog.text


async def test_unknown_time_zone_uses_home_assistant_zone(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that an unknown time zone uses the Home Assistant zone and warns."""
    await hass.config.async_set_time_zone("Pacific/Auckland")
    freezer.move_to("2026-10-22T12:00:00+00:00")
    mock_client.async_get_user_settings.return_value = UserSettings.from_dict(
        {"timeZone": "Mars/Olympus_Mons"}
    )
    mock_config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    mock_client.async_get_daily_summary.assert_awaited_once_with(date(2026, 10, 23))
    assert "Unknown Garmin time zone Mars/Olympus_Mons" in caplog.text


@pytest.mark.parametrize(
    "error",
    [
        GarminPersonalRateLimitError("slow down", retry_after=120),
        GarminPersonalConnectionError("down"),
    ],
)
async def test_failed_poll_makes_entities_unavailable_until_recovery(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    error: Exception,
) -> None:
    """Test that a failed poll makes entities unavailable until the next success."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    assert hass.states.get(TOTAL_CALORIES).state == "655.0"

    mock_client.async_get_daily_summary.side_effect = error
    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(TOTAL_CALORIES).state == STATE_UNAVAILABLE

    mock_client.async_get_daily_summary.side_effect = None
    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(TOTAL_CALORIES).state == "655.0"


async def test_rejected_key_during_poll_starts_reauth(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that a rejected key during a poll starts reauthentication."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    mock_client.async_get_daily_summary.side_effect = GarminPersonalAuthenticationError(
        "no"
    )
    freezer.tick(timedelta(minutes=10))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_REAUTH
