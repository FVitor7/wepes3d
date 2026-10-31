"""
AssetProfile: a interface entre o motor (shared) e cada tipo de asset.

O motor (pipeline._import/_export) eh asset-agnostico: recebe um AssetProfile
que encapsula as UNICAS diferencas entre face e trofeu:

  - coord        : sistema de coordenadas (CoordSpace).
  - max_parts    : limite de parts (face=8; trofeu=None).
  - locate       : (payload, section) -> offset absoluto do MAGIC_MODEL.
  - patch_resize : corrige ponteiros do container quando as parts mudam de tamanho.
  - list_sections: (payload) -> offsets dos sub-modelos, ou None se nao aplicavel.

As IMPLEMENTACOES vivem em `faces/profile.py` (FACE_PROFILE) e
`trophy/profile.py` (TROPHY_PROFILE).
"""

from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from ..geometry.coords import CoordSpace


@dataclass(frozen=True)
class AssetProfile:
    name: str
    coord: CoordSpace
    max_parts: Optional[int]
    # locate(payload, section) -> model_offset (offset do 03 00 FF FF)
    locate: Callable[[bytes, int], int]
    # patch_resize(payload, model_offset, pre_parts_size, orig_end, new_end)
    #   -> (payload, n_patched)
    patch_resize: Callable[[bytes, int, int, int, int], Tuple[bytes, int]]
    # list_sections(payload) -> [model_offset, ...] (trofeu) ou None (face)
    list_sections: Optional[Callable[[bytes], List[int]]] = None
