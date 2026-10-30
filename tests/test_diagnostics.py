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
    """Test that diagnostics redact the key, account identifiers and activities."""
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
    assert diagnostics["summary"]["bodyBatteryActivityEventList"] == "**REDACTED**"
    assert diagnostics["summary"]["totalKilocalories"] == 655.0


async def test_diagnostics_redact_sleep_times(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test that diagnostics redact when the night started and ended."""
    mock_config_entry.add_to_hass(hass)
    await hass.config_entries.async_setup(mock_config_entry.entry_id)

    diagnostics = await get_diagnostics_for_config_entry(
        hass, hass_client, mock_config_entry
    )

    sleep = diagnostics["sleep"]
    for key in (
        "id",
        "userProfilePK",
        "sleepStartTimestampGMT",
        "sleepEndTimestampGMT",
        "sleepStartTimestampLocal",
        "sleepEndTimestampLocal",
    ):
        assert sleep[key] == "**REDACTED**"
    assert sleep["sleepNeed"]["userProfilePk"] == "**REDACTED**"
    assert sleep["sleepNeed"]["deviceId"] == "**REDACTED**"
    assert sleep["sleepNeed"]["timestampGmt"] == "**REDACTED**"
    assert sleep["sleepTimeSeconds"] == 27000
    assert diagnostics["hrv"]["createTimeStamp"] == "**REDACTED**"
    assert diagnostics["hrv"]["lastNightAvg"] == 52
    assert diagnostics["sleep_last_update_success"] is True
