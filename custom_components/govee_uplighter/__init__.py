"""Govee Uplighter (local) : zones, anneau, blanc par zone et débit du H60B0 par le réseau local."""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import time

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_HOST, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import BATCH_WINDOW, LAMP_PORT, MAX_FRAMES, MIN_GAP, SIGNAL_UPDATE
from .protocol import Uplighter

_LOGGER = logging.getLogger(__name__)
PLATFORMS = [Platform.LIGHT, Platform.NUMBER]


class _Sender(asyncio.DatagramProtocol):
    """Rien à recevoir : la lampe répond sur le port 4002, que l'intégration Govee cloud écoute déjà."""


class UplighterHub:
    """Lampe d'une entrée : état supposé, regroupement des commandes et envoi espacé."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.host: str = entry.data[CONF_HOST]
        self.model = Uplighter()
        self._pending: dict = {}
        self._timer: asyncio.TimerHandle | None = None
        self._lock = asyncio.Lock()
        self._last = 0.0
        self._transport: asyncio.DatagramTransport | None = None

    @property
    def signal(self) -> str:
        return SIGNAL_UPDATE.format(self.entry.entry_id)

    async def async_start(self) -> None:
        self._transport, _ = await self.hass.loop.create_datagram_endpoint(
            _Sender, remote_addr=(self.host, LAMP_PORT)
        )

    def stop(self) -> None:
        if self._timer:
            self._timer.cancel()
        if self._transport:
            self._transport.close()

    @callback
    def queue(self, key: str, cmd) -> None:
        """Ajoute une commande au lot en cours ; le lot part BATCH_WINDOW après la première."""
        if isinstance(cmd, dict) and key != "segments":
            cmd = {k: v for k, v in cmd.items() if v is not None}  # ne pas effacer une valeur du même lot
        if key == "segments":
            segs = self._pending.setdefault("segments", {})
            for i, c in cmd.items():
                segs.setdefault(i, {}).update({k: v for k, v in c.items() if v is not None})
        elif isinstance(cmd, dict):
            self._pending.setdefault(key, {}).update(cmd)
        else:
            self._pending[key] = cmd
        if self._timer is None:
            self._timer = self.hass.loop.call_later(BATCH_WINDOW, self._flush)

    @callback
    def _flush(self) -> None:
        pending, self._pending, self._timer = self._pending, {}, None
        frames = self.model.apply(pending)
        async_dispatcher_send(self.hass, self.signal)
        if frames:
            self.entry.async_create_background_task(self.hass, self.async_send(frames), "govee_uplighter_send")

    async def async_send(self, frames: list[bytes]) -> None:
        for i in range(0, len(frames), MAX_FRAMES):
            chunk = frames[i : i + MAX_FRAMES]
            msg = {"msg": {"cmd": "ptReal", "data": {"command": [base64.b64encode(f).decode() for f in chunk]}}}
            async with self._lock:
                wait = self._last + MIN_GAP - time.monotonic()
                if wait > 0:
                    await asyncio.sleep(wait)
                if self._transport is None:
                    return
                self._transport.sendto(json.dumps(msg).encode())
                self._last = time.monotonic()
            _LOGGER.debug("-> %s : %s", self.host, " | ".join(f.hex(" ") for f in chunk))


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hub = UplighterHub(hass, entry)
    await hub.async_start()
    entry.runtime_data = hub
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def _async_reload(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if ok:
        entry.runtime_data.stop()
    return ok
