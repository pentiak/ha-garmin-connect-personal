"""Data update coordinator for Garmin Connect Personal."""

from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import TYPE_CHECKING, Any, override

from aio_garmin_personal import (
    Activity,
    DailySleep,
    DailySummary,
    GarminPersonalAuthenticationError,
    GarminPersonalClient,
    GarminPersonalError,
    GarminPersonalRateLimitError,
    HrvSummary,
    WeightEntry,
)

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    ACTIVITY_UPDATE_INTERVAL,
    DOMAIN,
    LOGGER,
    PREVIOUS_DAY_RECHECK_INTERVAL,
    PREVIOUS_DAY_SETTLE_TIME,
    SLEEP_UPDATE_INTERVAL,
    UPDATE_INTERVAL,
    WEIGHT_LOOKBACK,
    WEIGHT_UPDATE_INTERVAL,
)

if TYPE_CHECKING:
    from . import GarminConnectPersonalConfigEntry


@dataclass(frozen=True, kw_only=True)
class GarminConnectPersonalData:
    """The data of one poll.

    `summary` is `None` when Garmin has nothing for the current day yet. `previous_day`
    is the summary of the day before, fetched again while data synced after midnight can
    still change it, and `None` otherwise.
    """

    summary: DailySummary | None
    previous_day: DailySummary | None = None


@dataclass(frozen=True, kw_only=True)
class GarminConnectPersonalSleepData:
    """The most recent night: the one that ended today, or else the one before.

    Each is `None` when Garmin has neither night.
    """

    sleep: DailySleep | None
    hrv: HrvSummary | None


@dataclass(frozen=True, kw_only=True)
class GarminConnectPersonalWeightData:
    """The latest weight entry of the last year, or `None` without one."""

    latest: WeightEntry | None


@dataclass(frozen=True, kw_only=True)
class GarminConnectPersonalActivityData:
    """The most recently started activity, or `None` if the account has none."""

    latest: Activity | None


@dataclass(frozen=True, kw_only=True)
class GarminConnectPersonalRuntimeData:
    """The coordinators of a config entry."""

    daily: GarminConnectPersonalCoordinator
    sleep: GarminConnectPersonalSleepCoordinator
    weight: GarminConnectPersonalWeightCoordinator
    activity: GarminConnectPersonalActivityCoordinator


async def async_garmin_time_zone(name: str | None) -> tzinfo | None:
    """Return the zone for a Garmin profile `timeZone` value, or `None` if unknown."""
    if not name:
        return None
    return await dt_util.async_get_time_zone("UTC" if name.lower() == "gmt" else name)


class GarminConnectPersonalBaseCoordinator[_DataT](DataUpdateCoordinator[_DataT]):
    """A coordinator that maps the library's errors to Home Assistant's."""

    config_entry: GarminConnectPersonalConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GarminConnectPersonalConfigEntry,
        client: GarminPersonalClient,
        name: str,
        update_interval: timedelta,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=name,
            update_interval=update_interval,
        )
        self.client = client

    async def _async_call[T](self, request: Coroutine[Any, Any, T]) -> T:
        try:
            return await request
        except GarminPersonalAuthenticationError as err:
            raise ConfigEntryAuthFailed(
                translation_domain=DOMAIN, translation_key="invalid_auth"
            ) from err
        except GarminPersonalRateLimitError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="rate_limited",
                retry_after=err.retry_after,
            ) from err
        except GarminPersonalError as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"error": str(err)},
            ) from err


