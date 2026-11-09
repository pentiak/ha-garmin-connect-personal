"""Import of the daily totals into external long-term statistics (ADR-0029)."""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import TYPE_CHECKING

from aio_garmin_personal import (
    DailyOverview,
    GarminPersonalAuthenticationError,
    GarminPersonalClient,
    GarminPersonalError,
)

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    get_last_statistics,
)
from homeassistant.const import UnitOfEnergy, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util
from homeassistant.util.unit_conversion import DistanceConverter, EnergyConverter

from .const import DOMAIN, HISTORY_CHUNK_DAYS, HISTORY_LOOKBACK, HISTORY_OVERLAP, LOGGER

if TYPE_CHECKING:
    from . import GarminConnectPersonalConfigEntry


@dataclass(frozen=True, kw_only=True)
class HistoryTotal:
    """A daily total imported as an external statistic."""

    key: str
    name: str
    unit: str | None
    unit_class: str | None
    value_fn: Callable[[DailyOverview], float | None]


def _intensity_minutes(day: DailyOverview) -> int | None:
    """Return Garmin's intensity minutes, where vigorous minutes count double."""
    if (
        day.moderate_intensity_minutes is None
        and day.vigorous_intensity_minutes is None
    ):
        return None
    return (day.moderate_intensity_minutes or 0) + 2 * (
        day.vigorous_intensity_minutes or 0
    )


# The sensors with state class `total`, under the same keys and English names.
HISTORY_TOTALS: tuple[HistoryTotal, ...] = (
    HistoryTotal(
        key="total_calories",
        name="Total calories",
        unit=UnitOfEnergy.KILO_CALORIE,
        unit_class=EnergyConverter.UNIT_CLASS,
        value_fn=lambda day: day.total_kilocalories,
    ),
    HistoryTotal(
        key="active_calories",
        name="Active calories",
        unit=UnitOfEnergy.KILO_CALORIE,
        unit_class=EnergyConverter.UNIT_CLASS,
        value_fn=lambda day: day.active_kilocalories,
    ),
    HistoryTotal(
        key="resting_calories",
        name="Resting calories",
        unit=UnitOfEnergy.KILO_CALORIE,
        unit_class=EnergyConverter.UNIT_CLASS,
        value_fn=lambda day: day.resting_kilocalories,
    ),
    HistoryTotal(
        key="steps",
        name="Steps",
        unit=None,
        unit_class=None,
        value_fn=lambda day: day.steps,
    ),
    HistoryTotal(
        key="distance",
        name="Distance",
        unit=UnitOfLength.METERS,
        unit_class=DistanceConverter.UNIT_CLASS,
        value_fn=lambda day: day.total_distance_meters,
    ),
    HistoryTotal(
        key="floors_ascended",
        name="Floors climbed",
        unit=None,
        unit_class=None,
        value_fn=lambda day: day.floors_ascended,
    ),
    HistoryTotal(
        key="intensity_minutes",
        name="Intensity minutes",
        unit=UnitOfTime.MINUTES,
        unit_class=None,
        value_fn=_intensity_minutes,
    ),
    HistoryTotal(
        key="body_battery_charged",
        name="Body Battery charged",
        unit=None,
        unit_class=None,
        value_fn=lambda day: day.body_battery_charged,
    ),
    HistoryTotal(
        key="body_battery_drained",
        name="Body Battery drained",
        unit=None,
        unit_class=None,
        value_fn=lambda day: day.body_battery_drained,
    ),
)


def history_statistic_ids(entry: GarminConnectPersonalConfigEntry) -> list[str]:
    """Return the IDs of the entry's external statistics."""
    return [f"{DOMAIN}:{entry.unique_id}_{total.key}" for total in HISTORY_TOTALS]


def _row_start(day: date, zone: tzinfo) -> datetime:
    """Return the start of the hourly row that holds a day's total.

    Noon keeps the row on the same date in Home Assistant's zone unless the zones are 12
    hours or more apart. Rounding down in UTC keeps it on the hourly grid in zones with a
    half-hour offset.
    """
    noon = dt_util.as_utc(datetime.combine(day, time(12), tzinfo=zone))
    return noon.replace(minute=0, second=0, microsecond=0)


