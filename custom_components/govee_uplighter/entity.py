"""Base commune des entités : appareil, rafraîchissement après chaque lot envoyé."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from . import UplighterHub
from .const import DOMAIN


class UplighterEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_assumed_state = True  # la lampe ne renvoie pas l'état de ses zones

    def __init__(self, hub: UplighterHub, key: str) -> None:
        self.hub = hub
        self.key = key
        self._attr_unique_id = f"{hub.entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, hub.entry.entry_id)},
            name=hub.entry.title,
            manufacturer="Govee",
            model="H60B0 Uplighter",
        )

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(async_dispatcher_connect(self.hass, self.hub.signal, self.async_write_ha_state))
