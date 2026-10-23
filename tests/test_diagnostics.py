"""Tests for Garmin Connect Personal diagnostics."""

from unittest.mock import AsyncMock

from pytest_homeassistant_custom_component.common import MockConfigEntry
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.core import HomeAssistant


async def test_diagnostics_redact_key_and_identity(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that diagnostics redact the key and account identifiers."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )

    assert diagnostics["entry"] == {"api_key": "**REDACTED**"}
    assert diagnostics["time_zone"] == "Europe/Berlin"
    assert diagnostics["summary"]["userProfileId"] == "**REDACTED**"
    assert diagnostics["summary"]["userDailySummaryId"] == "**REDACTED**"
    assert diagnostics["summary"]["uuid"] == "**REDACTED**"
    assert diagnostics["summary"]["totalKilocalories"] == 655.0
