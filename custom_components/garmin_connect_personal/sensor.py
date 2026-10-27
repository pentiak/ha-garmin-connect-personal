"""Sensors for Garmin Connect Personal."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
import math
from typing import override

from aio_garmin_personal import DailySummary

from homeassistant.components.recorder.statistics import statistic_during_period
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.components.sensor.const import UNIT_CONVERTERS
from homeassistant.const import EntityCategory, UnitOfEnergy, UnitOfLength, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from . import GarminConnectPersonalConfigEntry
from .const import LOGGER
from .coordinator import GarminConnectPersonalCoordinator
from .entity import GarminConnectPersonalEntity

# The coordinator does all I/O.
PARALLEL_UPDATES = 0


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
        key="last_sync",
        translation_key="last_sync",
        device_class=SensorDeviceClass.TIMESTAMP,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda summary: summary.last_sync,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GarminConnectPersonalConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors of a config entry."""
    coordinator = entry.runtime_data
    async_add_entities(
        GarminConnectPersonalSensor(coordinator, description) for description in SENSORS
    )


class GarminConnectPersonalSensor(GarminConnectPersonalEntity, SensorEntity):
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
        the statistics from the day's last hour on, which raises that day's total and
        leaves the totals of later days as they were.
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
        recorded = (
            await recorder.async_add_executor_job(
                statistic_during_period,
                self.hass,
                start,
                end,
                self.entity_id,
                {"change"},
                units,
            )
        ).get("change")
        # No statistics for that day: the sensor did not exist or was disabled.
        if recorded is None:
            self._corrected_day = None
            return
        if math.isclose(value, recorded, abs_tol=1e-6):
            return
        last_hour = dt_util.as_utc(end - timedelta(minutes=1)).replace(
            minute=0, second=0, microsecond=0
        )
        LOGGER.debug(
            "Adding %s to the statistics of %s for %s",
            value - recorded,
            self.entity_id,
            summary.calendar_date,
        )
        recorder.async_adjust_statistics(
            self.entity_id, last_hour, value - recorded, unit or ""
        )
