"""Sensors for Garmin Connect Personal."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import math
from typing import override

from aio_garmin_personal import DailySummary, HrvSummary, WeightEntry

from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.sensor.const import UNIT_CONVERTERS
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfEnergy,
    UnitOfLength,
    UnitOfMass,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from . import GarminConnectPersonalConfigEntry
from .const import LOGGER
from .coordinator import (
    GarminConnectPersonalCoordinator,
    GarminConnectPersonalSleepCoordinator,
    GarminConnectPersonalSleepData,
    GarminConnectPersonalWeightCoordinator,
)
from .entity import GarminConnectPersonalEntity

# The coordinator does all I/O.
PARALLEL_UPDATES = 0

# Home Assistant has no unit constant for it; Withings in core uses the same string.
BREATHS_PER_MINUTE = "br/min"


@dataclass(frozen=True, kw_only=True)
class GarminConnectPersonalSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor read from the daily summary."""

    value_fn: Callable[[DailySummary], float | int | datetime | None]


def _intensity_minutes(summary: DailySummary) -> int | None:
    """Return Garmin's intensity minutes, where vigorous minutes count double."""
    if (
        summary.moderate_intensity_minutes is None
        and summary.vigorous_intensity_minutes is None
    ):
        return None
    return (summary.moderate_intensity_minutes or 0) + 2 * (
        summary.vigorous_intensity_minutes or 0
    )


SENSORS: tuple[GarminConnectPersonalSensorEntityDescription, ...] = (
    GarminConnectPersonalSensorEntityDescription(
        key="total_calories",
        translation_key="total_calories",
        native_unit_of_measurement=UnitOfEnergy.KILO_CALORIE,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda summary: summary.total_kilocalories,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="active_calories",
        translation_key="active_calories",
        native_unit_of_measurement=UnitOfEnergy.KILO_CALORIE,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda summary: summary.active_kilocalories,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="resting_calories",
        translation_key="resting_calories",
        native_unit_of_measurement=UnitOfEnergy.KILO_CALORIE,
        device_class=SensorDeviceClass.ENERGY,
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.bmr_kilocalories,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="steps",
        translation_key="steps",
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda summary: summary.total_steps,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="distance",
        native_unit_of_measurement=UnitOfLength.METERS,
        suggested_unit_of_measurement=UnitOfLength.KILOMETERS,
        suggested_display_precision=2,
        device_class=SensorDeviceClass.DISTANCE,
        state_class=SensorStateClass.TOTAL,
        value_fn=lambda summary: summary.total_distance_meters,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="floors_ascended",
        translation_key="floors_ascended",
        state_class=SensorStateClass.TOTAL,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.floors_ascended,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="intensity_minutes",
        translation_key="intensity_minutes",
        native_unit_of_measurement=UnitOfTime.MINUTES,
        state_class=SensorStateClass.TOTAL,
        value_fn=_intensity_minutes,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="resting_heart_rate",
        translation_key="resting_heart_rate",
        native_unit_of_measurement="bpm",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.resting_heart_rate,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="average_stress",
        translation_key="average_stress",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.average_stress_level,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="body_battery",
        translation_key="body_battery",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.body_battery_most_recent_value,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="body_battery_highest",
        translation_key="body_battery_highest",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.body_battery_highest_value,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="body_battery_lowest",
        translation_key="body_battery_lowest",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.body_battery_lowest_value,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="body_battery_charged",
        translation_key="body_battery_charged",
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.body_battery_charged_value,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="body_battery_drained",
        translation_key="body_battery_drained",
        state_class=SensorStateClass.TOTAL,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.body_battery_drained_value,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="min_heart_rate",
        translation_key="min_heart_rate",
        native_unit_of_measurement="bpm",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.min_heart_rate,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="max_heart_rate",
        translation_key="max_heart_rate",
        native_unit_of_measurement="bpm",
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.max_heart_rate,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="average_spo2",
        translation_key="average_spo2",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.average_spo2,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="lowest_spo2",
        translation_key="lowest_spo2",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.lowest_spo2,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="latest_spo2",
        translation_key="latest_spo2",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.latest_spo2,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="average_respiration",
        translation_key="average_respiration",
        native_unit_of_measurement=BREATHS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda summary: summary.average_waking_respiration,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="lowest_respiration",
        translation_key="lowest_respiration",
        native_unit_of_measurement=BREATHS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.lowest_respiration,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="highest_respiration",
        translation_key="highest_respiration",
        native_unit_of_measurement=BREATHS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.highest_respiration,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="latest_respiration",
        translation_key="latest_respiration",
        native_unit_of_measurement=BREATHS_PER_MINUTE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda summary: summary.latest_respiration,
    ),
    GarminConnectPersonalSensorEntityDescription(
        key="last_sync",
        translation_key="last_sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda summary: summary.last_sync,
    ),
)


