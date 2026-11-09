"""Constants for the Garmin Connect Personal integration."""

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "garmin_connect_personal"
LOGGER = logging.getLogger(__package__)

UPDATE_INTERVAL: Final = timedelta(minutes=10)
SLEEP_UPDATE_INTERVAL: Final = timedelta(hours=1)
WEIGHT_UPDATE_INTERVAL: Final = timedelta(hours=1)
ACTIVITY_UPDATE_INTERVAL: Final = timedelta(hours=1)
HISTORY_UPDATE_INTERVAL: Final = timedelta(hours=1)

# The first import of the daily totals covers three years, a month per request: Garmin
# rejects ranges of over about a year and has failed on ranges of several months. Later
# imports start a week before the last imported day, to pick up late changes (ADR-0029).
HISTORY_LOOKBACK: Final = timedelta(days=3 * 365)
HISTORY_CHUNK_DAYS: Final = 31
HISTORY_OVERLAP: Final = timedelta(days=7)

# How far back to look for the latest weight entry. Garmin accepts ranges of three years.
WEIGHT_LOOKBACK: Final = timedelta(days=365)

# Wait after midnight before reading the recorder's total for the day before, so that it
# has compiled the day's last hour.
PREVIOUS_DAY_SETTLE_TIME: Final = timedelta(minutes=15)
PREVIOUS_DAY_RECHECK_INTERVAL: Final = timedelta(hours=1)

DEFAULT_TITLE: Final = "Garmin Connect"
