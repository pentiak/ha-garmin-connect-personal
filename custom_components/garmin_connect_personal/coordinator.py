"""Data update coordinator for Garmin Connect Personal."""

from collections.abc import Coroutine
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, tzinfo
from typing import TYPE_CHECKING, Any, override

from aio_garmin_personal import (
    DailySummary,
    GarminPersonalAuthenticationError,
    GarminPersonalClient,
    GarminPersonalError,
    GarminPersonalRateLimitError,
)

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import DOMAIN, LOGGER, PREVIOUS_DAY_SETTLE_TIME, UPDATE_INTERVAL

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


async def async_garmin_time_zone(name: str | None) -> tzinfo | None:
    """Return the zone for a Garmin profile `timeZone` value, or `None` if unknown."""
    if not name:
        return None
    return await dt_util.async_get_time_zone("UTC" if name.lower() == "gmt" else name)


class GarminConnectPersonalCoordinator(
    DataUpdateCoordinator[GarminConnectPersonalData]
):
    """Poll the daily summary for the current day in the Garmin account's time zone."""

    config_entry: GarminConnectPersonalConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: GarminConnectPersonalConfigEntry,
        client: GarminPersonalClient,
    ) -> None:
        """Initialize the coordinator."""
        super().__init__(
            hass,
            LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=UPDATE_INTERVAL,
        )
        self.client = client
        self.time_zone: tzinfo = dt_util.get_default_time_zone()
        self._final_day: date | None = None

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
        """Fetch the summary of the current day, and of the day before until it is final.

        The first sync after midnight uploads what the watch recorded late the day
        before. Today's summary has a last sync time only once that sync has happened, so
        the day before is fetched on every poll until then, and once more after it.
        """
        now = dt_util.now(self.time_zone)
        today = now.date()
        summary = await self._async_call(self.client.async_get_daily_summary(today))
        yesterday = today - timedelta(days=1)
        midnight = datetime.combine(today, time.min, tzinfo=self.time_zone)
        if self._final_day == yesterday or now - midnight < PREVIOUS_DAY_SETTLE_TIME:
            return GarminConnectPersonalData(summary=summary)
        previous_day = await self._async_call(
            self.client.async_get_daily_summary(yesterday)
        )
        if summary is not None and summary.last_sync is not None:
            self._final_day = yesterday
        return GarminConnectPersonalData(summary=summary, previous_day=previous_day)

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