class GarminConnectPersonalCoordinator(
    GarminConnectPersonalBaseCoordinator[GarminConnectPersonalData]
):
    """Poll the daily summary for the current day in the Garmin account's time zone."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GarminConnectPersonalConfigEntry,
        client: GarminPersonalClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, entry, client, DOMAIN, UPDATE_INTERVAL)
        self.time_zone: tzinfo = dt_util.get_default_time_zone()
        self._new_day_synced: date | None = None
        self._previous_day_fetched: datetime | None = None

    @override
    async def _async_setup(self) -> None:
        """Read the account's time zone, which decides where Garmin's day starts."""
        settings = await self._async_call(self.client.async_get_user_settings())
        if (zone := await async_garmin_time_zone(settings.time_zone)) is not None:
            self.time_zone = zone
        elif settings.time_zone:
            LOGGER.warning(
                "Unknown Garmin time zone %s, using the Home Assistant time zone",
                settings.time_zone,
            )

    @override
    async def _async_update_data(self) -> GarminConnectPersonalData:
        """Fetch the summary of the current day, and of the day before until midnight.

        The first sync after midnight uploads what the watch recorded late the day
        before. Today's summary has a last sync time only once that sync has happened, so
        the day before is fetched on every poll until then. Garmin can still add to the
        day before after that, from a later sync, another device or a manual entry, so it
        is fetched hourly for the rest of the day.
        """
        now = dt_util.now(self.time_zone)
        today = now.date()
        summary = await self._async_call(self.client.async_get_daily_summary(today))
        yesterday = today - timedelta(days=1)
        midnight = datetime.combine(today, time.min, tzinfo=self.time_zone)
        if now - midnight < PREVIOUS_DAY_SETTLE_TIME or (
            self._new_day_synced == yesterday
            and self._previous_day_fetched is not None
            and now - self._previous_day_fetched < PREVIOUS_DAY_RECHECK_INTERVAL
        ):
            return GarminConnectPersonalData(summary=summary)
        previous_day = await self._async_call(
            self.client.async_get_daily_summary(yesterday)
        )
        self._previous_day_fetched = now
        if summary is not None and summary.last_sync is not None:
            self._new_day_synced = yesterday
        return GarminConnectPersonalData(summary=summary, previous_day=previous_day)


class GarminConnectPersonalSleepCoordinator(
    GarminConnectPersonalBaseCoordinator[GarminConnectPersonalSleepData]
):
    """Poll the most recent night's sleep and HRV.

    They change only when the watch syncs, so the entry also requests a refresh whenever
    the daily summary shows a new sync. The interval is a fallback for syncs that the
    daily coordinator misses, for example while it is failing.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GarminConnectPersonalConfigEntry,
        client: GarminPersonalClient,
        time_zone: tzinfo,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(hass, entry, client, f"{DOMAIN} sleep", SLEEP_UPDATE_INTERVAL)
        self.time_zone = time_zone

    @override
    async def _async_update_data(self) -> GarminConnectPersonalSleepData:
        """Fetch the night that ended today, or the night before until today's is there."""
        today = dt_util.now(self.time_zone).date()
        yesterday = today - timedelta(days=1)
        sleep = await self._async_call(self.client.async_get_sleep(today))
        if sleep is None:
            sleep = await self._async_call(self.client.async_get_sleep(yesterday))
        hrv = await self._async_call(self.client.async_get_hrv(today))
        if hrv is None or hrv.summary is None:
            hrv = await self._async_call(self.client.async_get_hrv(yesterday))
        return GarminConnectPersonalSleepData(
            sleep=sleep, hrv=hrv.summary if hrv is not None else None
        )


class GarminConnectPersonalWeightCoordinator(
    GarminConnectPersonalBaseCoordinator[GarminConnectPersonalWeightData]
):
    """Poll the latest weight entry, entered by hand or by a scale.

    Unlike the other coordinators, its first refresh may fail without failing setup: the
    weight sensors are then unavailable until a later poll succeeds.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GarminConnectPersonalConfigEntry,
        client: GarminPersonalClient,
        time_zone: tzinfo,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass, entry, client, f"{DOMAIN} weight", WEIGHT_UPDATE_INTERVAL
        )
        self.time_zone = time_zone
        # Setup goes on when the first weight request fails, so the data must exist
        # before any request has succeeded.
        self.data = GarminConnectPersonalWeightData(latest=None)

    @override
    async def _async_update_data(self) -> GarminConnectPersonalWeightData:
        """Fetch the last year's weight and keep the most recent entry."""
        today = dt_util.now(self.time_zone).date()
        weight = await self._async_call(
            self.client.async_get_weight(today - WEIGHT_LOOKBACK, today)
        )
        days = [day for day in weight.days if day.latest is not None]
        latest_day = max(days, key=lambda day: day.calendar_date, default=None)
        return GarminConnectPersonalWeightData(
            latest=latest_day.latest if latest_day else None
        )


class GarminConnectPersonalActivityCoordinator(
    GarminConnectPersonalBaseCoordinator[GarminConnectPersonalActivityData]
):
    """Poll the most recently started activity.

    Activities usually reach Garmin when the watch syncs, so the entry also requests a
    refresh whenever the daily summary shows a new sync. Like the weight coordinator, its
    first refresh may fail without failing setup.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GarminConnectPersonalConfigEntry,
        client: GarminPersonalClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass, entry, client, f"{DOMAIN} activity", ACTIVITY_UPDATE_INTERVAL
        )
        # Setup goes on when the first activity request fails, so the data must exist
        # before any request has succeeded.
        self.data = GarminConnectPersonalActivityData(latest=None)

    @override
    async def _async_update_data(self) -> GarminConnectPersonalActivityData:
        """Fetch the first activity of Garmin's list, which is sorted newest first."""
        activities = await self._async_call(self.client.async_get_activities(limit=1))
        return GarminConnectPersonalActivityData(
            latest=activities[0] if activities else None
        )
