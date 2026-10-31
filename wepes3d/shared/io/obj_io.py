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

1 UV POR VERTICE (o pipeline exige):
  - Quando as faces usam indices de v e vt diferentes (export do Blender, UV
    seams), cada par (v, vt) unico vira um vertice — duplicado nos seams.
    Arquivos ja alinhados (v == vt, como os do export) passam intactos.
  - Se as faces nao referenciam vt e o numero de UVs difere do de vertices,
    o pipeline aborta com mensagem clara (reexportar o .obj com UVs).

TRIANGULACAO AUTOMATICA:
  - Faces com >3 vertices sao automaticamente trianguladas via FAN
    triangulation: poligono [v0, v1, ..., vN-1] vira triangulos
    (v0, v1, v2), (v0, v2, v3), ..., (v0, vN-2, vN-1).
  - Funciona perfeitamente para poligonos CONVEXOS (caso comum de exports
    do Blender). Para poligonos concavos, fan pode gerar triangulos
    sobrepostos — triangule no Blender (Mesh > Triangulate Faces) primeiro.

CONVERSAO 1 UV POR VERTICE (`convert_obj_to_vertex_uv`):
  - Grava em disco o mesmo alinhamento que o `parse_obj` faz na leitura, no
    formato `f i/i` — util para conferir no Blender o que o import enxerga.
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

    UVs: segue o indice `vt` de cada canto da face (ver `_unify_vertex_uv`) —
    antes o UV era tomado pela posicao do vertice, o que embaralhava as UVs
    de .obj exportados do Blender.
    """
    vertices, uvs, polygons, poly_groups, group_names = _read_obj(filepath)
    vertices, uvs, polygons = _unify_vertex_uv(vertices, uvs, polygons)

    faces: List[Tuple[int, int, int]] = []
    face_groups: List[int] = []

    triangulated_count = 0   # quantas faces precisaram de fan triangulation
    extra_tris_from_fan = 0  # quantos triangulos extras geramos

    for poly, group in zip(polygons, poly_groups):
        # Fan triangulation: gera (poly[0], poly[i], poly[i+1])
        # Para tri (len=3) eh um pass-through.
        # Para quad (len=4) gera 2 tris.
        # Para n-gono gera (n - 2) tris.
        if len(poly) > 3:
            triangulated_count += 1
            extra_tris_from_fan += (len(poly) - 3)

        for i in range(1, len(poly) - 1):
            faces.append((poly[0], poly[i], poly[i + 1]))
            face_groups.append(group)

    if triangulated_count > 0:
        print(f"      [INFO] {triangulated_count} face(s) com >3 vertices trianguladas "
              f"(fan triangulation) — +{extra_tris_from_fan} triangulos.")

    return ObjMesh(vertices=vertices, uvs=uvs, faces=faces,
                   face_groups=face_groups, group_names=group_names)


def convert_obj_to_vertex_uv(input_path: str, output_path: str) -> None:
    """
    Reescreve um .obj com 1 UV por vertice: cada par (v, vt) unico vira um
    vertice e as faces passam a usar o MESMO indice para v e vt (`f i/i`).

    O import ja faz esse alinhamento na leitura (`parse_obj`); esta funcao o
    grava em disco — util para conferir no Blender o que o import enxerga ou
    para ferramentas que exigem v e vt alinhados. Preserva grupos (`o`/`g`) e
    poligonos (nao triangula); descarta normais e materiais. Um .obj ja
    alinhado sai com os vertices na mesma ordem.
    """
    vertices, uvs, polygons, poly_groups, group_names = _read_obj(input_path)
    if not uvs:
        raise ValueError(f"{input_path}: o .obj nao tem UVs (linhas 'vt').")
    vertices, uvs, polygons = _unify_vertex_uv(vertices, uvs, polygons)

    with open(output_path, 'w') as f:
        for (x, y, z) in vertices:
            f.write(f"v {x} {y} {z}\n")
        for (u, v) in uvs:
            f.write(f"vt {u} {v}\n")
        current_group = 0
        for poly, group in zip(polygons, poly_groups):
            if group != current_group:
                f.write(f"o {group_names[group]}\n")
                current_group = group
            f.write("f " + " ".join(f"{i + 1}/{i + 1}" for i in poly) + "\n")

    print(f"{output_path}: {len(vertices)} vertices, {len(uvs)} UVs, "
          f"{len(polygons)} faces (1 UV por vertice).")


def _read_obj(filepath: str):
    """
    Le v/vt/g/o/f. Devolve (vertices, uvs, polygons, poly_groups, group_names);
    cada polygon eh a lista de pares (v, vt) 0-based dos seus cantos — vt = v
    quando a face nao referencia UV (`f 1 2 3` ou `f 1//1 ...`). Faces com
    menos de 3 vertices (degeneradas) sao ignoradas.
    """
    vertices: List[Tuple[float, float, float]] = []
    uvs: List[Tuple[float, float]] = []
    polygons: List[List[Tuple[int, int]]] = []
    poly_groups: List[int] = []

    group_map = {"default": 0}
    current_group = 0

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
                # Coleta TODOS os cantos da face (nao trunca em 3).
                poly: List[Tuple[int, int]] = []
                for token in tokens[1:]:
                    fields = token.split('/')
                    v_idx = int(fields[0]) - 1
                    vt_idx = int(fields[1]) - 1 if len(fields) > 1 and fields[1] else v_idx
                    poly.append((v_idx, vt_idx))
                if len(poly) >= 3:
                    polygons.append(poly)
                    poly_groups.append(current_group)

    group_names = [''] * len(group_map)
    for name, idx in group_map.items():
        group_names[idx] = name

    return vertices, uvs, polygons, poly_groups, group_names


def _unify_vertex_uv(vertices, uvs, polygons):
    """
    Garante 1 UV por vertice: cada par (v, vt) unico referenciado pelas faces
    vira um vertice proprio — o vertice eh duplicado nos seams de UV.

    Se todos os cantos ja usam vt == v (ex.: .obj gerado pelo export), devolve
    vertices/UVs intactos e na mesma ordem. Senao, os vertices novos seguem a
    ordem da 1a aparicao nas faces (vertices que nenhuma face usa somem).
    Devolve (vertices, uvs, polygons) com cada polygon como lista de indices.
    """
    if all(v == vt for poly in polygons for v, vt in poly):
        return vertices, uvs, [[v for v, _ in poly] for poly in polygons]

    new_vertices: List[Tuple[float, float, float]] = []
    new_uvs: List[Tuple[float, float]] = []
    new_polygons: List[List[int]] = []
    index_of = {}
    for poly in polygons:
        new_poly = []
        for key in poly:
            if key not in index_of:
                index_of[key] = len(new_vertices)
                new_vertices.append(vertices[key[0]])
                new_uvs.append(uvs[key[1]])
            new_poly.append(index_of[key])
        new_polygons.append(new_poly)

    print(f"      [INFO] indices v/vt diferentes nas faces: {len(vertices)} vertices "
          f"-> {len(new_vertices)} (1 por par v/vt; duplicados nos seams de UV).")
    return new_vertices, new_uvs, new_polygons
