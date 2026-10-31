"""
wepes3d: importador/exportador .obj <-> .bin do PES.

Duas plataformas, isoladas em adapters/ (PC e PS2 sao formatos DIFERENTES):
  * PS2 (adapters/pesweps2): FACES/CABELOS, TROFEUS, ESTADIOS, KITS.
        Import + export. int16, modelo 0300ffff, VIF unpacks.
  * PC  (adapters/pes6pc):   FACES e TROFEUS. SO export (.bin/.str -> .obj).
        float32, modelo 20050420, strips por vertex group.

Organizacao (ver docs/11-arquitetura.md):
  shared/   nucleo (motor PS2 + I/O comum), em subpacotes por responsabilidade:
            io/ (bin/archive/obj), geometry/ (coords/transform),
            model/ (parser/reader/strip/rebuilder), pipeline/ (assets/importer/
            exporter/folder/partition) + constants.py. PC reaproveita so o io/.
  adapters/pesweps2/  adapters PS2 finos (profile = coord+navegacao; __init__ =
            wrappers import_/export_). FACE/TROFEU usam o motor importer/
            exporter; ESTADIO/KIT (so export) usam pipeline.folder.
  adapters/pes6pc/    leitor PC proprio (reader/coords) + API de export estilo
            "pasta de modelos" (list/export/complete/parts).

API:

    from wepes3d import (
        import_face, export_face, import_trophy, export_trophy,
        import_auto, export_auto,
        export_stadium, export_stadium_complete, list_stadium,
        export_kit, export_kit_complete, list_kit,
    )

    import_face("face.bin", "rosto.obj", "saida.bin",
                recalculate_normals=True, allow_recount=True, auto_fit=True)
    import_trophy("trofeu.bin", "taca.obj", "saida.bin", section=0, allow_recount=True)
    import_auto("qualquer.bin", "novo.obj", "saida.bin", allow_recount=True)
    export_auto("qualquer.bin", "saida.obj")                 # face/trofeu (detecta tipo)
    export_stadium_complete("stad1_main.bin", "estadio.obj")  # estadio inteiro
    export_kit_complete("kit_1135", "camisa.obj")             # kit
    convert_obj_to_vertex_uv("blender.obj", "pronto.obj")     # 1 UV por vertice

CLI: `python -m wepes3d TEMPLATE OBJ [OUT] --type auto|face|trophy|stadium|kit ...`
Docs em docs/ (08-trofeus, 09-estadios, 10-kits, 11-arquitetura).
"""

__version__ = "2.2.0-dev"

from .shared.io import compress_bin, decompress_bin
from .shared.io import ObjMesh, parse_obj, convert_obj_to_vertex_uv
from .shared.model import (
    Model, Part, parse_model, write_model, detect_asset_type, locate_model,
)
from .adapters.pesweps2 import (
    import_face, export_face,
    import_trophy, export_trophy, trophy_section_offsets,
    export_stadium, export_stadium_complete, export_stadium_parts,
    export_stadium_scene, list_stadium, stadium_index,
    export_kit, export_kit_complete, export_kit_parts, export_kit_scene,
    list_kit, kit_index,
)
from .adapters.pes6pc import (
    export_pc, export_pc_complete, export_pc_parts, list_pc, pc_index,
)


def import_auto(template_bin_path: str, obj_path: str, output_bin_path: str,
                **kwargs) -> None:
    """Detecta face vs trofeu pelo magic e roteia para o import correto."""
    payload, _, _ = decompress_bin(template_bin_path)
    if detect_asset_type(payload) == "trophy":
        import_trophy(template_bin_path, obj_path, output_bin_path, **kwargs)
    else:
        kwargs.pop("section", None)
        import_face(template_bin_path, obj_path, output_bin_path, **kwargs)


def export_auto(bin_path: str, obj_path: str, section: int = 0,
                write_mtl: bool = True) -> None:
    """Detecta face vs trofeu e exporta para .obj (+ .mtl)."""
    payload, _, _ = decompress_bin(bin_path)
    if detect_asset_type(payload) == "trophy":
        export_trophy(bin_path, obj_path, section=section, write_mtl=write_mtl)
    else:
        export_face(bin_path, obj_path, write_mtl=write_mtl)


def import_new_face(template_bin_path: str, obj_path: str, output_bin_path: str,
                    **kwargs) -> None:
    """[compat v1] Equivalente a import_face."""
    kwargs.pop("section", None)
    import_face(template_bin_path, obj_path, output_bin_path, **kwargs)


__all__ = [
    "import_face", "export_face",
    "import_trophy", "export_trophy", "trophy_section_offsets",
    "export_stadium", "export_stadium_complete", "export_stadium_parts",
    "export_stadium_scene", "list_stadium", "stadium_index",
    "export_kit", "export_kit_complete", "export_kit_parts", "export_kit_scene",
    "list_kit", "kit_index",
    "export_pc", "export_pc_complete", "export_pc_parts", "list_pc", "pc_index",
    "import_auto", "export_auto", "import_new_face",
    "Model", "Part", "parse_model", "write_model",
    "detect_asset_type", "locate_model",
    "compress_bin", "decompress_bin", "ObjMesh", "parse_obj",
    "convert_obj_to_vertex_uv",
]
