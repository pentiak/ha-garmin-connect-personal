"""Fixtures for Garmin Connect Personal tests."""

from collections.abc import Generator
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from aio_garmin_personal import (
    Activity,
    DailyHrv,
    DailySleep,
    DailySummary,
    UserSettings,
)
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.garmin_connect_personal.const import DOMAIN
from homeassistant.const import CONF_API_KEY

FIXTURES = Path(__file__).parent / "fixtures"
ACCOUNT_ID = "123456789"
API_KEY = "test-api-key"


def load_json(name: str) -> dict[str, Any]:
    """Return a fixture file as decoded JSON."""
    data: dict[str, Any] = json.loads((FIXTURES / name).read_text(encoding="utf-8"))
    return data


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load integrations from custom_components in every test."""


@pytest.fixture
def daily_summary() -> DailySummary:
    """Return the fixture's daily summary."""
    return DailySummary.from_dict(load_json("daily_summary.json"))


@pytest.fixture
def sleep() -> DailySleep:
    """Return the fixture's night of sleep."""
    return DailySleep.from_dict(load_json("sleep.json"))


@pytest.fixture
def hrv() -> DailyHrv:
    """Return the fixture's night of HRV."""
    return DailyHrv.from_dict(load_json("hrv.json"))


@pytest.fixture
def user_settings() -> UserSettings:
    """Return the fixture's profile settings."""
    return UserSettings.from_dict(load_json("user_settings.json"))


@pytest.fixture
def activities() -> list[Activity]:
    """Return the fixture's activities, most recent first."""
    data: list[dict[str, Any]] = json.loads(
        (FIXTURES / "activities.json").read_text(encoding="utf-8")
    )
    return [Activity.from_dict(item) for item in data]


@pytest.fixture
def mock_client(
    daily_summary: DailySummary,
    user_settings: UserSettings,
    activities: list[Activity],
    sleep: DailySleep,
    hrv: DailyHrv,
) -> Generator[AsyncMock]:
    """Replace the library client in both the integration and the config flow."""
    with (
        patch(
            "custom_components.garmin_connect_personal.GarminPersonalClient",
            autospec=True,
        ) as client_class,
        patch(
            "custom_components.garmin_connect_personal.config_flow.GarminPersonalClient",
            new=client_class,
        ),
    ):
        client = client_class.return_value
        client.async_get_user_settings.return_value = user_settings
        client.async_get_daily_summary.return_value = daily_summary
        client.async_get_activities.return_value = activities
        client.async_get_sleep.return_value = sleep
        client.async_get_hrv.return_value = hrv
        yield client


@pytest.fixture
def mock_config_entry() -> MockConfigEntry:
    """Return a config entry for the fixture account."""
    return MockConfigEntry(
        domain=DOMAIN,
        title="Garmin Connect",
        unique_id=ACCOUNT_ID,
        data={CONF_API_KEY: API_KEY},
    )
