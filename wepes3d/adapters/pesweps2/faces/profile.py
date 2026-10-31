"""
FACE/HAIR adapter: what is different for faces compared with trophies.

- Coordinates: stored (iy, iz, ix), VERTEX_FACTOR = -0.001553, with an X flip.
- Container: the model is DIRECTLY at payload[8] (MAGIC_MODEL).
- Resize: parts_end / parts_end-16 pointers in pre_parts (the end of the
  parts relative to the model, at +0x2C, is written by the importer).
- max_parts: 8 (byte[0x04]=8 in all face examples).
"""

import struct
from typing import Tuple

from ....shared.constants import VERTEX_FACTOR, NORMAL_SCALE, MAGIC_MODEL
from ....shared.geometry import CoordSpace, obj_to_int16_uv, int16_to_obj_uv, clamp16
from ....shared.pipeline import AssetProfile


# ============================================================================
# Face coordinates
# ============================================================================

def obj_to_int16_vertex(x: float, y: float, z: float) -> Tuple[int, int, int]:
    """OBJ (x,y,z) -> stored (iy, iz, ix). Flips X."""
    return (clamp16(round(y / VERTEX_FACTOR)),
            clamp16(round(z / VERTEX_FACTOR)),
            clamp16(round(x / VERTEX_FACTOR * -1)))


def int16_to_obj_vertex(iy: int, iz: int, ix: int) -> Tuple[float, float, float]:
    """stored (iy, iz, ix) -> OBJ (x,y,z). Undoes the X flip."""
    return (ix * VERTEX_FACTOR * -1, iy * VERTEX_FACTOR, iz * VERTEX_FACTOR)


def obj_to_int16_normal(nx: float, ny: float, nz: float) -> Tuple[int, int, int]:
    """Unit normal -> int16, with the same X flip as the vertices."""
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
# Container: direct model
# ============================================================================

def locate(payload: bytes, section: int = 0) -> int:
    """A face has its model DIRECTLY at payload[8] (`section` is ignored)."""
    offset_file_1 = struct.unpack_from("<I", payload, 8)[0]
    magic = payload[offset_file_1:offset_file_1 + 4]
    if magic != MAGIC_MODEL:
        raise ValueError(f"This does not look like a face: magic@0x{offset_file_1:X}="
                         f"{magic.hex()} (expected {MAGIC_MODEL.hex()}).")
    return offset_file_1


# ============================================================================
# Resize: parts_end / parts_end-16 pointers
# ============================================================================

def patch_resize(payload: bytes, model_offset: int, pre_parts_size: int,
                 orig_parts_end: int, new_parts_end: int) -> Tuple[bytes, int]:
    """Updates the uint32 values in pre_parts that are equal to parts_end or parts_end-16."""
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
