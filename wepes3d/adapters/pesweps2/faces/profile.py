"""
Adapter de FACE/CABELO: o que difere do trofeu para faces.

- Coordenadas: stored (iy, iz, ix), VERTEX_FACTOR = -0.001553, com flip de X.
- Container: modelo DIRETO em payload[8] (MAGIC_MODEL).
- Resize: ponteiros parts_end / parts_end-16 no pre_parts.
- max_parts: 8 (byte[0x04]=8 em todos os exemplos de face).
"""

import struct
from typing import Tuple

from ....shared.constants import VERTEX_FACTOR, NORMAL_SCALE, MAGIC_MODEL
from ....shared.geometry import CoordSpace, obj_to_int16_uv, int16_to_obj_uv, clamp16
from ....shared.pipeline import AssetProfile


# ============================================================================
# Coordenadas da face
# ============================================================================

def obj_to_int16_vertex(x: float, y: float, z: float) -> Tuple[int, int, int]:
    """OBJ (x,y,z) -> stored (iy, iz, ix). Inverte X."""
    return (clamp16(round(y / VERTEX_FACTOR)),
            clamp16(round(z / VERTEX_FACTOR)),
            clamp16(round(x / VERTEX_FACTOR * -1)))


def int16_to_obj_vertex(iy: int, iz: int, ix: int) -> Tuple[float, float, float]:
    """stored (iy, iz, ix) -> OBJ (x,y,z). Reverte flip do X."""
    return (ix * VERTEX_FACTOR * -1, iy * VERTEX_FACTOR, iz * VERTEX_FACTOR)


def obj_to_int16_normal(nx: float, ny: float, nz: float) -> Tuple[int, int, int]:
    """Normal unitaria -> int16, mesmo flip de X dos vertices."""
    return (clamp16(round(-nx * NORMAL_SCALE)),
            clamp16(round(ny * NORMAL_SCALE)),
            clamp16(round(nz * NORMAL_SCALE)))


COORD = CoordSpace(
    name="face",
    obj_to_int16_vertex=obj_to_int16_vertex,
    int16_to_obj_vertex=int16_to_obj_vertex,
    obj_to_int16_uv=obj_to_int16_uv,
    int16_to_obj_uv=int16_to_obj_uv,
    obj_to_int16_normal=obj_to_int16_normal,
)


# ============================================================================
# Container: modelo direto
# ============================================================================

def locate(payload: bytes, section: int = 0) -> int:
    """A face tem o modelo DIRETO em payload[8] (ignora `section`)."""
    offset_file_1 = struct.unpack_from("<I", payload, 8)[0]
    magic = payload[offset_file_1:offset_file_1 + 4]
    if magic != MAGIC_MODEL:
        raise ValueError(f"Nao parece uma face: magic@0x{offset_file_1:X}="
                         f"{magic.hex()} (esperado {MAGIC_MODEL.hex()}).")
    return offset_file_1


# ============================================================================
# Resize: ponteiros parts_end / parts_end-16
# ============================================================================

def patch_resize(payload: bytes, model_offset: int, pre_parts_size: int,
                 orig_parts_end: int, new_parts_end: int) -> Tuple[bytes, int]:
    """Atualiza os uint32 no pre_parts que valem parts_end ou parts_end-16."""
    arr = bytearray(payload)
    patched = 0
    for off in range(0, pre_parts_size - 3, 4):
        val = struct.unpack_from("<I", arr, off)[0]
        if val == orig_parts_end:
            struct.pack_into("<I", arr, off, new_parts_end)
            patched += 1
        elif val == orig_parts_end - 16:
            struct.pack_into("<I", arr, off, new_parts_end - 16)
            patched += 1
    return bytes(arr), patched


FACE_PROFILE = AssetProfile(
    name="face", coord=COORD, max_parts=8,
    locate=locate, patch_resize=patch_resize, list_sections=None,
)
