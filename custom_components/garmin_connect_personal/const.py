"""Constants for the Garmin Connect Personal integration."""

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "garmin_connect_personal"
LOGGER = logging.getLogger(__package__)

UPDATE_INTERVAL: Final = timedelta(minutes=10)
SLEEP_UPDATE_INTERVAL: Final = timedelta(hours=1)

# Wait after midnight before reading the recorder's total for the day before, so that it
# has compiled the day's last hour.
PREVIOUS_DAY_SETTLE_TIME: Final = timedelta(minutes=15)

DEFAULT_TITLE: Final = "Garmin Connect"
