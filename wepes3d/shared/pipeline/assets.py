"""
AssetProfile: the interface between the engine (shared) and each asset type.

The engine (pipeline._import/_export) is asset-agnostic: it receives an
AssetProfile that holds the ONLY differences between faces and trophies:

  - coord        : coordinate system (CoordSpace).
  - max_parts    : parts limit (face=8; trophy=None).
  - locate       : (payload, section) -> absolute offset of the MAGIC_MODEL.
  - patch_resize : fixes the container pointers when the parts change size.
  - list_sections: (payload) -> offsets of the sub-models, or None if it does
                   not apply.

The IMPLEMENTATIONS live in `adapters/pesweps2/faces/profile.py`
(FACE_PROFILE) and `adapters/pesweps2/trophies/profile.py` (TROPHY_PROFILE).
"""

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from ..geometry.coords import CoordSpace


@dataclass(frozen=True)
class AssetProfile:
    name: str
    coord: CoordSpace
    max_parts: Optional[int]
    # locate(payload, section) -> model_offset (offset of 03 00 FF FF)
    locate: Callable[[bytes, int], int]
    # patch_resize(payload, model_offset, pre_parts_size, orig_end, new_end)
    #   -> (payload, n_patched)
    patch_resize: Callable[[bytes, int, int, int, int], Tuple[bytes, int]]
    # list_sections(payload) -> [model_offset, ...] (trophy) or None (face)
    list_sections: Optional[Callable[[bytes], List[int]]] = None
