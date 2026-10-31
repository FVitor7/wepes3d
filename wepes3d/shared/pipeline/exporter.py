"""
EXPORT engine .bin -> .obj for FACES and TROPHIES (driven by an AssetProfile).

Stadiums and kits use `folder.py` (model folder). The geometry of each part
is read by the universal reader `model.reader`.
"""

from .assets import AssetProfile
from ..io.bin_io import decompress_bin
from ..io.obj_write import write_obj
from ..model.reader import read_model_geometry


def _export(profile: AssetProfile, bin_path: str, obj_path: str,
            section: int = 0, write_mtl: bool = True) -> None:
    """
    Exports one sub-model (.mdl) of a .bin to .obj (+ optional .mtl).

    Each part is read by the UNIVERSAL reader
    `model.reader.read_part_geometry` (it finds the format from the bytes
    themselves). Vertices/UVs are converted to OBJ space with `profile.coord`.
    """
    coord = profile.coord
    payload, _, _ = decompress_bin(bin_path)
    model_offset = profile.locate(payload, section)

    verts, uvs, faces, skipped, nparts = read_model_geometry(
        coord, payload, model_offset)

    write_obj(obj_path, verts, uvs, faces, write_mtl=write_mtl,
              comment=f"{profile.name} section {section} of {bin_path}")
    print(f"[export] {profile.name} sec{section}: {len(verts)} v, "
          f"{len(faces)} faces -> {obj_path}")
    if skipped:
        print(f"  [WARNING] {skipped}/{nparts} part(s) skipped: geometry "
              f"structure not recognized by the universal reader.")
