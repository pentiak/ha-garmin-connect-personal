"""Tests for the import of the daily totals into external statistics."""

import asyncio
from datetime import date, datetime, timedelta
from functools import partial
from typing import Any
from unittest.mock import AsyncMock

from aio_garmin_personal import (
    DailyOverview,
    GarminPersonalAuthenticationError,
    GarminPersonalConnectionError,
    UserSettings,
)
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.garmin_connect_personal.const import DOMAIN
from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.statistics import (
    get_metadata,
    statistics_during_period,
)
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from .conftest import load_json

STEPS = "garmin_connect_personal:123456789_steps"
TOTAL_CALORIES = "garmin_connect_personal:123456789_total_calories"
INTENSITY = "garmin_connect_personal:123456789_intensity_minutes"
RANGE_START = datetime.fromisoformat("2023-01-01T00:00:00+00:00")


def _day(day: date, **changes: Any) -> DailyOverview:
    """Return the fixture day for another date, with the given top-level fields."""
    return DailyOverview.from_dict(
        load_json("daily_overview.json") | {"calendarDate": day.isoformat()} | changes
    )


def _steps(day: date, steps: int | None) -> DailyOverview:
    """Return the fixture day for another date with another step count."""
    movement = load_json("daily_overview.json")["movement"]
    return _day(day, movement=movement | {"steps": {"value": steps}})


class FakeGarminHistory:
    """Answers each requested range with the days currently set in it."""

    def __init__(self, client: AsyncMock) -> None:
        """Route the mock client's range requests to this object."""
        self.days: dict[date, DailyOverview] = {}
        self.requests: list[tuple[date, date]] = []
        client.async_get_daily_overviews.side_effect = self._get

    async def _get(self, start: date, end: date) -> list[DailyOverview]:
        """Return the days from `start` to `end`, as Garmin would."""
        self.requests.append((start, end))
        return [day for when, day in sorted(self.days.items()) if start <= when <= end]


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Recorder, enable_custom_integrations: None
) -> None:
    """Start the recorder before Home Assistant, as the harness requires."""


@pytest.fixture(autouse=True)
def morning(freezer: FrozenDateTimeFactory) -> None:
    """Run every test on the morning of the fixture day in Berlin."""
    freezer.move_to("2026-10-23T08:00:00+00:00")


@pytest.fixture
def history(mock_client: AsyncMock) -> FakeGarminHistory:
    """Return the range answers of the mock client."""
    return FakeGarminHistory(mock_client)


async def _settle(hass: HomeAssistant) -> None:
    """Wait for the import, which runs as a background task, and its recorder jobs."""
    await hass.async_block_till_done(wait_background_tasks=True)
    await async_wait_recording_done(hass)


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await _settle(hass)


async def _next_run(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await _settle(hass)


async def _rows(
    hass: HomeAssistant, statistic_id: str
) -> list[tuple[datetime, float, float]]:
    """Return the UTC start, state and sum of each row of an external statistic."""
    result = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        RANGE_START,
        None,
        {statistic_id},
        "hour",
        None,
        {"state", "sum"},
    )
    return [
        (dt_util.utc_from_timestamp(row["start"]), row["state"], row["sum"])
        for row in result.get(statistic_id, [])
    ]


def _at(value: str) -> datetime:
    """Return an ISO time as a datetime."""
    return datetime.fromisoformat(value)


