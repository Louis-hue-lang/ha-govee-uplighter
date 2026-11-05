"""Configuration : adresse IP de la lampe (contrôle LAN activé dans l'app Govee Home)."""
from __future__ import annotations

import ipaddress

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_NAME

from .const import DEFAULT_NAME, DOMAIN


def _valid(host: str) -> bool:
    try:
        ipaddress.IPv4Address(host)
    except ValueError:
        return False
    return True


class UplighterConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if _valid(host):
                await self.async_set_unique_id(host)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=user_input[CONF_NAME].strip() or DEFAULT_NAME, data={CONF_HOST: host})
            errors[CONF_HOST] = "invalid_host"
        schema = vol.Schema({vol.Required(CONF_HOST): str, vol.Required(CONF_NAME, default=DEFAULT_NAME): str})
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_reconfigure(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Nouvelle adresse IP si le routeur en a donné une autre à la lampe."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            host = user_input[CONF_HOST].strip()
            if _valid(host):
                return self.async_update_reload_and_abort(entry, data={CONF_HOST: host}, unique_id=host)
            errors[CONF_HOST] = "invalid_host"
        schema = vol.Schema({vol.Required(CONF_HOST, default=entry.data[CONF_HOST]): str})
        return self.async_show_form(step_id="reconfigure", data_schema=schema, errors=errors)
