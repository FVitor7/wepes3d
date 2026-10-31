"""
CoordSpace: int16<->float converters of an asset (shared).

The geometry block (int16 vertices/normals/UVs) has the SAME layout in faces
and trophies; only the axis/scale CONVENTION changes. Each asset builds its
own `CoordSpace` in `adapters/pesweps2/<asset>/profile.py`. This module has:

  - the CoordSpace dataclass (the type);
  - the UV conversions (the same for every PS2 asset: V is flipped).
"""

from dataclasses import dataclass
from typing import Callable, Tuple

from ..constants import UV_FACTOR


def clamp16(v: int) -> int:
    return max(-32768, min(32767, v))


# ============================================================================
# UV (the same for face and trophy)
# ============================================================================

def obj_to_int16_uv(u: float, v: float) -> Tuple[int, int]:
    """OBJ (u,v) -> stored (iu, iv). Flips V."""
    return (clamp16(round(u / UV_FACTOR)), clamp16(round((1.0 - v) / UV_FACTOR)))


def int16_to_obj_uv(u: int, v: int) -> Tuple[float, float]:
    """stored (u,v) -> OBJ (u*UV_FACTOR, 1 - v*UV_FACTOR)."""
    return (u * UV_FACTOR, 1.0 - v * UV_FACTOR)


# ============================================================================
# CoordSpace
# ============================================================================

@dataclass(frozen=True)
class CoordSpace:
    """int16<->float converters of an asset. obj = Wavefront space (Blender)."""
    name: str
    obj_to_int16_vertex: Callable[[float, float, float], Tuple[int, int, int]]
    int16_to_obj_vertex: Callable[[int, int, int], Tuple[float, float, float]]
    obj_to_int16_uv: Callable[[float, float], Tuple[int, int]]
    int16_to_obj_uv: Callable[[int, int], Tuple[float, float]]
    obj_to_int16_normal: Callable[[float, float, float], Tuple[int, int, int]]
