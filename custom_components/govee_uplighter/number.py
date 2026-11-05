"""Débit : vitesse de rotation de la lentille de l'ondulation (0 ≈ figée)."""
from __future__ import annotations

from homeassistant.components.number import NumberMode, RestoreNumber
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import UplighterEntity


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([FlowNumber(entry.runtime_data)])


class FlowNumber(UplighterEntity, RestoreNumber):
    _attr_native_min_value = 0
    _attr_native_max_value = 100
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER

    def __init__(self, hub) -> None:
        super().__init__(hub, "flow")

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_number_data()
        if last is not None and last.native_value is not None:
            self.hub.model.flow = int(last.native_value)
        await super().async_added_to_hass()

    @property
    def native_value(self) -> float:
        return self.hub.model.flow

    async def async_set_native_value(self, value: float) -> None:
        self.hub.queue("flow", int(value))