async def test_first_import_covers_three_years_a_month_at_a_time(
    hass: HomeAssistant,
    history: FakeGarminHistory,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that the first run requests three years up to yesterday, 31 days at a time."""
    await _setup(hass, mock_config_entry)

    assert history.requests[0] == (date(2023, 10, 23), date(2023, 11, 22))
    assert history.requests[-1][1] == date(2026, 10, 22)
    assert len(history.requests) == 36
    for (_, end), (start, _) in zip(
        history.requests, history.requests[1:], strict=False
    ):
        assert start == end + timedelta(days=1)


async def test_days_are_imported_at_noon_with_running_sums(
    hass: HomeAssistant,
    history: FakeGarminHistory,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test one row per day at noon in the Garmin zone, summed over the days."""
    history.days[date(2026, 10, 21)] = _steps(date(2026, 10, 21), 5000)
    history.days[date(2026, 10, 22)] = _steps(date(2026, 10, 22), 9120)

    await _setup(hass, mock_config_entry)

    # Noon in Berlin is 10:00 UTC on these days.
    assert (await _rows(hass, STEPS)) == [
        (_at("2026-10-21T10:00:00+00:00"), 5000.0, 5000.0),
        (_at("2026-10-22T10:00:00+00:00"), 9120.0, 14120.0),
    ]
    assert (await _rows(hass, INTENSITY)) == [
        (_at("2026-10-21T10:00:00+00:00"), 50.0, 50.0),
        (_at("2026-10-22T10:00:00+00:00"), 50.0, 100.0),
    ]
    metadata = await get_instance(hass).async_add_executor_job(
        partial(get_metadata, hass, statistic_ids={STEPS, TOTAL_CALORIES})
    )
    assert metadata[STEPS][1]["name"] == "Garmin Connect Steps"
    assert metadata[STEPS][1]["source"] == DOMAIN
    assert metadata[STEPS][1]["unit_of_measurement"] is None
    assert metadata[TOTAL_CALORIES][1]["unit_of_measurement"] == "kcal"
    assert metadata[TOTAL_CALORIES][1]["unit_class"] == "energy"


async def test_half_hour_zone_rounds_down_to_the_hour(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    history: FakeGarminHistory,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that noon in a zone with a half-hour offset gives a row on the hour."""
    mock_client.async_get_user_settings.return_value = UserSettings.from_dict(
        load_json("user_settings.json") | {"timeZone": "Asia/Kolkata"}
    )
    history.days[date(2026, 10, 22)] = _steps(date(2026, 10, 22), 9120)

    await _setup(hass, mock_config_entry)

    # Noon in Kolkata is 06:30 UTC.
    assert (await _rows(hass, STEPS)) == [
        (_at("2026-10-22T06:00:00+00:00"), 9120.0, 9120.0)
    ]


async def test_days_without_wellness_data_and_null_values_add_no_row(
    hass: HomeAssistant,
    history: FakeGarminHistory,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that only days with wellness data count, and a null value is skipped."""
    history.days[date(2026, 10, 19)] = _day(
        date(2026, 10, 19), includesWellnessData=False
    )
    history.days[date(2026, 10, 20)] = _steps(date(2026, 10, 20), 4000)
    history.days[date(2026, 10, 21)] = _steps(date(2026, 10, 21), None)
    history.days[date(2026, 10, 22)] = _day(date(2026, 10, 22), intensityMinutes={})

    await _setup(hass, mock_config_entry)

    assert (await _rows(hass, STEPS)) == [
        (_at("2026-10-20T10:00:00+00:00"), 4000.0, 4000.0),
        (_at("2026-10-22T10:00:00+00:00"), 9120.0, 13120.0),
    ]
    assert [row[0] for row in (await _rows(hass, INTENSITY))] == [
        _at("2026-10-20T10:00:00+00:00"),
        _at("2026-10-21T10:00:00+00:00"),
    ]
    assert len(await _rows(hass, TOTAL_CALORIES)) == 3


async def test_later_runs_import_the_last_week_again(
    hass: HomeAssistant,
    history: FakeGarminHistory,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that each run replaces the last week and continues the sum before it."""
    history.days[date(2026, 10, 10)] = _steps(date(2026, 10, 10), 1000)
    history.days[date(2026, 10, 21)] = _steps(date(2026, 10, 21), 5000)
    history.days[date(2026, 10, 22)] = _steps(date(2026, 10, 22), 6000)
    await _setup(hass, mock_config_entry)
    history.requests.clear()

    # A late sync adds to the day before.
    history.days[date(2026, 10, 22)] = _steps(date(2026, 10, 22), 9120)
    await _next_run(hass, freezer)

    assert history.requests == [(date(2026, 10, 15), date(2026, 10, 22))]
    assert (await _rows(hass, STEPS)) == [
        (_at("2026-10-10T10:00:00+00:00"), 1000.0, 1000.0),
        (_at("2026-10-21T10:00:00+00:00"), 5000.0, 6000.0),
        (_at("2026-10-22T10:00:00+00:00"), 9120.0, 15120.0),
    ]

    # The next day, which ends in winter time: noon is 11:00 UTC.
    history.requests.clear()
    history.days[date(2026, 10, 25)] = _steps(date(2026, 10, 25), 3000)
    freezer.move_to("2026-10-26T08:00:00+00:00")
    async_fire_time_changed(hass)
    await _settle(hass)

    assert history.requests == [(date(2026, 10, 15), date(2026, 10, 25))]
    assert (await _rows(hass, STEPS))[-1] == (
        _at("2026-10-25T11:00:00+00:00"),
        3000.0,
        18120.0,
    )


async def test_failure_is_logged_once_and_retried(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    history: FakeGarminHistory,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Test that a failing import logs one warning, and imports when Garmin answers."""
    history.days[date(2026, 10, 22)] = _steps(date(2026, 10, 22), 9120)
    mock_client.async_get_daily_overviews.side_effect = GarminPersonalConnectionError(
        "down"
    )
    await _setup(hass, mock_config_entry)
    await _next_run(hass, freezer)

    assert caplog.text.count("Could not import the history from Garmin: down") == 1
    assert await _rows(hass, STEPS) == []

    mock_client.async_get_daily_overviews.side_effect = history._get
    await _next_run(hass, freezer)

    assert "Importing the history from Garmin works again" in caplog.text
    assert len(await _rows(hass, STEPS)) == 1


async def test_rejected_key_starts_reauth(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that a rejected key during the import starts reauthentication."""
    mock_client.async_get_daily_overviews.side_effect = (
        GarminPersonalAuthenticationError("no")
    )

    await _setup(hass, mock_config_entry)

    (flow,) = hass.config_entries.flow.async_progress_by_handler(DOMAIN)
    assert flow["context"]["source"] == SOURCE_REAUTH


async def test_run_still_going_skips_the_next(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    history: FakeGarminHistory,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that an hourly run does nothing while the previous one is still going."""
    release = asyncio.Event()

    async def _slow(start: date, end: date) -> list[DailyOverview]:
        """Wait until released before answering."""
        history.requests.append((start, end))
        await release.wait()
        return []

    mock_client.async_get_daily_overviews.side_effect = _slow
    mock_config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()

    freezer.tick(timedelta(hours=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert len(history.requests) == 1
    release.set()
    await _settle(hass)


async def test_removing_the_entry_clears_the_statistics(
    hass: HomeAssistant,
    history: FakeGarminHistory,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that the imported statistics are deleted with the entry."""
    history.days[date(2026, 10, 22)] = _steps(date(2026, 10, 22), 9120)
    await _setup(hass, mock_config_entry)
    assert len(await _rows(hass, STEPS)) == 1

    await hass.config_entries.async_remove(mock_config_entry.entry_id)
    await _settle(hass)

    assert await _rows(hass, STEPS) == []
