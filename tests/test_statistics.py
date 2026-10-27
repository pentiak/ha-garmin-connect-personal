"""Tests for the correction of the day before in the long-term statistics."""

from datetime import date, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock

from aio_garmin_personal import DailySummary
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
    do_adhoc_statistics,
)

from homeassistant.components.recorder import Recorder
from homeassistant.components.recorder.statistics import statistic_during_period
from homeassistant.core import HomeAssistant
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from .conftest import load_json

STEPS = "sensor.garmin_connect_steps"
DISTANCE = "sensor.garmin_connect_distance"

# The fixture account's zone is Europe/Berlin, UTC+2 on these days.
DAY_BEFORE = date(2026, 10, 23)
DAY_BEFORE_START = datetime.fromisoformat("2026-10-22T22:00:00+00:00")
MIDNIGHT = datetime.fromisoformat("2026-10-23T22:00:00+00:00")
DAY_AFTER_END = datetime.fromisoformat("2026-10-24T22:00:00+00:00")


def _summary(
    day: date, steps: int | None, meters: int | None, *, synced: bool = True
) -> DailySummary:
    """Return the fixture summary for another day and totals."""
    return DailySummary.from_dict(
        load_json("daily_summary.json")
        | {
            "calendarDate": day.isoformat(),
            "totalSteps": steps,
            "totalDistanceMeters": meters,
            "lastSyncTimestampGMT": "2026-10-23T06:12:48.317" if synced else None,
        }
    )


class FakeGarminDays:
    """Answers each requested day with the summary currently set for it."""

    def __init__(self, client: AsyncMock) -> None:
        """Route the mock client's daily summary requests to this object."""
        self.days: dict[date, DailySummary] = {}
        self.requests: list[date] = []
        client.async_get_daily_summary.side_effect = self._get

    async def _get(self, day: date) -> DailySummary:
        self.requests.append(day)
        return self.days[day]


async def _change(hass: HomeAssistant, statistic_id: str, start: datetime) -> Any:
    """Return the change of a statistic over the Garmin day that starts at `start`."""
    result = await get_instance(hass).async_add_executor_job(
        statistic_during_period,
        hass,
        start,
        start + timedelta(days=1),
        statistic_id,
        {"change"},
        None,
    )
    return result["change"]


async def _poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory, at: str) -> None:
    freezer.move_to(at)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)


async def _compile(
    hass: HomeAssistant, freezer: FrozenDateTimeFactory, *starts: str
) -> None:
    """Compile the given 5-minute periods once they have ended, as the recorder does."""
    for start in starts:
        period = datetime.fromisoformat(start)
        freezer.move_to(max(dt_util.utcnow(), period + timedelta(minutes=5)))
        do_adhoc_statistics(hass, start=period)
    await async_wait_recording_done(hass)


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    recorder_mock: Recorder, enable_custom_integrations: None
) -> None:
    """Start the recorder before Home Assistant, as the harness requires."""


@pytest.fixture
def garmin_days(mock_client: AsyncMock) -> FakeGarminDays:
    """Return the per-day answers of the mock client."""
    return FakeGarminDays(mock_client)


