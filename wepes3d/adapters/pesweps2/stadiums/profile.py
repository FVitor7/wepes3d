"""
STADIUM adapter: what is different from faces/trophies.

- Coordinates: factor = 1/256 = 0.00390625 (big scale). stored (s0,s1,s2)
  -> obj (s0, s2, -s1)  (taken from `stadium_modifier.py`:
  `x,z,y = unpack(3h); v = (x*F, y*F, -z*F)`).
- Navigation: the decompressed payload is a "folder" of sub-models: the total
  at [0], the offset of the table (TOC) at [4], and the ABSOLUTE offsets of
  each model (`MAGIC_MODEL` 03 00 FF FF) from the TOC on. (A stadium has 1..N
  models = stands/quadrants.) See `shared/io/pes_archive.py` for .str (single
  block) vs .bin (00 06 00 00 container of several compressed blocks).
- max_parts: None (stadiums have ~120-150 parts per model).

See docs/09-stadiums-and-kits.md.
"""

from typing import Tuple

from ....shared.constants import NORMAL_SCALE
from ....shared.geometry import CoordSpace, obj_to_int16_uv, int16_to_obj_uv, clamp16
from ....shared.pipeline import AssetProfile
from ....shared.io import model_offsets

STADIUM_VERTEX_FACTOR = 0.00390625
"""1/256. Stadium scale (much bigger than faces/trophies)."""


# ============================================================================
# Stadium coordinates
# ============================================================================

def int16_to_obj_vertex(s0: int, s1: int, s2: int) -> Tuple[float, float, float]:
    """stored (s0,s1,s2) -> OBJ (s0*f, s2*f, -s1*f)."""
    f = STADIUM_VERTEX_FACTOR
    return (s0 * f, s2 * f, -s1 * f)


def obj_to_int16_vertex(x: float, y: float, z: float) -> Tuple[int, int, int]:
    """OBJ (x,y,z) -> stored (x/f, -z/f, y/f) (inverse of int16_to_obj_vertex)."""
    f = STADIUM_VERTEX_FACTOR
    return (clamp16(round(x / f)), clamp16(round(-z / f)), clamp16(round(y / f)))


def obj_to_int16_normal(nx: float, ny: float, nz: float) -> Tuple[int, int, int]:
    """Unit normal -> int16, with the same axis order as the vertices
    (nx, -nz, ny)."""
    return (clamp16(round(nx * NORMAL_SCALE)),
            clamp16(round(-nz * NORMAL_SCALE)),
            clamp16(round(ny * NORMAL_SCALE)))


COORD = CoordSpace(
    name="stadium",
    obj_to_int16_vertex=obj_to_int16_vertex,
    int16_to_obj_vertex=int16_to_obj_vertex,
    obj_to_int16_uv=obj_to_int16_uv,
    int16_to_obj_uv=int16_to_obj_uv,
    obj_to_int16_normal=obj_to_int16_normal,
)


# ============================================================================
# Navigation: "folder" of sub-models (generic, in shared.io.pes_archive)
# ============================================================================

def locate(payload: bytes, section: int = 0) -> int:
    """Offset of the model `section` inside the decompressed payload (block)."""
    offs = model_offsets(payload)
    if not (0 <= section < len(offs)):
        raise ValueError(f"model {section} does not exist ({len(offs)} models in the block).")
    return offs[section]


def patch_resize(payload: bytes, model_offset: int, pre_parts_size: int,
                 orig_parts_end: int, new_parts_end: int) -> Tuple[bytes, int]:
    """Stadium resize (import by parts) is not implemented yet.

    For a roundtrip of the SAME size (delta == 0) it does nothing. A change of
    size would need to move the TOC + the offsets of the next models + (in the
    .bin) the TOC of the outer container — it will be added together with the
    import by parts."""
    if new_parts_end == orig_parts_end:
        return payload, 0
    raise NotImplementedError(
        "stadium resize (import with a different count) is not supported yet; "
        "use a same-size roundtrip, or only export for now.")


STADIUM_PROFILE = AssetProfile(
    name="stadium", coord=COORD, max_parts=None,
    locate=locate, patch_resize=patch_resize, list_sections=model_offsets,
)
