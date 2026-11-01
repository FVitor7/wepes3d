"""
wepes3d: .obj <-> .bin importer/exporter for PES.

Main goal: import NEW 3D models (trophies, faces, hair...) into PES PS2, to
make the game more real. The export exists to open the original models in
Blender and use them as a starting point.

Two platforms, kept apart in adapters/ (PC and PS2 are DIFFERENT formats):
  * PS2 (adapters/pesweps2): FACES/HAIR, TROPHIES, STADIUMS, KITS.
        Import + export. int16, 0300ffff model, VIF unpacks.
  * PC  (adapters/pes6pc):   FACES and TROPHIES. Export ONLY (.bin/.str -> .obj).
        float32, 20050420 model, strips per vertex group.

Layout (see docs/10-architecture.md):
  shared/   the core (PS2 engine + common I/O), in sub-packages by job:
            io/ (bin/archive/obj), geometry/ (coords/transform),
            model/ (parser/reader/strip/rebuilder), pipeline/ (assets/importer/
            exporter/folder/partition) + constants.py. PC only reuses io/.
  adapters/pesweps2/  thin PS2 adapters (profile = coord + navigation;
            __init__ = import_/export_ wrappers). FACE/TROPHY use the
            importer/exporter engine; STADIUM/KIT (export only) use
            pipeline.folder.
  adapters/pes6pc/    its own PC reader (reader/coords) + an export API in the
            "model folder" style (list/export/complete/parts).

API:

    from wepes3d import (
        import_face, export_face, import_trophy, export_trophy,
        import_auto, export_auto,
        export_stadium, export_stadium_complete, list_stadium,
        export_kit, export_kit_complete, list_kit,
    )

    import_face("face.bin", "new_face.obj", "out.bin",
                recalculate_normals=True, allow_recount=True, auto_fit=True)
    import_trophy("trophy.bin", "cup.obj", "out.bin", section=0, allow_recount=True)
    import_auto("any.bin", "new.obj", "out.bin", allow_recount=True)
    export_auto("any.bin", "out.obj")                         # face/trophy (detects the type)
    export_stadium_complete("stad1_main.bin", "stadium.obj")  # whole stadium
    export_kit_complete("kit_1135", "shirt.obj")              # kit
    convert_obj_to_vertex_uv("blender.obj", "ready.obj")      # 1 UV per vertex

CLI: `python -m wepes3d export|import|list ...` (see cli.py).
Docs in docs/ (08-trophies, 09-stadiums-and-kits, 10-architecture).
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
    """Detects face vs trophy from the magic and calls the right import."""
    payload, _, _ = decompress_bin(template_bin_path)
    if detect_asset_type(payload) == "trophy":
        import_trophy(template_bin_path, obj_path, output_bin_path, **kwargs)
    else:
        kwargs.pop("section", None)
        import_face(template_bin_path, obj_path, output_bin_path, **kwargs)


def export_auto(bin_path: str, obj_path: str, section: int = 0,
                write_mtl: bool = True) -> None:
    """Detects face vs trophy and exports to .obj (+ .mtl)."""
    payload, _, _ = decompress_bin(bin_path)
    if detect_asset_type(payload) == "trophy":
        export_trophy(bin_path, obj_path, section=section, write_mtl=write_mtl)
    else:
        export_face(bin_path, obj_path, write_mtl=write_mtl)


def import_new_face(template_bin_path: str, obj_path: str, output_bin_path: str,
                    **kwargs) -> None:
    """[v1 compatibility] Same as import_face."""
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
