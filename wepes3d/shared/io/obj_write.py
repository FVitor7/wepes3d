"""
Escrita de .obj (Wavefront) + .mtl — usado pelo motor de export.

Asset-agnostico: recebe vertices/UVs/faces ja no espaco OBJ. O .mtl referencia
uma textura `<base>.png` por convencao; a imagem em si nao eh extraida aqui (vem
da secao de textura do .bin via ferramenta externa).
"""

import os
from typing import List, Optional, Tuple


def write_obj(path: str,
              verts: List[Tuple[float, float, float]],
              uvs: List[Tuple[float, float]],
              faces: List[Tuple[int, int, int]],
              write_mtl: bool = True,
              comment: str = "",
              groups: Optional[List[Tuple[str, int, int]]] = None) -> None:
    """Escreve um .obj. Se `groups` (lista de (nome, face_inicio, qtd_faces)) for
    dado, emite um `o <nome>` antes do bloco de faces de cada grupo — o Blender
    importa como objetos separados (1 por part)."""
    base = os.path.splitext(os.path.basename(path))[0]
    mtl_name = base + ".mtl"

    if write_mtl:
        mtl_path = os.path.join(os.path.dirname(path), mtl_name)
        with open(mtl_path, "w") as mtl:
            mtl.write("# gerado por wepes3d\n\n")
            mtl.write("newmtl material1\n")
            mtl.write(f"\tmap_Kd {base}.png\n")

    with open(path, "w") as obj:
        if comment:
            obj.write(f"# {comment}\n")
        obj.write(f"# wepes3d export — v={len(verts)} "
                  f"vt={len(uvs)} f={len(faces)}\n\n")
        if write_mtl:
            obj.write(f"mtllib {mtl_name}\n")
            obj.write("usemtl material1\n\n")
        for (x, y, z) in verts:
            obj.write(f"v {x:.6f} {y:.6f} {z:.6f}\n")
        obj.write("\n")
        for (u, v) in uvs:
            obj.write(f"vt {u:.6f} {v:.6f}\n")
        obj.write("\n")

        def _face(a, b, c):
            return f"f {a+1}/{a+1} {b+1}/{b+1} {c+1}/{c+1}\n"

        if groups:
            for name, fstart, fcount in groups:
                obj.write(f"o {name}\n")
                for (a, b, c) in faces[fstart:fstart + fcount]:
                    obj.write(_face(a, b, c))
        else:
            for (a, b, c) in faces:
                obj.write(_face(a, b, c))
