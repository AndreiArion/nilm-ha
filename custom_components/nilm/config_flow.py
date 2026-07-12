"""Config flow: pick the meter sensor and detector sensitivity."""
from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    CONF_H,
    CONF_KAPPA,
    CONF_PERIOD,
    CONF_SOURCE,
    CONF_T_SS,
    DEFAULT_H,
    DEFAULT_KAPPA,
    DEFAULT_PERIOD,
    DEFAULT_T_SS,
    DOMAIN,
)


def _num(min_v: float, max_v: float, step: float, unit: str) -> selector.NumberSelector:
    return selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=min_v, max=max_v, step=step, unit_of_measurement=unit,
            mode=selector.NumberSelectorMode.BOX))


class NilmConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Single-step setup."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> config_entries.ConfigFlowResult:
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_SOURCE])
            self._abort_if_unique_id_configured()
            return self.async_create_entry(
                title=f"NILM ({user_input[CONF_SOURCE]})", data=user_input)

        schema = vol.Schema({
            vol.Required(CONF_SOURCE): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="sensor")),
            vol.Required(CONF_PERIOD, default=DEFAULT_PERIOD): _num(1, 60, 1, "s"),
            vol.Required(CONF_T_SS, default=DEFAULT_T_SS): _num(5, 100, 1, "VA"),
            vol.Required(CONF_KAPPA, default=DEFAULT_KAPPA): _num(5, 100, 1, "VA"),
            vol.Required(CONF_H, default=DEFAULT_H): _num(10, 200, 1, "VA"),
        })
        return self.async_show_form(step_id="user", data_schema=schema)
