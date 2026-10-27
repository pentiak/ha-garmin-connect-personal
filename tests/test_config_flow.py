"""Tests for the Garmin Connect Personal config flow."""

from collections.abc import Generator
from datetime import date
from unittest.mock import AsyncMock, patch

from aio_garmin_personal import (
    Activity,
    DailySummary,
    GarminPersonalAuthenticationError,
    GarminPersonalConnectionError,
    GarminPersonalResponseError,
    UserSettings,
)
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.garmin_connect_personal.const import DOMAIN
from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_API_KEY
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import ACCOUNT_ID, load_json

pytestmark = pytest.mark.usefixtures("mock_setup_entry")


@pytest.fixture
def mock_setup_entry() -> Generator[AsyncMock]:
    """Prevent the config flow tests from setting up the entry."""
    with patch(
        "custom_components.garmin_connect_personal.async_setup_entry", return_value=True
    ) as setup:
        yield setup


async def test_user_flow_creates_entry(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """Test that a valid key creates an entry for the account."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "  new-key \n"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Alex Example"
    assert result["data"] == {CONF_API_KEY: "new-key"}
    assert result["result"].unique_id == ACCOUNT_ID


async def test_user_flow_asks_for_garmin_today(
    hass: HomeAssistant, mock_client: AsyncMock, freezer: FrozenDateTimeFactory
) -> None:
    """Test that the flow requests today's summary in the Garmin time zone."""
    freezer.move_to("2026-10-22T23:30:00+00:00")

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "key"}
    )

    mock_client.async_get_daily_summary.assert_awaited_once_with(date(2026, 10, 23))


@pytest.mark.parametrize(
    ("side_effect", "error"),
    [
        (GarminPersonalAuthenticationError("rejected"), "invalid_auth"),
        (GarminPersonalConnectionError("down"), "cannot_connect"),
        (GarminPersonalResponseError("bad", 500), "unknown"),
    ],
)
async def test_user_flow_errors_recover(
    hass: HomeAssistant, mock_client: AsyncMock, side_effect: Exception, error: str
) -> None:
    """Test each error shown in the form, and that a retry succeeds."""
    mock_client.async_get_user_settings.side_effect = side_effect

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "key"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    mock_client.async_get_user_settings.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "key"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_user_flow_empty_summary_is_unknown_error(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """Test that an empty summary response shows the unknown error."""
    mock_client.async_get_daily_summary.return_value = None

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "key"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "unknown"}


@pytest.mark.parametrize(
    ("display_name", "title"),
    [
        ("Trail Runner", "Trail Runner"),
        ("00000000-0000-4000-8000-000000000000", "Alex Example"),
        (None, "Alex Example"),
    ],
)
async def test_user_flow_title_from_display_name_or_full_name(
    hass: HomeAssistant, mock_client: AsyncMock, display_name: str | None, title: str
) -> None:
    """Test that a set display name wins over the full name from the activities."""
    settings = load_json("user_settings.json") | {"displayName": display_name}
    mock_client.async_get_user_settings.return_value = UserSettings.from_dict(settings)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "key"}
    )

    assert result["title"] == title


@pytest.mark.parametrize(
    "activities",
    [
        [],
        [Activity.from_dict({"activityId": 1})],
        [Activity.from_dict({"activityId": 1, "ownerFullName": "  "})],
    ],
    ids=["no-activities", "no-full-name", "blank-full-name"],
)
async def test_user_flow_title_without_full_name(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """Test the default title for an account whose activities give no name."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "key"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Garmin Connect"


async def test_user_flow_title_when_activities_fail(
    hass: HomeAssistant, mock_client: AsyncMock
) -> None:
    """Test that an unreadable activity list still creates the entry."""
    mock_client.async_get_activities.side_effect = GarminPersonalResponseError(
        "GET returned HTTP 403", 403
    )

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "key"}
    )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Garmin Connect"


async def test_user_flow_aborts_for_configured_account(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that an account already configured aborts the flow."""
    mock_config_entry.add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_replaces_key(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that reauthentication stores the new key."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "renewed-key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert mock_config_entry.data == {CONF_API_KEY: "renewed-key"}


async def test_reauth_error_recovers(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that reauthentication shows an error and accepts a retry."""
    mock_config_entry.add_to_hass(hass)
    mock_client.async_get_user_settings.side_effect = GarminPersonalAuthenticationError(
        "no"
    )

    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "still-wrong"}
    )

    assert result["errors"] == {"base": "invalid_auth"}

    mock_client.async_get_user_settings.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "renewed-key"}
    )

    assert result["reason"] == "reauth_successful"


async def test_reauth_rejects_other_account(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that reauthentication with another account keeps the old key."""
    mock_config_entry.add_to_hass(hass)
    other = load_json("daily_summary.json") | {"userProfileId": 987654321}
    mock_client.async_get_daily_summary.return_value = DailySummary.from_dict(other)

    result = await mock_config_entry.start_reauth_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "other-key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_account"
    assert mock_config_entry.data == {CONF_API_KEY: "test-api-key"}


async def test_reconfigure_replaces_key(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that reconfiguration stores the new key."""
    mock_config_entry.add_to_hass(hass)

    result = await mock_config_entry.start_reconfigure_flow(hass)
    assert result["step_id"] == "reconfigure"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_API_KEY: "next-key"}
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert mock_config_entry.data == {CONF_API_KEY: "next-key"}
