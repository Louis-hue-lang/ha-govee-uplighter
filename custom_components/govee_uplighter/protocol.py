"""Protocole local du lampadaire Govee Uplighter H60B0, sans dépendance à Home Assistant.

Trames et règles reprises de SamWiIIiams/govee-lan-bridge (licence MIT), qui les a relevées dans le
trafic Bluetooth de l'app Govee Home et vérifiées sur la lampe. Chaque trame fait 20 octets (données,
zéros, XOR) ; plusieurs partent dans un message LAN ``ptReal`` vers le port UDP 4003.

Constaté sur la lampe de Louis le 2026-11-05 : blanc du plafond et du bas réglés séparément, débit 0-100.
"""
from __future__ import annotations

import math

MIN_K, MAX_K = 2700, 6500  # hors de cette plage le H60B0 s'éteint jusqu'à un réglage valide
SECTIONS = {"ripple": 1, "side": 2, "lower": 3}
SIDE_SEGMENTS = 8  # anneau latéral ; bit n du masque = segment n+1
SIDE_OFF_PCT = 1  # anneau diffus : la luminosité minimale est son « éteint »
DEFAULT_RGB = (255, 200, 150)


def frame(*data: int) -> bytes:
    """Trame Govee de 20 octets : données, zéros, somme XOR."""
    b = list(data) + [0] * (19 - len(data))
    x = 0
    for v in b:
        x ^= v
    return bytes(b + [x])


def kelvin_to_rgb(k: int) -> tuple[int, int, int]:
    """RVB approché d'une température (l'app l'envoie avec la valeur en kelvins)."""
    t = k / 100.0
    if t <= 66:
        r = 255.0
        g = 99.4708025861 * math.log(t) - 161.1195681661
        b = 0.0 if t <= 19 else 138.5177312231 * math.log(t - 10) - 305.0447927307
    else:
        r = 329.698727446 * ((t - 60) ** -0.1332047592)
        g = 288.1221695283 * ((t - 60) ** -0.0755148492)
        b = 255.0
    return tuple(max(0, min(255, int(c))) for c in (r, g, b))  # type: ignore[return-value]


def clamp_k(k: float) -> int:
    return max(MIN_K, min(MAX_K, int(k)))


def pct(brightness_255: float) -> int:
    return max(1, min(100, round(int(brightness_255) * 100 / 255)))


def f_power(on: bool) -> bytes:
    return frame(0x33, 0x01, 1 if on else 0)


def f_master(p: int) -> bytes:
    return frame(0x33, 0x04, p)


def f_section(sec: int, on: bool) -> bytes:
    return frame(0x33, 0x30, sec, 1 if on else 0)


def f_flow(v: float) -> bytes:
    return frame(0x33, 0x05, 0x2C, 0x01, 0x03, max(0, min(100, int(v))))


def f_brightness(sec: int, p: int, mask: int = 0xFF) -> bytes:
    if sec == 2:
        return frame(0x33, 0x05, 0x2C, 2, 0x02, p, mask)  # l'anneau veut le masque de segments
    return frame(0x33, 0x05, 0x2C, sec, 0x02, p)


def f_rgb(sec: int, r: int, g: int, b: int, mask: int = 0xFF) -> bytes:
    if sec == 3:
        raise ValueError("la lampe du bas n'a pas de couleur")  # des octets RVB l'éteignent
    extra = (mask,) if sec == 2 else ()
    return frame(0x33, 0x05, 0x2C, sec, 0x01, r, g, b, 0, 0, *extra)


def f_kelvin(sec: int, k: float, mask: int = 0xFF) -> bytes:
    k = clamp_k(k)
    if sec == 3:
        return frame(0x33, 0x05, 0x2C, 3, 0x01, k >> 8, k & 0xFF)  # pas d'octets RVB pour le bas
    r, g, b = kelvin_to_rgb(k)
    extra = (mask,) if sec == 2 else ()
    return frame(0x33, 0x05, 0x2C, sec, 0x01, r, g, b, k >> 8, k & 0xFF, *extra)