class GarminConnectPersonalHistory:
    """Imports Garmin's daily totals into the entry's external statistics."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GarminConnectPersonalConfigEntry,
        client: GarminPersonalClient,
        time_zone: tzinfo,
    ) -> None:
        """Initialize the importer."""
        self.hass = hass
        self.entry = entry
        self.client = client
        self.time_zone = time_zone
        self._running = False
        self._failing = False

    async def async_import(self) -> None:
        """Import the days that are new or may have changed since the last run.

        A run that is still going, such as the first import of three years, makes the
        next one a no-op. A failure is logged when it starts and when it ends.
        """
        if self._running:
            return
        self._running = True
        try:
            await self._async_import()
        except GarminPersonalAuthenticationError:
            self.entry.async_start_reauth(self.hass)
        except GarminPersonalError as err:
            if not self._failing:
                LOGGER.warning("Could not import the history from Garmin: %s", err)
            self._failing = True
        else:
            if self._failing:
                LOGGER.info("Importing the history from Garmin works again")
            self._failing = False
        finally:
            self._running = False

    async def _async_import(self) -> None:
        """Fetch the days a month at a time, oldest first, and import each month."""
        yesterday = dt_util.now(self.time_zone).date() - timedelta(days=1)
        ids = history_statistic_ids(self.entry)
        recorder = get_instance(self.hass)
        last_rows = await recorder.async_add_executor_job(self._last_rows, ids)
        newest = [
            dt_util.utc_from_timestamp(rows[0]["start"])
            for rows in last_rows.values()
            if rows
        ]
        if any(
            start != _row_start(start.astimezone(self.time_zone).date(), self.time_zone)
            for start in newest
        ):
            # The Garmin zone has changed, so the days imported again would get a second
            # row at another hour. The recorder runs its jobs in order, so the statistics
            # are cleared before this run's rows are added.
            LOGGER.info("The Garmin time zone has changed; importing the history again")
            recorder.async_clear_statistics(ids)
            last_rows = {}
            newest = []
        last_day = max(
            (start.astimezone(self.time_zone).date() for start in newest),
            default=None,
        )
        first = (
            yesterday - HISTORY_LOOKBACK
            if last_day is None
            else last_day - HISTORY_OVERLAP
        )
        start = _row_start(first, self.time_zone)
        sums = {
            statistic_id: next(
                (
                    row["sum"] or 0.0
                    for row in last_rows.get(statistic_id, [])
                    if row["start"] < start.timestamp()
                ),
                0.0,
            )
            for statistic_id in ids
        }
        chunk_start = first
        while chunk_start <= yesterday:
            chunk_end = min(
                chunk_start + timedelta(days=HISTORY_CHUNK_DAYS - 1), yesterday
            )
            days = await self.client.async_get_daily_overviews(chunk_start, chunk_end)
            self._add(days, ids, sums)
            chunk_start = chunk_end + timedelta(days=1)

    def _last_rows(self, ids: list[str]) -> dict[str, list[dict[str, float]]]:
        """Return the most recent rows of each statistic, newest first.

        Enough rows to reach back past the days that the overlap imports again.
        """
        count = HISTORY_OVERLAP.days + 2
        rows: dict[str, list[dict[str, float]]] = {}
        for statistic_id in ids:
            result = get_last_statistics(self.hass, count, statistic_id, False, {"sum"})
            rows[statistic_id] = [
                {"start": row["start"], "sum": row.get("sum") or 0.0}
                for row in result.get(statistic_id, [])
            ]
        return rows

    def _add(
        self,
        days: Iterable[DailyOverview],
        ids: list[str],
        sums: dict[str, float],
    ) -> None:
        """Queue one row per day with wellness data for each total that has a value."""
        wellness_days = sorted(
            (day for day in days if day.includes_wellness_data),
            key=lambda day: day.calendar_date,
        )
        for total, statistic_id in zip(HISTORY_TOTALS, ids, strict=True):
            rows: list[StatisticData] = []
            for day in wellness_days:
                if (value := total.value_fn(day)) is None:
                    continue
                sums[statistic_id] += value
                rows.append(
                    StatisticData(
                        start=_row_start(day.calendar_date, self.time_zone),
                        state=value,
                        sum=sums[statistic_id],
                    )
                )
            if not rows:
                continue
            async_add_external_statistics(
                self.hass,
                StatisticMetaData(
                    mean_type=StatisticMeanType.NONE,
                    has_sum=True,
                    name=f"{self.entry.title} {total.name}",
                    source=DOMAIN,
                    statistic_id=statistic_id,
                    unit_class=total.unit_class,
                    unit_of_measurement=total.unit,
                ),
                rows,
            )
