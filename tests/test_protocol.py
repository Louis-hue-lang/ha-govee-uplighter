"""Trames comparées octet par octet aux relevés de govee-lan-bridge, et règles du H60B0."""
import importlib.util
import pathlib

_path = pathlib.Path(__file__).parents[1] / "custom_components" / "govee_uplighter" / "protocol.py"
_spec = importlib.util.spec_from_file_location("protocol", _path)
P = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(P)


def hexf(b):
    return b.hex(" ")


def test_frames_match_captures():
    cases = {
        "33 30 03 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00": P.f_section(3, False),
        "33 30 01 01 00 00 00 00 00 00 00 00 00 00 00 00 00 00 00 03": P.f_section(1, True),
        "33 05 2c 03 01 0a 8c 00 00 00 00 00 00 00 00 00 00 00 00 9e": P.f_kelvin(3, 2700),
        "33 05 2c 03 01 19 64 00 00 00 00 00 00 00 00 00 00 00 00 65": P.f_kelvin(3, 6500),
        "33 05 2c 03 02 01 00 00 00 00 00 00 00 00 00 00 00 00 00 1a": P.f_brightness(3, 1),
        "33 05 2c 01 02 64 00 00 00 00 00 00 00 00 00 00 00 00 00 7d": P.f_brightness(1, 100),
        "33 05 2c 01 03 37 00 00 00 00 00 00 00 00 00 00 00 00 00 2f": P.f_flow(55),
        "33 05 2c 01 01 00 ff ff 00 00 00 00 00 00 00 00 00 00 00 1a": P.f_rgb(1, 0, 255, 255),
    }
    for want, got in cases.items():
        assert hexf(got) == want


def test_lower_never_gets_colour():
    u = P.Uplighter()
    frames = u.apply({"lower": {"on": True, "rgb": (255, 0, 0), "kelvin": None}})
    assert all(not hexf(f).startswith("33 05 2c 03 01") or f[7:10] == b"\0\0\0" for f in frames)


def test_two_section_limit_turns_off_longest_on():
    u = P.Uplighter()
    u.apply({"ripple": {"on": True}})
    u.apply({"side": {"on": True}})
    frames = [hexf(f) for f in u.apply({"lower": {"on": True}})]
    assert frames[0].startswith("33 30 01 00")  # ripple, allumée la première, s'éteint
    assert not u.state["ripple"]["on"] and u.state["side"]["on"] and u.state["lower"]["on"]


def test_per_zone_white_is_independent():
    u = P.Uplighter()
    frames = [hexf(f) for f in u.apply({"ripple": {"on": True, "kelvin": 2700}, "lower": {"on": True, "kelvin": 6500}})]
    assert any(f.startswith("33 05 2c 01 01") and "0a 8c" in f for f in frames)
    assert any(f.startswith("33 05 2c 03 01 19 64") for f in frames)


def test_side_segments_masks():
    u = P.Uplighter()
    u.apply({"side": {"on": True}})
    frames = [hexf(f) for f in u.apply({"segments": {0: {"rgb": (0, 255, 0)}, 3: {"rgb": (0, 255, 0)}}})]
    assert any(f.startswith("33 05 2c 02 01 00 ff 00 00 00 09") for f in frames)  # masque 0b1001


def test_lamp_off_is_power_only():
    u = P.Uplighter()
    assert [hexf(f) for f in u.apply({"lamp": {"on": False}})] == [hexf(P.f_power(False))]


def test_flow_clamped():
    u = P.Uplighter()
    assert hexf(u.apply({"flow": 250})[0]).startswith("33 05 2c 01 03 64")
