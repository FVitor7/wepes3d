"""
Leitura de arquivos .obj (Wavefront OBJ).

Formato minimo suportado:
  v  X Y Z      (vertice float)
  vt U V        (UV float)
  vn NX NY NZ   (normal float — IGNORADAS pelo script, recalculadas)
  g NOME        (inicio de grupo)
  o NOME        (inicio de objeto)
  f a/b/c d/e/f g/h/i   (triangulo com 3 indices 1-based)
  f a d g       (triangulo com so indices de vertice)

PRE-CONDICOES IMPORTANTES:
  - 1 UV por vertice (sem UV seams / split). Se o arquivo tem mais UVs que
    vertices, o pipeline detecta e aborta com mensagem clara explicando como
    resolver no Blender ("Merge UVs by Distance").

TRIANGULACAO AUTOMATICA:
  - Faces com >3 vertices sao automaticamente trianguladas via FAN
    triangulation: poligono [v0, v1, ..., vN-1] vira triangulos
    (v0, v1, v2), (v0, v2, v3), ..., (v0, vN-2, vN-1).
  - Funciona perfeitamente para poligonos CONVEXOS (caso comum de exports
    do Blender). Para poligonos concavos, fan pode gerar triangulos
    sobrepostos — triangule no Blender (Mesh > Triangulate Faces) primeiro.
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ObjMesh:
    """Conteudo essencial de um .obj para o pipeline de importacao."""
    vertices: List[Tuple[float, float, float]]
    uvs: List[Tuple[float, float]]
    faces: List[Tuple[int, int, int]]
    """Triangulos: tuplas de 3 indices 0-based no array `vertices`."""

    face_groups: List[int]
    """Indice do grupo a que cada face pertence (paralelo a `faces`)."""

    group_names: List[str]
    """Nomes dos grupos por indice. group_names[i] = nome do grupo `i`."""


def parse_obj(filepath: str) -> ObjMesh:
    """
    Parser minimalista de .obj.

    Grupos: linhas 'g NOME' ou 'o NOME' iniciam um novo grupo. Cada `f`
    subsequente eh associado a esse grupo. Util para `--use-groups` que
    mapeia 1 grupo do .obj -> 1 part do PS2.
    """
    vertices: List[Tuple[float, float, float]] = []
    uvs: List[Tuple[float, float]] = []
    faces: List[Tuple[int, int, int]] = []
    face_groups: List[int] = []

    group_map = {"default": 0}
    current_group = 0

    triangulated_count = 0   # quantas faces precisaram de fan triangulation
    extra_tris_from_fan = 0  # quantos triangulos extras geramos

    with open(filepath, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            tokens = line.split()
            tag = tokens[0]

            if tag == 'v':
                vertices.append((float(tokens[1]), float(tokens[2]), float(tokens[3])))
            elif tag == 'vt':
                uvs.append((float(tokens[1]), float(tokens[2])))
            elif tag in ('g', 'o'):
                name = ' '.join(tokens[1:]) if len(tokens) > 1 else "default"
                if name not in group_map:
                    group_map[name] = len(group_map)
                current_group = group_map[name]
            elif tag == 'f':
                # Coleta TODOS os vertices da face (nao trunca em 3).
                poly: List[int] = []
                for token in tokens[1:]:
                    v_idx = int(token.split('/')[0]) - 1
                    poly.append(v_idx)

                if len(poly) < 3:
                    continue   # face degenerada — ignora

                # Fan triangulation: gera (poly[0], poly[i], poly[i+1])
                # Para tri (len=3) eh um pass-through.
                # Para quad (len=4) gera 2 tris.
                # Para n-gono gera (n - 2) tris.
                if len(poly) > 3:
                    triangulated_count += 1
                    extra_tris_from_fan += (len(poly) - 3)

                for i in range(1, len(poly) - 1):
                    faces.append((poly[0], poly[i], poly[i + 1]))
                    face_groups.append(current_group)

    if triangulated_count > 0:
        print(f"      [INFO] {triangulated_count} face(s) com >3 vertices trianguladas "
              f"(fan triangulation) — +{extra_tris_from_fan} triangulos.")

    group_names = [''] * len(group_map)
    for name, idx in group_map.items():
        group_names[idx] = name

    return ObjMesh(vertices=vertices, uvs=uvs, faces=faces,
                   face_groups=face_groups, group_names=group_names)
