"""Tests for the Garmin Connect Personal sensors."""

from unittest.mock import AsyncMock

from aio_garmin_personal import DailySummary
from freezegun.api import FrozenDateTimeFactory
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    snapshot_platform,
)
from syrupy.assertion import SnapshotAssertion

from homeassistant.const import STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .conftest import ACCOUNT_ID, load_json


async def _setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "mock_client")
async def test_all_entities(
    hass: HomeAssistant,
    snapshot: SnapshotAssertion,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
    freezer: FrozenDateTimeFactory,
) -> None:
    """Test the registry entry and state of every sensor, all of them enabled."""
    freezer.move_to("2026-10-23T08:00:00+00:00")
    await _setup(hass, mock_config_entry)

    await snapshot_platform(hass, entity_registry, snapshot, mock_config_entry.entry_id)


@pytest.mark.usefixtures("mock_client")
async def test_disabled_by_default(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    mock_config_entry: MockConfigEntry,
) -> None:
    """Test which sensors are disabled until the user enables them."""
    await _setup(hass, mock_config_entry)

    disabled = {
        entry.entity_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, mock_config_entry.entry_id
        )
        if entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION
    }

    assert disabled == {
        "sensor.garmin_connect_resting_calories",
        "sensor.garmin_connect_floors_climbed",
        "sensor.garmin_connect_average_stress",
        "sensor.garmin_connect_body_battery_highest",
        "sensor.garmin_connect_body_battery_lowest",
        "sensor.garmin_connect_body_battery_charged",
        "sensor.garmin_connect_body_battery_drained",
        "sensor.garmin_connect_lowest_heart_rate",
        "sensor.garmin_connect_highest_heart_rate",
        "sensor.garmin_connect_lowest_spo2",
        "sensor.garmin_connect_latest_spo2",
        "sensor.garmin_connect_lowest_respiration_rate",
        "sensor.garmin_connect_highest_respiration_rate",
        "sensor.garmin_connect_latest_respiration_rate",
        "sensor.garmin_connect_deep_sleep",
        "sensor.garmin_connect_light_sleep",
        "sensor.garmin_connect_rem_sleep",
        "sensor.garmin_connect_awake_time",
        "sensor.garmin_connect_hrv_weekly_average",
        "sensor.garmin_connect_bmi",
        "sensor.garmin_connect_body_fat",
        "sensor.garmin_connect_last_weigh_in",
        "sensor.garmin_connect_last_activity_type",
        "sensor.garmin_connect_last_activity_distance",
        "sensor.garmin_connect_last_activity_calories",
        "sensor.garmin_connect_last_activity_average_heart_rate",
    }


@pytest.mark.usefixtures("entity_registry_enabled_by_default")
async def test_body_battery_charge_resets_at_garmin_midnight(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that the Body Battery charged and drained are daily totals."""
    await _setup(hass, mock_config_entry)

    for key in ("charged", "drained"):
        sensor = hass.states.get(f"sensor.garmin_connect_body_battery_{key}")
        assert sensor is not None
        assert sensor.attributes["last_reset"] == "2026-10-23T00:00:00+02:00"


async def test_daily_totals_reset_at_garmin_midnight(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that daily totals reset at midnight in the Garmin time zone."""
    await _setup(hass, mock_config_entry)

    calories = hass.states.get("sensor.garmin_connect_total_calories")
    body_battery = hass.states.get("sensor.garmin_connect_body_battery")

    assert calories is not None
    assert calories.attributes["state_class"] == "total"
    assert calories.attributes["last_reset"] == "2026-10-23T00:00:00+02:00"
    assert body_battery is not None
    assert "last_reset" not in body_battery.attributes


async def test_sensors_unknown_without_summary(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that sensors are unknown when there is no summary."""
    mock_client.async_get_daily_summary.return_value = None

    await _setup(hass, mock_config_entry)

    calories = hass.states.get("sensor.garmin_connect_total_calories")
    assert calories is not None
    assert calories.state == STATE_UNKNOWN
    assert calories.attributes.get("last_reset") is None


async def test_sensors_unknown_for_day_without_data(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that sensors are unknown for a day without data."""
    mock_client.async_get_daily_summary.return_value = DailySummary.from_dict(
        load_json("daily_summary_empty.json")
    )

    await _setup(hass, mock_config_entry)

    calories = hass.states.get("sensor.garmin_connect_total_calories")
    assert calories is not None
    assert calories.state == STATE_UNKNOWN
    assert calories.attributes["last_reset"] == "2026-10-24T00:00:00+02:00"
    assert hass.states.get("sensor.garmin_connect_steps").state == STATE_UNKNOWN
    assert (
        hass.states.get("sensor.garmin_connect_intensity_minutes").state
        == STATE_UNKNOWN
    )
    assert hass.states.get("sensor.garmin_connect_average_spo2").state == STATE_UNKNOWN
    assert (
        hass.states.get("sensor.garmin_connect_average_respiration_rate").state
        == STATE_UNKNOWN
    )


async def test_intensity_minutes_unknown_without_either_value(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that intensity minutes are unknown without either value."""
    summary = load_json("daily_summary.json")
    del summary["moderateIntensityMinutes"], summary["vigorousIntensityMinutes"]
    mock_client.async_get_daily_summary.return_value = DailySummary.from_dict(summary)

    await _setup(hass, mock_config_entry)

    assert (
        hass.states.get("sensor.garmin_connect_intensity_minutes").state
        == STATE_UNKNOWN
    )


async def test_entities_share_one_service_device(
    hass: HomeAssistant,
    mock_client: AsyncMock,
    mock_config_entry: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    """Test that all entities belong to one service device."""
    await _setup(hass, mock_config_entry)

    device = device_registry.async_get_device_by_identifier(
        ("garmin_connect_personal", ACCOUNT_ID), mock_config_entry.entry_id
    )

    assert device is not None
    assert device.entry_type is dr.DeviceEntryType.SERVICE
    assert device.name == "Garmin Connect"
    entities = er.async_entries_for_device(
        entity_registry, device.id, include_disabled_entities=True
    )
    assert {e.unique_id for e in entities} >= {
        f"{ACCOUNT_ID}_total_calories",
        f"{ACCOUNT_ID}_active_calories",
    }


async def test_sensors_attribute_garmin(
    hass: HomeAssistant, mock_client: AsyncMock, mock_config_entry: MockConfigEntry
) -> None:
    """Test that the sensors name Garmin as the data source."""
    await _setup(hass, mock_config_entry)

    sensor = hass.states.get("sensor.garmin_connect_steps")

    assert sensor is not None
    assert sensor.attributes["attribution"] == "Data provided by Garmin"
