"""
Motor de EXPORT .bin -> .obj para FACE e TROFEU (parametrizado por AssetProfile).

Estadio e kit usam `folder.py` (pasta de modelos). A leitura de geometria de
cada part vem do leitor universal `model.reader`.
"""

from .assets import AssetProfile
from ..io.bin_io import decompress_bin
from ..io.obj_write import write_obj
from ..model.reader import read_model_geometry


def _export(profile: AssetProfile, bin_path: str, obj_path: str,
            section: int = 0, write_mtl: bool = True) -> None:
    """
    Exporta um sub-modelo (.mdl) de um .bin para .obj (+ .mtl opcional).

    Cada part e' lida pelo leitor UNIVERSAL `model.reader.read_part_geometry`
    (detecta o formato pelos proprios bytes). Converte vertices/UVs para o espaco
    OBJ via `profile.coord`.
    """
    coord = profile.coord
    payload, _, _ = decompress_bin(bin_path)
    model_offset = profile.locate(payload, section)

    verts, uvs, faces, skipped, nparts = read_model_geometry(
        coord, payload, model_offset)

    write_obj(obj_path, verts, uvs, faces, write_mtl=write_mtl,
              comment=f"{profile.name} section {section} de {bin_path}")
    print(f"[export] {profile.name} sec{section}: {len(verts)} v, "
          f"{len(faces)} faces -> {obj_path}")
    if skipped:
        print(f"  [AVISO] {skipped}/{nparts} part(s) puladas: estrutura "
              f"de geometria nao reconhecida pelo leitor universal.")