async def test_late_sync_corrects_the_day_before(
    hass: HomeAssistant,
    garmin_days: FakeGarminDays,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that data synced after midnight ends up in the day it belongs to."""
    garmin_days.days[date(2026, 10, 22)] = _summary(date(2026, 10, 22), None, None)
    garmin_days.days[DAY_BEFORE] = _summary(DAY_BEFORE, 1000, 800)
    freezer.move_to("2026-10-23T20:30:00+00:00")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await async_wait_recording_done(hass)

    # The last sync before midnight.
    garmin_days.days[DAY_BEFORE] = _summary(DAY_BEFORE, 1200, 1100)
    await _poll(hass, freezer, "2026-10-23T21:40:00+00:00")
    await _compile(
        hass,
        freezer,
        "2026-10-23T20:30:00+00:00",
        "2026-10-23T20:55:00+00:00",
        "2026-10-23T21:40:00+00:00",
        "2026-10-23T21:55:00+00:00",
    )
    assert await _change(hass, STEPS, DAY_BEFORE_START) == 200
    assert await _change(hass, DISTANCE, DAY_BEFORE_START) == pytest.approx(0.3)

    # The watch syncs after midnight: the rest of the day before, and the new day.
    garmin_days.days[DAY_BEFORE] = _summary(DAY_BEFORE, 1500, 1400)
    garmin_days.days[date(2026, 10, 24)] = _summary(date(2026, 10, 24), 50, 40)
    await _poll(hass, freezer, "2026-10-23T22:20:00+00:00")
    await _compile(hass, freezer, "2026-10-23T22:20:00+00:00")

    assert await _change(hass, STEPS, DAY_BEFORE_START) == 1500
    assert await _change(hass, DISTANCE, DAY_BEFORE_START) == pytest.approx(1.4)
    assert await _change(hass, STEPS, MIDNIGHT) == 50
    assert await _change(hass, DISTANCE, MIDNIGHT) == pytest.approx(0.04)

    # Today has synced, so the day before is final and no longer requested.
    garmin_days.requests.clear()
    await _poll(hass, freezer, "2026-10-23T22:30:00+00:00")
    assert garmin_days.requests == [date(2026, 10, 24)]


async def test_correction_is_not_repeated_after_a_reload(
    hass: HomeAssistant,
    garmin_days: FakeGarminDays,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that the day before is corrected once, also across a reload."""
    garmin_days.days[date(2026, 10, 22)] = _summary(date(2026, 10, 22), None, None)
    garmin_days.days[DAY_BEFORE] = _summary(DAY_BEFORE, 1000, 800)
    freezer.move_to("2026-10-23T20:30:00+00:00")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    garmin_days.days[DAY_BEFORE] = _summary(DAY_BEFORE, 1200, 1100)
    await _poll(hass, freezer, "2026-10-23T21:40:00+00:00")
    await _compile(
        hass,
        freezer,
        "2026-10-23T20:30:00+00:00",
        "2026-10-23T20:55:00+00:00",
        "2026-10-23T21:40:00+00:00",
        "2026-10-23T21:55:00+00:00",
    )

    # Today has not synced yet, so every poll fetches the day before again.
    garmin_days.days[DAY_BEFORE] = _summary(DAY_BEFORE, 1500, 1400)
    garmin_days.days[date(2026, 10, 24)] = _summary(
        date(2026, 10, 24), None, None, synced=False
    )
    await _poll(hass, freezer, "2026-10-23T22:20:00+00:00")
    await _poll(hass, freezer, "2026-10-23T22:30:00+00:00")
    await hass.config_entries.async_reload(mock_config_entry.entry_id)
    await async_wait_recording_done(hass)
    await _poll(hass, freezer, "2026-10-23T22:40:00+00:00")

    assert garmin_days.requests.count(DAY_BEFORE) >= 4
    assert await _change(hass, STEPS, DAY_BEFORE_START) == 1500


async def test_day_before_is_corrected_when_set_up_after_midnight(
    hass: HomeAssistant,
    garmin_days: FakeGarminDays,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test that a restart after midnight still corrects the day before."""
    garmin_days.days[date(2026, 10, 22)] = _summary(date(2026, 10, 22), None, None)
    garmin_days.days[DAY_BEFORE] = _summary(DAY_BEFORE, 1000, 800)
    freezer.move_to("2026-10-23T20:30:00+00:00")
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    garmin_days.days[DAY_BEFORE] = _summary(DAY_BEFORE, 1200, 1100)
    await _poll(hass, freezer, "2026-10-23T21:40:00+00:00")
    await hass.config_entries.async_unload(mock_config_entry.entry_id)
    await _compile(
        hass,
        freezer,
        "2026-10-23T20:30:00+00:00",
        "2026-10-23T20:55:00+00:00",
        "2026-10-23T21:40:00+00:00",
        "2026-10-23T21:55:00+00:00",
    )

    garmin_days.days[DAY_BEFORE] = _summary(DAY_BEFORE, 1500, 1400)
    garmin_days.days[date(2026, 10, 24)] = _summary(date(2026, 10, 24), 50, 40)
    freezer.move_to("2026-10-23T22:20:00+00:00")
    await hass.config_entries.async_setup(mock_config_entry.entry_id)
    await hass.async_block_till_done()
    await async_wait_recording_done(hass)

    assert await _change(hass, STEPS, DAY_BEFORE_START) == 1500
