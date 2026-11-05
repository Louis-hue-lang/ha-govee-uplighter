"""Lumières : lampe entière, Ondulante, Latérale (avec ses 8 segments) et Inférieure."""
from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.light import (
    ATTR_BRIGHTNESS,
    ATTR_COLOR_TEMP_KELVIN,
    ATTR_RGB_COLOR,
    ColorMode,
    LightEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv, entity_platform
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .entity import UplighterEntity
from .protocol import MAX_K, MIN_K, SIDE_SEGMENTS

SET_SEGMENTS_SCHEMA = {
    vol.Required("segments"): vol.All(cv.ensure_list, [vol.All(vol.Coerce(int), vol.Range(min=1, max=SIDE_SEGMENTS))]),
    vol.Exclusive(ATTR_RGB_COLOR, "colour"): vol.All(vol.Coerce(tuple), vol.ExactSequence((cv.byte,) * 3)),
    vol.Exclusive(ATTR_COLOR_TEMP_KELVIN, "colour"): vol.All(vol.Coerce(int), vol.Range(min=MIN_K, max=MAX_K)),
    vol.Optional("brightness_pct"): vol.All(vol.Coerce(int), vol.Range(min=0, max=100)),
}


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    hub = entry.runtime_data
    async_add_entities(
        [LampLight(hub), SectionLight(hub, "ripple"), SectionLight(hub, "side"), SectionLight(hub, "lower")]
    )
    entity_platform.async_get_current_platform().async_register_entity_service(
        "set_segments", SET_SEGMENTS_SCHEMA, "async_set_segments"
    )


class LampLight(UplighterEntity, LightEntity, RestoreEntity):
    """Marche / arrêt et luminosité générale."""

    _attr_name = None
    _attr_color_mode = ColorMode.BRIGHTNESS
    _attr_supported_color_modes = {ColorMode.BRIGHTNESS}

    def __init__(self, hub) -> None:
        super().__init__(hub, "lamp")
        self._attr_translation_key = None

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_state()
        if last is not None:
            self.hub.model.power["on"] = last.state == "on"
            if last.attributes.get(ATTR_BRIGHTNESS):
                self.hub.model.power["brightness"] = last.attributes[ATTR_BRIGHTNESS]
        await super().async_added_to_hass()

    @property
    def is_on(self) -> bool:
        return self.hub.model.power["on"]

    @property
    def brightness(self) -> int:
        return self.hub.model.power["brightness"]

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.hub.queue("lamp", {"on": True, "brightness": kwargs.get(ATTR_BRIGHTNESS)})

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.hub.queue("lamp", {"on": False})

    async def async_set_segments(self, **kwargs: Any) -> None:
        raise ServiceValidationError("set_segments se lance sur la lumière Latérale")


class SectionLight(UplighterEntity, LightEntity, RestoreEntity):
    """Une zone : Ondulante (ripple), Latérale (side) ou Inférieure (lower, blanc seulement)."""

    _attr_min_color_temp_kelvin = MIN_K
    _attr_max_color_temp_kelvin = MAX_K

    def __init__(self, hub, name: str) -> None:
        super().__init__(hub, name)
        self._attr_supported_color_modes = (
            {ColorMode.COLOR_TEMP} if name == "lower" else {ColorMode.COLOR_TEMP, ColorMode.RGB}
        )

    @property
    def _s(self) -> dict:
        return self.hub.model.state[self.key]

    async def async_added_to_hass(self) -> None:
        last = await self.async_get_last_state()
        if last is not None:
            a = last.attributes
            data: dict = {"on": last.state == "on"}
            if a.get(ATTR_BRIGHTNESS):
                data["brightness"] = a[ATTR_BRIGHTNESS]
            if a.get("color_mode") == ColorMode.RGB and a.get(ATTR_RGB_COLOR) and self.key != "lower":
                data["mode"], data["rgb"] = "rgb", tuple(a[ATTR_RGB_COLOR])
            elif a.get(ATTR_COLOR_TEMP_KELVIN):
                data["mode"], data["kelvin"] = "color_temp", a[ATTR_COLOR_TEMP_KELVIN]
            self.hub.model.restore_section(self.key, data)
            if self.key == "side" and isinstance(a.get("segments"), list):
                for seg, saved in zip(self.hub.model.segs, a["segments"]):
                    seg.update({k: (tuple(v) if k == "rgb" else v) for k, v in saved.items() if k in seg})
        await super().async_added_to_hass()

    @property
    def is_on(self) -> bool:
        return self.hub.model.section_on(self.key)

    @property
    def brightness(self) -> int:
        return self._s["brightness"]

    @property
    def color_mode(self) -> ColorMode:
        return ColorMode.RGB if self._s["mode"] == "rgb" and self.key != "lower" else ColorMode.COLOR_TEMP

    @property
    def rgb_color(self) -> tuple[int, int, int] | None:
        return self._s.get("rgb")

    @property
    def color_temp_kelvin(self) -> int:
        return self._s["kelvin"]

    @property
    def extra_state_attributes(self) -> dict | None:
        if self.key != "side":
            return None
        # Lu par la carte pour dessiner l'anneau ; repris au redémarrage
        return {"segments": [dict(seg) for seg in self.hub.model.segs]}

    async def async_turn_on(self, **kwargs: Any) -> None:
        cmd = {"on": True, "brightness": kwargs.get(ATTR_BRIGHTNESS), "kelvin": kwargs.get(ATTR_COLOR_TEMP_KELVIN)}
        if self.key != "lower":
            cmd["rgb"] = kwargs.get(ATTR_RGB_COLOR)
        self.hub.queue(self.key, cmd)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.hub.queue(self.key, {"on": False})

    async def async_set_segments(self, **kwargs: Any) -> None:
        if self.key != "side":
            raise ServiceValidationError("set_segments se lance sur la lumière Latérale")
        cmd: dict = {"rgb": kwargs.get(ATTR_RGB_COLOR), "kelvin": kwargs.get(ATTR_COLOR_TEMP_KELVIN)}
        if kwargs.get("brightness_pct") is not None:
            if kwargs["brightness_pct"] == 0:
                cmd = {"on": False}
            else:
                cmd["brightness"] = round(kwargs["brightness_pct"] * 255 / 100)
        self.hub.queue("segments", {i - 1: dict(cmd) for i in kwargs["segments"]})