@dataclass(frozen=True, kw_only=True)
class GarminConnectPersonalSleepSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor read from the most recent night."""

    value_fn: Callable[[GarminConnectPersonalSleepData], float | int | str | None]


HRV_STATUSES = ["none", "poor", "low", "unbalanced", "balanced", "invalid"]


def _hrv_status(hrv: HrvSummary | None) -> str | None:
    """Return the HRV status as an option of the enum sensor, or `None` if unknown."""
    if hrv is None or hrv.status is None:
        return None
    if (status := hrv.status.lower()) not in HRV_STATUSES:
        LOGGER.debug("Unknown HRV status %s", hrv.status)
        return None
    return status


def _sleep_duration(
    key: str,
    value_fn: Callable[[GarminConnectPersonalSleepData], int | None],
    *,
    enabled: bool = False,
) -> GarminConnectPersonalSleepSensorEntityDescription:
    """Describe a sleep duration, recorded in seconds and shown in hours."""
    return GarminConnectPersonalSleepSensorEntityDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_unit_of_measurement=UnitOfTime.HOURS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.DURATION,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=enabled,
        value_fn=value_fn,
    )


SLEEP_SENSORS: tuple[GarminConnectPersonalSleepSensorEntityDescription, ...] = (
    GarminConnectPersonalSleepSensorEntityDescription(
        key="sleep_score",
        translation_key="sleep_score",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.sleep.score if data.sleep else None,
    ),
    _sleep_duration(
        "sleep_duration",
        lambda data: data.sleep.sleep_seconds if data.sleep else None,
        enabled=True,
    ),
    _sleep_duration(
        "deep_sleep",
        lambda data: data.sleep.deep_sleep_seconds if data.sleep else None,
    ),
    _sleep_duration(
        "light_sleep",
        lambda data: data.sleep.light_sleep_seconds if data.sleep else None,
    ),
    _sleep_duration(
        "rem_sleep",
        lambda data: data.sleep.rem_sleep_seconds if data.sleep else None,
    ),
    _sleep_duration(
        "awake_time",
        lambda data: data.sleep.awake_sleep_seconds if data.sleep else None,
    ),
    GarminConnectPersonalSleepSensorEntityDescription(
        key="hrv_last_night",
        translation_key="hrv_last_night",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.hrv.last_night_average if data.hrv else None,
    ),
    GarminConnectPersonalSleepSensorEntityDescription(
        key="hrv_weekly_average",
        translation_key="hrv_weekly_average",
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_registry_enabled_default=False,
        value_fn=lambda data: data.hrv.weekly_average if data.hrv else None,
    ),
    GarminConnectPersonalSleepSensorEntityDescription(
        key="hrv_status",
        translation_key="hrv_status",
        device_class=SensorDeviceClass.ENUM,
        options=HRV_STATUSES,
        value_fn=lambda data: _hrv_status(data.hrv),
    ),
)


@dataclass(frozen=True, kw_only=True)
class GarminConnectPersonalWeightSensorEntityDescription(SensorEntityDescription):
    """Describes a sensor read from the latest weight entry."""

    value_fn: Callable[[WeightEntry], float | datetime | None]


WEIGHT_SENSORS: tuple[GarminConnectPersonalWeightSensorEntityDescription, ...] = (
    GarminConnectPersonalWeightSensorEntityDescription(
        key="weight",
        native_unit_of_measurement=UnitOfMass.GRAMS,
        suggested_unit_of_measurement=UnitOfMass.KILOGRAMS,
        suggested_display_precision=1,
        device_class=SensorDeviceClass.WEIGHT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda entry: entry.weight_grams,
    ),
    GarminConnectPersonalWeightSensorEntityDescription(
        key="bmi",
        translation_key="bmi",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda entry: entry.bmi,
    ),
    GarminConnectPersonalWeightSensorEntityDescription(
        key="body_fat",
        translation_key="body_fat",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        entity_registry_enabled_default=False,
        value_fn=lambda entry: entry.body_fat_percent,
    ),
    GarminConnectPersonalWeightSensorEntityDescription(
        key="last_weigh_in",
        translation_key="last_weigh_in",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_registry_enabled_default=False,
        value_fn=lambda entry: entry.time_gmt,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GarminConnectPersonalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors of a config entry."""
    daily = entry.runtime_data.daily
    sleep = entry.runtime_data.sleep
    weight = entry.runtime_data.weight
    async_add_entities(
        [
            *(
                GarminConnectPersonalSensor(daily, description)
                for description in SENSORS
            ),
            *(
                GarminConnectPersonalSleepSensor(sleep, description)
                for description in SLEEP_SENSORS
            ),
            *(
                GarminConnectPersonalWeightSensor(weight, description)
                for description in WEIGHT_SENSORS
            ),
        ]
    )