def new_light(with_rgb: bool = True) -> dict:
    s = {"on": False, "brightness": 255, "mode": "color_temp", "kelvin": 4000}
    if with_rgb:
        s["rgb"] = DEFAULT_RGB
    return s


def apply_colour(target: dict, cmd: dict) -> bool:
    """Recopie couleur / blanc / luminosité d'une commande ; True si la teinte a changé."""
    changed = False
    if cmd.get("rgb") is not None and "rgb" in target:
        target["rgb"], target["mode"] = tuple(int(v) for v in cmd["rgb"]), "rgb"
        changed = True
    elif cmd.get("kelvin") is not None:
        target["kelvin"], target["mode"] = clamp_k(cmd["kelvin"]), "color_temp"
        changed = True
    if cmd.get("brightness") is not None:
        target["brightness"] = int(cmd["brightness"])
    return changed


class Uplighter:
    """État supposé de la lampe et traduction des commandes en trames.

    La lampe ne renvoie pas l'état de ses zones : l'état est « dernier réglage envoyé ».
    Commandes (dict) : ``on`` (bool), ``brightness`` (0-255), ``rgb`` (r, g, b), ``kelvin``.
    """

    def __init__(self) -> None:
        self.power = {"on": True, "brightness": 255}
        self.state = {"ripple": new_light(), "side": new_light(), "lower": new_light(with_rgb=False)}
        self.segs = [dict(new_light(), on=True) for _ in range(SIDE_SEGMENTS)]
        self.flow = 20
        self.on_order: list[str] = []  # zones dans l'ordre d'allumage (la lampe en accepte deux)

    # -- état ------------------------------------------------------------------

    def section_on(self, name: str) -> bool:
        return self.power["on"] and self.state[name]["on"]

    def restore_section(self, name: str, data: dict) -> None:
        self.state[name].update(data)
        if data.get("on") and name not in self.on_order:
            self.on_order.append(name)

    # -- trames ----------------------------------------------------------------

    def _colour_frame(self, sec: int, s: dict) -> bytes:
        if s["mode"] == "color_temp" or "rgb" not in s:
            return f_kelvin(sec, s["kelvin"])
        return f_rgb(sec, *s["rgb"])

    def side_segment_frames(self, indices) -> list[bytes]:
        colours: dict[tuple, int] = {}
        levels: dict[int, int] = {}
        for i in indices:
            seg, bit = self.segs[i], 1 << i
            key = ("k", seg["kelvin"]) if seg["mode"] == "color_temp" else ("rgb", *seg["rgb"])
            colours[key] = colours.get(key, 0) | bit
            p = pct(seg["brightness"]) if seg["on"] else SIDE_OFF_PCT
            levels[p] = levels.get(p, 0) | bit
        frames = [f_kelvin(2, k[1], m) if k[0] == "k" else f_rgb(2, *k[1:], mask=m) for k, m in colours.items()]
        frames += [f_brightness(2, p, m) for p, m in levels.items()]
        return frames

    def power_on_frames(self) -> list[bytes]:
        if self.power["on"]:
            return [f_power(True)]
        self.power["on"] = True
        return [f_power(True), f_master(pct(self.power["brightness"]))]

    def make_room(self, name: str, protect=()) -> list[bytes]:
        """Deux zones au plus : éteint la zone allumée depuis le plus longtemps,
        de préférence une qui n'est pas allumée dans le même changement."""
        on = [n for n in self.on_order if n != name and self.state[n]["on"]]
        on.sort(key=lambda n: n in protect)
        frames = []
        while len(on) >= 2:
            victim = on.pop(0)
            self.state[victim]["on"] = False
            self.on_order.remove(victim)
            frames.append(f_section(SECTIONS[victim], False))
        return frames

    def section_frames(self, name: str, cmd: dict, protect=()) -> list[bytes]:
        sec, s, frames = SECTIONS[name], self.state[name], []
        if cmd.get("on") is False:
            s["on"] = False
            if name in self.on_order:
                self.on_order.remove(name)
            return [f_section(sec, False)]
        turning_on = not s["on"] or not self.power["on"]
        s["on"] = True
        if turning_on:
            frames += self.make_room(name, protect)
        # Toujours renvoyer marche + zone : l'état n'est que supposé, et « allumer » une zone déjà
        # allumée est sans effet ; une lampe changée ailleurs (app, coupure) se recale ainsi.
        frames += self.power_on_frames() + [f_section(sec, True)]
        if name in self.on_order:
            self.on_order.remove(name)
        self.on_order.append(name)
        if name == "side":
            return frames + self.side_frames(cmd, turning_on)
        if apply_colour(s, cmd) or turning_on:  # rallumée : remettre sa teinte mémorisée
            frames.append(self._colour_frame(sec, s))
        if cmd.get("brightness") is not None or turning_on:
            frames.append(f_brightness(sec, pct(s["brightness"])))
        return frames

    def side_frames(self, cmd: dict, turning_on: bool) -> list[bytes]:
        """Commande de tout l'anneau : teinte ou luminosité repeignent les 8 segments."""
        s = self.state["side"]
        colour_changed = apply_colour(s, cmd)
        if colour_changed or cmd.get("brightness") is not None:
            for seg in self.segs:
                seg["on"] = True
                if colour_changed:
                    seg["mode"], seg["rgb"], seg["kelvin"] = s["mode"], s["rgb"], s["kelvin"]
                if cmd.get("brightness") is not None:
                    seg["brightness"] = s["brightness"]
            return self.side_segment_frames(range(SIDE_SEGMENTS))
        if turning_on:
            if not any(seg["on"] for seg in self.segs):
                for seg in self.segs:
                    seg["on"] = True
            return self.side_segment_frames(range(SIDE_SEGMENTS))
        return []

    def segment_frames(self, seg_cmds: dict[int, dict], protect=()) -> list[bytes]:
        for i, cmd in seg_cmds.items():
            seg = self.segs[i]
            if cmd.get("on") is False:
                seg["on"] = False
                continue
            seg["on"] = True
            apply_colour(seg, cmd)
        side = self.state["side"]
        if not any(seg["on"] for seg in self.segs):
            return self.section_frames("side", {"on": False}) if side["on"] else []
        if not side["on"] or not self.power["on"]:
            return self.section_frames("side", {"on": True}, protect)
        return self.power_on_frames() + [f_section(2, True)] + self.side_segment_frames(sorted(seg_cmds))

    def apply(self, pending: dict) -> list[bytes]:
        """Traduit un lot de commandes (``lamp``, zones, ``segments``, ``flow``) en trames, sans doublon."""
        frames: list[bytes] = []
        lamp = pending.get("lamp")
        if lamp is not None and lamp.get("on") is False:
            self.power["on"] = False
            return [f_power(False)]
        if lamp is not None:
            frames += self.power_on_frames()
            if lamp.get("brightness") is not None:
                self.power["brightness"] = int(lamp["brightness"])
                frames.append(f_master(pct(self.power["brightness"])))
        seg_cmds = {i: c for i, c in (pending.get("segments") or {}).items() if 0 <= i < SIDE_SEGMENTS}
        offs = [n for n in SECTIONS if n in pending and pending[n].get("on") is False]
        ons = [n for n in SECTIONS if n in pending and n not in offs]
        protect = set(ons) | ({"side"} if any(c.get("on") is not False for c in seg_cmds.values()) else set())
        for name in offs + ons:
            frames += self.section_frames(name, pending[name], protect)
        if seg_cmds:
            frames += self.segment_frames(seg_cmds, protect)
        if "flow" in pending:
            self.flow = max(0, min(100, int(pending["flow"])))
            frames.append(f_flow(self.flow))
        unique: list[bytes] = []
        for f in frames:
            if f not in unique:
                unique.append(f)
        return unique
