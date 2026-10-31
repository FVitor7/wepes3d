"""
KIT adapter (uniform: shirt/body, hands) — export .bin -> .obj.

Reverse engineering (checked by rendering): kit files are `00 06 01 00`
compressed blocks that decompress into a "model folder" (`03 00 FF FF`) — the
SAME navigation as stadiums. The internal 3D model is the usual one (universal
reader). The COORDINATES are the SAME as the FACE (a kit is player equipment,
in the same space as the body): factor -0.001553, face axes.

Map of the sample files we analysed (in a local `kit/` folder; they are not
in this repository):
  * `unnamed_1135` — shirt/body (5 models: LODs/pieces)
  * `unnamed_5170` — hands (4 models)
  * `unnamed_5302/5306/6039/6040/6041` — texture/data (0 3D models)

So all the logic comes from `shared/pipeline/folder.py`; here we only plug in
the face `CoordSpace`.

API:
    list_kit("kit/unnamed_1135")                 # prints the structure
    export_kit("kit/unnamed_1135", "shirt.obj")  # 1 model (global 0)
    export_kit_complete("kit/unnamed_1135", "kit.obj")    # everything in one .obj
    export_kit_parts("kit/unnamed_1135", "out/kit")       # 1 .obj per model
    export_kit_scene([a, b], "scene.obj")        # several files in one .obj
"""

from typing import List, Tuple

from ....shared.pipeline import folder as _fm
from ..faces.profile import COORD as KIT_COORD

_LABEL = "kit"


def kit_index(path: str) -> List[Tuple[int, int, int]]:
    return _fm.index(path)


def list_kit(path: str) -> None:
    _fm.list_models(path, KIT_COORD, _LABEL)


def export_kit(path: str, obj_path: str, model: int = 0, block: int = None,
               write_mtl: bool = True, groups: bool = False, dedup: bool = False) -> None:
    _fm.export_model(path, obj_path, KIT_COORD, _LABEL, model=model, block=block,
                     write_mtl=write_mtl, groups=groups, dedup=dedup)


def export_kit_complete(path: str, obj_path: str, write_mtl: bool = True,
                        dedup: bool = False) -> None:
    _fm.export_complete(path, obj_path, KIT_COORD, _LABEL, write_mtl=write_mtl, dedup=dedup)


def export_kit_parts(path: str, out_prefix: str, write_mtl: bool = True,
                     groups: bool = False, dedup: bool = False) -> List[str]:
    return _fm.export_parts(path, out_prefix, KIT_COORD, _LABEL, write_mtl=write_mtl,
                            groups=groups, dedup=dedup)


def export_kit_scene(paths: List[str], obj_path: str, write_mtl: bool = True) -> None:
    _fm.export_scene(paths, obj_path, KIT_COORD, _LABEL, write_mtl=write_mtl)
