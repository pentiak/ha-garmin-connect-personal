"""Constants for the Garmin Connect Personal integration."""

from datetime import timedelta
import logging
from typing import Final

DOMAIN: Final = "garmin_connect_personal"
LOGGER = logging.getLogger(__package__)

UPDATE_INTERVAL: Final = timedelta(minutes=10)

DEFAULT_TITLE: Final = "Garmin Connect"
