"""Config flow for Garmin Connect Personal."""

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from aio_garmin_personal import (
    GarminPersonalAuthenticationError,
    GarminPersonalClient,
    GarminPersonalConnectionError,
    GarminPersonalError,
    GarminPersonalResponseError,
)
import probatio

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_API_KEY
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)
from homeassistant.util import dt as dt_util

from .const import DEFAULT_TITLE, DOMAIN, LOGGER
from .coordinator import async_garmin_time_zone

API_KEY_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_API_KEY): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        )
    }
)


class GarminConnectPersonalConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Garmin Connect Personal."""

    VERSION = 1
    MINOR_VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the Personal API key."""
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            account_id, title = await self._async_validate(api_key, errors)
            if account_id is not None:
                await self.async_set_unique_id(account_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=title, data={CONF_API_KEY: api_key}
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(API_KEY_SCHEMA, user_input),
            errors=errors,
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauthentication after Garmin rejected the stored key."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new key for the same Garmin account."""
        return await self._async_step_replace_key("reauth_confirm", user_input)

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Let the user replace a key that still works, for example before it expires."""
        return await self._async_step_replace_key("reconfigure", user_input)

    async def _async_step_replace_key(
        self, step_id: str, user_input: dict[str, Any] | None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            api_key = user_input[CONF_API_KEY].strip()
            account_id, _ = await self._async_validate(api_key, errors)
            if account_id is not None:
                await self.async_set_unique_id(account_id)
                self._abort_if_unique_id_mismatch(reason="wrong_account")
                entry = (
                    self._get_reauth_entry()
                    if step_id == "reauth_confirm"
                    else self._get_reconfigure_entry()
                )
                return self.async_update_reload_and_abort(
                    entry, data_updates={CONF_API_KEY: api_key}
                )
        return self.async_show_form(
            step_id=step_id, data_schema=API_KEY_SCHEMA, errors=errors
        )

    async def _async_validate(
        self, api_key: str, errors: dict[str, str]
    ) -> tuple[str | None, str]:
        """Return the account ID and display name for a key, or fill `errors`."""
        client = GarminPersonalClient(async_get_clientsession(self.hass), api_key)
        try:
            return await _async_identify_account(client)
        except GarminPersonalAuthenticationError:
            errors["base"] = "invalid_auth"
        except GarminPersonalConnectionError:
            errors["base"] = "cannot_connect"
        except GarminPersonalError:
            LOGGER.exception("Unexpected response from Garmin")
            errors["base"] = "unknown"
        return None, ""


async def _async_identify_account(client: GarminPersonalClient) -> tuple[str, str]:
    """Return the Garmin user profile ID and a title for the entry.

    The profile ID only appears in daily summaries. Garmin returns one for any day, with
    null metrics when there is no data, so today's always identifies the account.
    """
    settings = await client.async_get_user_settings()
    zone = (
        await async_garmin_time_zone(settings.time_zone)
        or dt_util.get_default_time_zone()
    )
    summary = await client.async_get_daily_summary(dt_util.now(zone).date())
    if summary is None:
        raise GarminPersonalResponseError("Daily summary response was empty")
    return str(summary.user_profile_id), _title(settings.display_name)


def _title(display_name: str | None) -> str:
    """Return the display name, unless Garmin has filled it with a generated UUID."""
    if not display_name:
        return DEFAULT_TITLE
    try:
        UUID(display_name)
    except ValueError:
        return display_name
    return DEFAULT_TITLE
