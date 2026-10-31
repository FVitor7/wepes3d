"""
CoordSpace: conversores int16<->float de um asset (shared).

O bloco de geometria (vertices/normais/UVs int16) tem layout IDENTICO entre
face e trofeu; muda so a CONVENCAO de eixos/escala. Cada asset constroi seu
`CoordSpace` em `faces/profile.py` / `trophy/profile.py`. Aqui ficam:

  - a dataclass CoordSpace (tipo);
  - as conversoes de UV (iguais nos dois assets: V invertido).
"""

from dataclasses import dataclass
from typing import Callable, Tuple

from ..constants import UV_FACTOR


def clamp16(v: int) -> int:
    return max(-32768, min(32767, v))


# ============================================================================
# UV (igual para face e trofeu)
# ============================================================================

def obj_to_int16_uv(u: float, v: float) -> Tuple[int, int]:
    """OBJ (u,v) -> stored (iu, iv). Inverte V."""
    return (clamp16(round(u / UV_FACTOR)), clamp16(round((1.0 - v) / UV_FACTOR)))


def int16_to_obj_uv(u: int, v: int) -> Tuple[float, float]:
    """stored (u,v) -> OBJ (u*UV_FACTOR, 1 - v*UV_FACTOR)."""
    return (u * UV_FACTOR, 1.0 - v * UV_FACTOR)


# ============================================================================
# CoordSpace
# ============================================================================

@dataclass(frozen=True)
class CoordSpace:
    """Conversores int16<->float de um asset. obj = espaco Wavefront (Blender)."""
    name: str
    obj_to_int16_vertex: Callable[[float, float, float], Tuple[int, int, int]]
    int16_to_obj_vertex: Callable[[int, int, int], Tuple[float, float, float]]
    obj_to_int16_uv: Callable[[float, float], Tuple[int, int]]
    int16_to_obj_uv: Callable[[int, int], Tuple[float, float]]
    obj_to_int16_normal: Callable[[float, float, float], Tuple[int, int, int]]
