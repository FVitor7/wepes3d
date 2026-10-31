"""
Adapter de KIT (uniforme: camisa/corpo, mãos) — export .bin -> .obj.

Engenharia reversa (validada renderizando): os arquivos de kit são blocos
comprimidos `00 06 01 00` que descompactam para uma "pasta de modelos"
(`03 00 FF FF`) — MESMA navegação de estádio. O modelo 3D interno é o de sempre
(leitor universal). A COORDENADA é a MESMA da FACE (kit é equipamento do jogador,
no mesmo espaço do corpo): factor -0.001553, eixos da face.

Mapa dos arquivos de exemplo em `kit/`:
  * `unnamed_1135` — camisa/corpo (5 modelos: LODs/peças)
  * `unnamed_5170` — mãos (4 modelos)
  * `unnamed_5302/5306/6039/6040/6041` — textura/dados (0 modelos 3D)

Por isso toda a lógica é reaproveitada de `shared/folder_models.py`; aqui só
amarramos o `CoordSpace` da face.

API:
    list_kit("kit/unnamed_1135")                 # imprime estrutura
    export_kit("kit/unnamed_1135", "camisa.obj") # 1 modelo (global 0)
    export_kit_complete("kit/unnamed_1135", "kit.obj")    # tudo num .obj
    export_kit_parts("kit/unnamed_1135", "out/kit")       # 1 .obj por modelo
    export_kit_scene([a, b], "cena.obj")         # varios arquivos num .obj
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
