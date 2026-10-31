"""CoordSpace: a conversão int16<->float é uma bijeção (lossless)."""

import itertools

import pytest

from wepes3d.shared.geometry.coords import (
    clamp16, obj_to_int16_uv, int16_to_obj_uv,
)
from wepes3d.adapters.pesweps2.faces.profile import COORD as FACE
from wepes3d.adapters.pesweps2.trophies.profile import COORD as TROPHY
from wepes3d.adapters.pesweps2.stadiums.profile import COORD as STADIUM
from wepes3d.adapters.pes6pc.coords import (
    raw_to_obj_vertex, raw_to_obj_uv, PC_SCALE,
)

# Valores int16 representativos (extremos + comuns).
SAMPLES = [-32768, -32767, -1000, -87, -1, 0, 1, 87, 1000, 32767]


@pytest.mark.parametrize("coord", [FACE, TROPHY, STADIUM], ids=lambda c: c.name)
def test_vertex_bijection(coord):
    """int16 -> obj -> int16 recupera os mesmos inteiros (em todos os assets)."""
    for s0, s1, s2 in itertools.islice(
            itertools.product(SAMPLES, SAMPLES, SAMPLES), 0, None, 7):
        x, y, z = coord.int16_to_obj_vertex(s0, s1, s2)
        back = coord.obj_to_int16_vertex(x, y, z)
        assert back == (s0, s1, s2), f"{coord.name}: {(s0,s1,s2)} -> {back}"


@pytest.mark.parametrize("coord", [FACE, TROPHY, STADIUM], ids=lambda c: c.name)
def test_normal_in_range(coord):
    nx, ny, nz = coord.obj_to_int16_normal(0.0, 1.0, 0.0)
    for c in (nx, ny, nz):
        assert -32768 <= c <= 32767


def test_uv_bijection():
    for iu, iv in itertools.product(SAMPLES, SAMPLES):
        u, v = int16_to_obj_uv(iu, iv)
        back = obj_to_int16_uv(u, v)
        assert back == (clamp16(iu), clamp16(iv))


def test_uv_v_is_flipped():
    # V invertido: stored 0 -> obj 1.0
    u, v = int16_to_obj_uv(0, 0)
    assert v == 1.0


def test_clamp16_saturates():
    assert clamp16(99999) == 32767
    assert clamp16(-99999) == -32768
    assert clamp16(5) == 5


def test_face_known_vertex():
    # vert0 de examples/face.bin (stored y,z,x = 293,-1110,0) -> obj conferido.
    x, y, z = FACE.int16_to_obj_vertex(293, -1110, 0)
    assert round(x, 6) == 0.0
    assert round(y, 6) == -0.455029
    assert round(z, 6) == 1.723830


def test_pc_coords_scale_and_uv_flip():
    x, y, z = raw_to_obj_vertex(1.0, 2.0, 3.0)
    assert x == 3.0 * PC_SCALE
    assert y == -1.0 * PC_SCALE
    assert z == -2.0 * PC_SCALE
    assert raw_to_obj_uv(0.25, 0.10) == (0.25, 0.90)