class GarminConnectPersonalSensor(
    GarminConnectPersonalEntity[GarminConnectPersonalCoordinator], SensorEntity
):
    """A value from the current day's summary."""

    entity_description: GarminConnectPersonalSensorEntityDescription

    def __init__(
        self,
        coordinator: GarminConnectPersonalCoordinator,
        description: GarminConnectPersonalSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description
        self._corrected_day: tuple[date, float] | None = None

    @property
    def native_value(self) -> float | int | datetime | None:
        """Return the value for the current day, or `None` before Garmin has any."""
        if (summary := self.coordinator.data.summary) is None:
            return None
        return self.entity_description.value_fn(summary)

    @property
    def last_reset(self) -> datetime | None:
        """Return midnight of the summary's day in the Garmin time zone, for daily totals."""
        # An explicit reset time, because the recorder only infers one for total_increasing
        # from a drop below 90% of the previous value, and calorie totals need not drop that
        # far at midnight.
        if self.state_class is not SensorStateClass.TOTAL:
            return None
        if (summary := self.coordinator.data.summary) is None:
            return None
        return datetime.combine(
            summary.calendar_date, time.min, tzinfo=self.coordinator.time_zone
        )

    @override
    async def async_added_to_hass(self) -> None:
        """Correct the day before if the first refresh fetched it."""
        await super().async_added_to_hass()
        self._async_schedule_correction()

    @callback
    @override
    def _handle_coordinator_update(self) -> None:
        """Write the new state, and correct the day before when Garmin has more for it."""
        self._async_schedule_correction()
        super()._handle_coordinator_update()

    @callback
    def _async_schedule_correction(self) -> None:
        """Start correcting the day before, for a daily total, if the poll fetched it."""
        if (
            self.state_class is SensorStateClass.TOTAL
            and (previous_day := self.coordinator.data.previous_day) is not None
            and "recorder" in self.hass.config.components
        ):
            self.coordinator.config_entry.async_create_background_task(
                self.hass,
                self._async_correct_day(previous_day),
                f"{self.entity_id} correct {previous_day.calendar_date}",
            )

    async def _async_correct_day(self, summary: DailySummary) -> None:
        """Make the long-term statistics of a past day match Garmin's final total.

        Data synced after midnight never reaches the state, so the day's change in the
        statistics stops at the last value before midnight. The difference is added to
        the statistics from the day's last recorded hour on, which raises that day's total
        and leaves the totals of later days as they were.
        """
        value = self.entity_description.value_fn(summary)
        if not isinstance(value, int | float):
            return
        if self._corrected_day == (summary.calendar_date, value):
            return
        # Set before reading, so that a second poll cannot apply the same difference.
        self._corrected_day = (summary.calendar_date, value)
        zone = self.coordinator.time_zone
        start = datetime.combine(summary.calendar_date, time.min, tzinfo=zone)
        end = datetime.combine(
            summary.calendar_date + timedelta(days=1), time.min, tzinfo=zone
        )
        unit = self.native_unit_of_measurement
        units = None
        if unit and (converter := UNIT_CONVERTERS.get(self.device_class)):
            units = {converter.UNIT_CLASS: unit}
        recorder = get_instance(self.hass)
        recorded, last_hour = await recorder.async_add_executor_job(
            _recorded_day, self.hass, self.entity_id, start, end, units
        )
        # No statistics for that day: the sensor did not exist, was disabled or had no
        # value all day.
        if recorded is None or last_hour is None:
            self._corrected_day = None
            return
        if math.isclose(value, recorded, abs_tol=1e-6):
            return
        LOGGER.debug(
            "Adding %s to the statistics of %s for %s",
            value - recorded,
            self.entity_id,
            summary.calendar_date,
        )
        recorder.async_adjust_statistics(
            self.entity_id, last_hour, value - recorded, unit or ""
        )


def _recorded_day(
    hass: HomeAssistant,
    statistic_id: str,
    start: datetime,
    end: datetime,
    units: dict[str, str] | None,
) -> tuple[float | None, datetime | None]:
    """Return a day's change in the statistics, and the start of its last recorded hour.

    The recorder writes no hourly row while the sensor has no value, for example while a
    watch does not reach its phone. An adjustment applies only to rows that exist, so it
    has to start at a row of that day rather than at the day's last hour. Each row's
    change is taken against the last row before it, however long ago that was.
    """
    rows = statistics_during_period(
        hass, start, end, {statistic_id}, "hour", units, {"change"}
    ).get(statistic_id)
    if not rows:
        return None, None
    change = sum(row.get("change") or 0 for row in rows)
    return change, dt_util.utc_from_timestamp(rows[-1]["start"])


class GarminConnectPersonalSleepSensor(
    GarminConnectPersonalEntity[GarminConnectPersonalSleepCoordinator], SensorEntity
):
    """A value from the most recent night's sleep or HRV."""

    entity_description: GarminConnectPersonalSleepSensorEntityDescription

    def __init__(
        self,
        coordinator: GarminConnectPersonalSleepCoordinator,
        description: GarminConnectPersonalSleepSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | int | str | None:
        """Return the value for the most recent night, or `None` without one."""
        return self.entity_description.value_fn(self.coordinator.data)


class GarminConnectPersonalWeightSensor(
    GarminConnectPersonalEntity[GarminConnectPersonalWeightCoordinator], SensorEntity
):
    """A value from the latest weight entry."""

    entity_description: GarminConnectPersonalWeightSensorEntityDescription

    def __init__(
        self,
        coordinator: GarminConnectPersonalWeightCoordinator,
        description: GarminConnectPersonalWeightSensorEntityDescription,
    ) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | datetime | None:
        """Return the value of the latest entry, or `None` without one."""
        if (latest := self.coordinator.data.latest) is None:
            return None
        return self.entity_description.value_fn(latest)
