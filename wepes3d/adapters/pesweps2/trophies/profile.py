"""
TROPHY adapter: what is different from faces.

- Coordinates: stored (sx, sz, -sy), factor = +0.001553 (Y is negated).
- NESTED container: payload[8] = container 00 06 00 00 -> base = +32 ->
  section directory (.mdl sub-models). sec0 = trophy; sec1+ = stand/stage.
- Resize: moves the directory entries (after the target) + the ABS pointers
  of the outer header (e.g. the texture container at payload[0x0C]).
- max_parts: None (trophies have 14-31 parts per sub-model; no limit of 8).

See docs/08-trophies.md.
"""

import struct
from typing import List, Tuple

from ....shared.constants import MAGIC_MODEL, CONTAINER_MAGIC, NORMAL_SCALE
from ....shared.geometry import CoordSpace, obj_to_int16_uv, int16_to_obj_uv, clamp16
from ....shared.pipeline import AssetProfile

TROPHY_VERTEX_FACTOR = 0.001553
"""Trophy vertex factor (positive). Same size as the face |VERTEX_FACTOR|, but
WITHOUT the negative sign — the axis flip comes from negating Y."""


# ============================================================================
# Trophy coordinates
# ============================================================================

def obj_to_int16_vertex(x: float, y: float, z: float) -> Tuple[int, int, int]:
    """OBJ (x,y,z) -> stored (sx, sz, -sy). Flips Y."""
    f = TROPHY_VERTEX_FACTOR
    return (clamp16(round(x / f)), clamp16(round(z / f)), clamp16(round(-y / f)))


def int16_to_obj_vertex(s0: int, s1: int, s2: int) -> Tuple[float, float, float]:
    """stored (s0,s1,s2) -> OBJ (s0*f, -s2*f, s1*f)."""
    f = TROPHY_VERTEX_FACTOR
    return (s0 * f, -s2 * f, s1 * f)


def obj_to_int16_normal(nx: float, ny: float, nz: float) -> Tuple[int, int, int]:
    """Unit normal -> int16, with the same axis order as the trophy vertices
    (nx, nz, -ny). Check it in the game when you use recount with normals."""
    return (clamp16(round(nx * NORMAL_SCALE)),
            clamp16(round(nz * NORMAL_SCALE)),
            clamp16(round(-ny * NORMAL_SCALE)))


COORD = CoordSpace(
    name="trophy",
    obj_to_int16_vertex=obj_to_int16_vertex,
    int16_to_obj_vertex=int16_to_obj_vertex,
    obj_to_int16_uv=obj_to_int16_uv,
    int16_to_obj_uv=int16_to_obj_uv,
    obj_to_int16_normal=obj_to_int16_normal,
)


# ============================================================================
# Nested container: section directory (.mdl)
# ============================================================================

def section_offsets(payload: bytes) -> List[int]:
    """ABSOLUTE offsets of each sub-model (.mdl) in the section directory.
    sec0 = main trophy; sec1+ = stand/stage/etc."""
    offset_file_1 = struct.unpack_from("<I", payload, 8)[0]
    if payload[offset_file_1:offset_file_1 + 4] != CONTAINER_MAGIC:
        raise ValueError("The asset is not a trophy (no 00060000 container).")
    base = offset_file_1 + 32
    count = struct.unpack_from("<I", payload, base)[0]
    offsets: List[int] = []
    for i in range(count):
        rel = struct.unpack_from("<I", payload, base + 8 + 4 * i)[0]
        ab = base + rel
        if payload[ab:ab + 4] == MAGIC_MODEL:
            offsets.append(ab)
    return offsets


def locate(payload: bytes, section: int = 0) -> int:
    """Offset of the sub-model `section` (0 = main trophy)."""
    secs = section_offsets(payload)
    if not (0 <= section < len(secs)):
        raise ValueError(f"section {section} does not exist ({len(secs)} sub-models).")
    return secs[section]


# ============================================================================
# Resize: section directory (+delta) + outer header (ABS pointers)
# ============================================================================

def patch_resize(payload: bytes, model_offset: int, pre_parts_size: int,
                 orig_parts_end: int, new_parts_end: int) -> Tuple[bytes, int]:
    """
    When the target changes size by delta, moves these by +delta:
      - the directory entries (relative to base) whose absolute target is
        >= orig_parts_end;
      - the uint32 values of the outer header (0x00..base, ABS) that are
        >= orig_parts_end (e.g. the texture container at payload[0x0C]).
    `pre_parts_size` is not used (kept so the signature matches).
    The end of the parts in the model header (+0x2C) is written by the
    importer.
    """
    delta = new_parts_end - orig_parts_end
    if delta == 0:
        return payload, 0
    arr = bytearray(payload)
    offset_file_1 = struct.unpack_from("<I", arr, 8)[0]
    base = offset_file_1 + 32
    count = struct.unpack_from("<I", arr, base)[0]
    patched = 0

    for i in range(count):
        off = base + 8 + 4 * i
        if off + 4 > len(arr):
            break
        rel = struct.unpack_from("<I", arr, off)[0]
        if base + rel >= orig_parts_end:      # section after the target -> move it
            struct.pack_into("<I", arr, off, rel + delta)
            patched += 1

    for off in range(0, base - 3, 4):
        val = struct.unpack_from("<I", arr, off)[0]
        if orig_parts_end <= val < len(payload):
            struct.pack_into("<I", arr, off, val + delta)
            patched += 1

    return bytes(arr), patched


TROPHY_PROFILE = AssetProfile(
    name="trophy", coord=COORD, max_parts=None,
    locate=locate, patch_resize=patch_resize, list_sections=section_offsets,
)
