"""
Adapter de ESTADIO (export .bin/.str -> .obj).

Um arquivo de estadio e' uma "pasta" de modelos (arquibancadas/quadrantes); um
container .bin agrupa varios blocos. O modelo 3D interno (parts/VIF/strip) e' o
MESMO de face/trofeu — so muda a coord (escala 1/256). Toda a logica de leitura
e export e' generica em `shared/pes_archive.py` + `shared/folder_models.py`;
aqui so amarramos o `CoordSpace` do estadio.

API:
    list_stadium("stadium.bin")                       # imprime estrutura
    export_stadium("stadium.str", "m0.obj")           # 1 modelo (global 0)
    export_stadium_complete("stadium.bin", "all.obj") # tudo num .obj so
    export_stadium_parts("stadium.bin", "out/estadio")# 1 .obj por modelo
    export_stadium_scene([a, b, ...], "cena.obj")     # varios arquivos num .obj
"""

from typing import List, Tuple

from ....shared.pipeline import folder as _fm
from .profile import STADIUM_PROFILE

_COORD = STADIUM_PROFILE.coord
_LABEL = "stadium"


def stadium_index(path: str) -> List[Tuple[int, int, int]]:
    return _fm.index(path)


def list_stadium(path: str) -> None:
    _fm.list_models(path, _COORD, _LABEL)


def export_stadium(path: str, obj_path: str, model: int = 0, block: int = None,
                   write_mtl: bool = True, groups: bool = False, dedup: bool = False) -> None:
    _fm.export_model(path, obj_path, _COORD, _LABEL, model=model, block=block,
                     write_mtl=write_mtl, groups=groups, dedup=dedup)


def export_stadium_complete(path: str, obj_path: str, write_mtl: bool = True,
                            dedup: bool = False) -> None:
    _fm.export_complete(path, obj_path, _COORD, _LABEL, write_mtl=write_mtl, dedup=dedup)


def export_stadium_parts(path: str, out_prefix: str, write_mtl: bool = True,
                         groups: bool = False, dedup: bool = False) -> List[str]:
    return _fm.export_parts(path, out_prefix, _COORD, _LABEL, write_mtl=write_mtl,
                            groups=groups, dedup=dedup)


def export_stadium_scene(paths: List[str], obj_path: str, write_mtl: bool = True) -> None:
    _fm.export_scene(paths, obj_path, _COORD, _LABEL, write_mtl=write_mtl)
