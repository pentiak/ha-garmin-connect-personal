"""Tests for the sleep and HRV sensors of Garmin Connect Personal."""

from datetime import date, timedelta
from unittest.mock import AsyncMock, call

from aio_garmin_personal import (
    DailyHrv,
    DailySleep,
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

from custom_components.garmin_connect_personal.const import DOMAIN
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er

from .conftest import load_json

TODAY = date(2026, 10, 23)
YESTERDAY = date(2026, 10, 22)
SLEEP_SCORE = "sensor.garmin_connect_sleep_score"
HRV_STATUS = "sensor.garmin_connect_hrv_status"
TOTAL_CALORIES = "sensor.garmin_connect_total_calories"


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


@pytest.mark.parametrize(
    ("entity_id", "state", "unit"),
    [
        (SLEEP_SCORE, "81", None),
        ("sensor.garmin_connect_sleep_duration", "7.5", "h"),
        ("sensor.garmin_connect_hrv_last_night", "52", "ms"),
        (HRV_STATUS, "balanced", None),
    ],
)
async def test_sleep_sensor_states(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_id: str,
    state: str,
    unit: str | None,
) -> None:
    """Test the state and unit of each enabled sleep and HRV sensor."""
    await _setup(hass, mock_config_entry)

    sensor = hass.states.get(entity_id)

    assert sensor is not None
    assert sensor.state == state
    assert sensor.attributes.get("unit_of_measurement") == unit
    mock_client.async_get_sleep.assert_awaited_once_with(TODAY)
    mock_client.async_get_hrv.assert_awaited_once_with(TODAY)


async def test_hrv_status_options(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that the HRV status offers the statuses of Garmin's API."""
    await _setup(hass, mock_config_entry)

    sensor = hass.states.get(HRV_STATUS)

    assert sensor is not None
    assert sensor.attributes["options"] == [
        "none",
        "poor",
        "low",
        "unbalanced",
        "balanced",
        "invalid",
    ]


@pytest.mark.parametrize(
    "entity_id",
    [
        "sensor.garmin_connect_deep_sleep",
        "sensor.garmin_connect_light_sleep",
        "sensor.garmin_connect_rem_sleep",
        "sensor.garmin_connect_awake_time",
        "sensor.garmin_connect_hrv_weekly_average",
    ],
)
async def test_sleep_details_disabled_by_default(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    entity_registry: er.EntityRegistry,
    entity_id: str,
) -> None:
    """Test that the sleep stages and the weekly HRV are disabled by default."""
    await _setup(hass, mock_config_entry)

    entry = entity_registry.async_get(entity_id)

    assert entry is not None
    assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_night_before_until_last_night_is_there(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    sleep: DailySleep,
    hrv: DailyHrv,
) -> None:
    """Test that the night before is shown while Garmin has nothing for last night."""
    mock_client.async_get_sleep.side_effect = lambda day: (
        sleep if day == YESTERDAY else None
    )
    mock_client.async_get_hrv.side_effect = lambda day: (
        hrv if day == YESTERDAY else None
    )

    await _setup(hass, mock_config_entry)

    assert hass.states.get(SLEEP_SCORE).state == "81"
    assert hass.states.get(HRV_STATUS).state == "balanced"
    assert mock_client.async_get_sleep.await_args_list == [
        call(TODAY),
        call(YESTERDAY),
    ]
    assert mock_client.async_get_hrv.await_args_list == [call(TODAY), call(YESTERDAY)]


async def test_hrv_without_summary_falls_back(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that HRV readings without a summary count as no HRV for that night."""
    without_summary = DailyHrv.from_dict(load_json("hrv.json") | {"hrvSummary": None})
    mock_client.async_get_hrv.side_effect = [without_summary, None]

    await _setup(hass, mock_config_entry)

    assert hass.states.get(HRV_STATUS).state == STATE_UNKNOWN
    assert hass.states.get("sensor.garmin_connect_hrv_last_night").state == (
        STATE_UNKNOWN
    )


async def test_sleep_sensors_unknown_without_either_night(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that the sensors are unknown when Garmin has neither night."""
    mock_client.async_get_sleep.return_value = None
    mock_client.async_get_hrv.return_value = None

    await _setup(hass, mock_config_entry)

    assert hass.states.get(SLEEP_SCORE).state == STATE_UNKNOWN
    assert hass.states.get(HRV_STATUS).state == STATE_UNKNOWN


async def test_unknown_hrv_status_is_unknown(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that a status missing from Garmin's API document leaves the sensor unknown."""
    data = load_json("hrv.json")
    data["hrvSummary"] = data["hrvSummary"] | {"status": "SOMETHING_NEW"}
    mock_client.async_get_hrv.return_value = DailyHrv.from_dict(data)

    await _setup(hass, mock_config_entry)

    assert hass.states.get(HRV_STATUS).state == STATE_UNKNOWN


async def test_new_sync_refreshes_sleep(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that sleep is fetched again after a sync, and not on polls without one."""
    await _setup(hass, mock_config_entry)

    await _poll(hass, freezer)

    assert mock_client.async_get_sleep.await_count == 1

    mock_client.async_get_daily_summary.return_value = DailySummary.from_dict(
        load_json("daily_summary.json")
        | {"lastSyncTimestampGMT": "2026-10-23T08:05:00.0"}
    )
    await _poll(hass, freezer)

    assert mock_client.async_get_sleep.await_count == 2
    assert mock_client.async_get_hrv.await_count == 2


async def test_day_without_summary_does_not_refresh_sleep(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that a poll without a daily summary does not count as a sync."""
    await _setup(hass, mock_config_entry)

    mock_client.async_get_daily_summary.return_value = None
    await _poll(hass, freezer)

    assert mock_client.async_get_sleep.await_count == 1
    assert hass.states.get(SLEEP_SCORE).state == "81"


async def test_sleep_polls_hourly_without_sync(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that sleep is fetched every hour even when no sync is seen."""
    await _setup(hass, mock_config_entry)

    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert mock_client.async_get_sleep.await_count == 2


async def test_failed_sleep_poll_leaves_daily_sensors_available(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that a failing sleep endpoint makes only the sleep sensors unavailable."""
    await _setup(hass, mock_config_entry)

    mock_client.async_get_sleep.side_effect = GarminPersonalConnectionError("down")
    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get(SLEEP_SCORE).state == STATE_UNAVAILABLE
    assert hass.states.get(HRV_STATUS).state == STATE_UNAVAILABLE
    assert hass.states.get(TOTAL_CALORIES).state == "655.0"


async def test_rejected_key_during_sleep_poll_starts_reauth(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that a rejected key while polling sleep starts reauthentication."""
    await _setup(hass, mock_config_entry)

    mock_client.async_get_sleep.side_effect = GarminPersonalAuthenticationError("no")
    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_REAUTH
