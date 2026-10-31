"""
Particionamento do mesh em parts do PS2.

O .bin tem N parts (no template face.bin = 8 parts × 87 vertices = 696 vertices
total). Cada part eh uma "ilha" — todos os triangulos de uma part tem seus 3
vertices DENTRO da part (nao cruzam fronteiras).

Quando o .obj importado tem mais ou menos vertices que o template, eh
necessario REDISTRIBUIR. Tres estrategias suportadas:

  1. BFS por adjacencia      — `partition_mesh_by_faces`
     Cresce parts a partir de uma face semente, expandindo pelos vizinhos.
     Bom default sem informacao adicional do usuario.

  2. Por grupos OBJ          — `partition_by_obj_groups`
     Cada grupo 'g'/'o' do .obj vira uma part. Controle manual no Blender:
     separe o rosto em N objetos antes de exportar.

  3. Nearest-neighbor do template — `partition_by_template`
     Cada vertice do .obj eh atribuido a part do vertice template mais
     proximo. Preserva a topologia anatomica esperada pelo PES.

Em todos os casos, vertices em "seams" (fronteiras entre parts) sao
DUPLICADOS, com UV e posicao identicas — apenas o indice eh duplicado.
"""

from collections import defaultdict, deque, Counter
from typing import Callable, List, Tuple


# ============================================================================
# Calculo de ranges (start, end) por part
# ============================================================================

def compute_new_ranges_from_sizes(sizes: List[int]) -> List[Tuple[int, int]]:
    """Converte uma lista de tamanhos em ranges [(start, end_exclusive)]."""
    ranges = []
    cumulative = 0
    for s in sizes:
        ranges.append((cumulative, cumulative + s))
        cumulative += s
    return ranges


# ============================================================================
# Atribuicao de triangulos as parts (apos definir ranges)
# ============================================================================

def assign_triangles_to_parts(
    faces: List[Tuple[int, int, int]],
    part_ranges: List[Tuple[int, int]],
) -> List[List[Tuple[int, int, int]]]:
    """
    Atribui cada triangulo a sua part: requer que TODOS os 3 vertices
    estejam dentro do mesmo range. Triangulos que cruzam fronteiras
    geram ValueError com mensagem clara.

    Retorna triangulos LOCAIS (indices relativos ao inicio da part).
    """
    per_part = [[] for _ in part_ranges]

    def find_part(v: int):
        for i, (s, e) in enumerate(part_ranges):
            if s <= v < e:
                return i
        return None

    for tri_idx, (a, b, c) in enumerate(faces):
        pa, pb, pc = find_part(a), find_part(b), find_part(c)
        if pa is None or pb is None or pc is None:
            raise ValueError(
                f"Triangulo {tri_idx}: vertice(s) fora dos ranges "
                f"(v{a}->p{pa}, v{b}->p{pb}, v{c}->p{pc})"
            )
        if pa != pb or pa != pc:
            raise ValueError(
                f"Triangulo {tri_idx} (v{a}, v{b}, v{c}) cruza fronteira de parts:\n"
                f"  v{a} -> part {pa}\n  v{b} -> part {pb}\n  v{c} -> part {pc}\n"
                f"Use --allow-recount para recalcular fronteiras automaticamente."
            )
        start = part_ranges[pa][0]
        per_part[pa].append((a - start, b - start, c - start))

    return per_part


# ============================================================================
# Estrategia 1: BFS por adjacencia de faces
# ============================================================================

def partition_mesh_by_faces(
    vertices: List[Tuple[float, float, float]],
    uvs: List[Tuple[float, float]],
    faces: List[Tuple[int, int, int]],
    n_parts: int,
) -> Tuple[List, List, List[Tuple[int, int, int]], List[int]]:
    """
    Particiona em n_parts usando BFS por adjacencia de faces.

    1. Constroi grafo: face -> faces vizinhas (compartilham 1+ vertice).
    2. Para cada part, BFS a partir de uma face nao-atribuida ate atingir
       o target (n_faces / n_parts).
    3. Re-indexa: vertices usados em multiplas parts sao DUPLICADOS.

    Retorna (new_vertices, new_uvs, new_faces_global, sizes_per_part).
    """
    n_faces = len(faces)
    target = max(1, n_faces // n_parts)

    vert_to_faces: dict = defaultdict(list)
    for fi, (a, b, c) in enumerate(faces):
        vert_to_faces[a].append(fi)
        vert_to_faces[b].append(fi)
        vert_to_faces[c].append(fi)

    face_adj: List[set] = [set() for _ in range(n_faces)]
    for flist in vert_to_faces.values():
        for fi in flist:
            for fj in flist:
                if fi != fj:
                    face_adj[fi].add(fj)

    unassigned = set(range(n_faces))
    part_face_lists: List[List[int]] = [[] for _ in range(n_parts)]

    for part_idx in range(n_parts):
        if not unassigned:
            break
        is_last = (part_idx == n_parts - 1)
        local_target = len(unassigned) if is_last else target

        count = 0
        while count < local_target and unassigned:
            seed = min(unassigned)
            queue: deque = deque([seed])
            while queue and count < local_target:
                fi = queue.popleft()
                if fi not in unassigned:
                    continue
                part_face_lists[part_idx].append(fi)
                unassigned.discard(fi)
                count += 1
                for fj in face_adj[fi]:
                    if fj in unassigned:
                        queue.append(fj)

    return _reindex_partition(vertices, uvs, faces, part_face_lists, n_parts)


# ============================================================================
# Estrategia 2: por grupos OBJ
# ============================================================================

def partition_by_obj_groups(
    vertices: List[Tuple[float, float, float]],
    uvs: List[Tuple[float, float]],
    faces: List[Tuple[int, int, int]],
    face_groups: List[int],
    n_groups: int,
) -> Tuple[List, List, List[Tuple[int, int, int]], List[int]]:
    """
    Cada grupo 'g'/'o' do .obj vira uma part. O numero de grupos deve ser
    igual ao numero de parts desejadas. Permite controle manual fino no
    Blender: separe a malha em N objetos, exporte como OBJ multi-object.
    """
    part_face_lists: List[List[int]] = [[] for _ in range(n_groups)]
    for fi, gidx in enumerate(face_groups):
        if gidx < n_groups:
            part_face_lists[gidx].append(fi)
    return _reindex_partition(vertices, uvs, faces, part_face_lists, n_groups)


# ============================================================================
# Estrategia 3: nearest-neighbor do template
# ============================================================================

def partition_by_template(
    vertices: List[Tuple[float, float, float]],
    uvs: List[Tuple[float, float]],
    faces: List[Tuple[int, int, int]],
    template,
    int16_to_obj: Callable,
) -> Tuple[List, List, List[Tuple[int, int, int]], List[int]]:
    """
    Cada vertice do mesh novo eh atribuido ao mesmo part_idx do vertice
    template mais proximo (no espaco OBJ). Triangulos sao atribuidos pela
    MAIORIA dos 3 votos dos seus vertices.

    Pre-condicao: vertices devem estar no mesmo espaco do template — use
    junto com `auto_fit_vertices` que centra/escala.

    Vantagem: preserva a topologia anatomica esperada pelo PES (P0 = lado
    direito frontal, P1 = lado esquerdo frontal, etc.). BFS puro pode
    criar parts desbalanceadas que nao casam com a regiao anatomica.
    """
    template_verts: List[Tuple[float, float, float]] = []
    template_part_of: List[int] = []
    for part_idx, part in enumerate(template.parts):
        for (s0, s1, s2) in part.vertices:
            x, y, z = int16_to_obj(s0, s1, s2)
            template_verts.append((x, y, z))
            template_part_of.append(part_idx)

    n_parts = len(template.parts)

    def nearest_part(vx, vy, vz):
        best_d2 = float('inf')
        best_p = 0
        for k, (tx, ty, tz) in enumerate(template_verts):
            d2 = (vx - tx) ** 2 + (vy - ty) ** 2 + (vz - tz) ** 2
            if d2 < best_d2:
                best_d2 = d2
                best_p = template_part_of[k]
        return best_p

    new_v_part = [nearest_part(x, y, z) for (x, y, z) in vertices]

    part_face_lists: List[List[int]] = [[] for _ in range(n_parts)]
    seams = 0
    for fi, (a, b, c) in enumerate(faces):
        votes = (new_v_part[a], new_v_part[b], new_v_part[c])
        winner, cnt = Counter(votes).most_common(1)[0]
        if cnt < 3:
            seams += 1
        part_face_lists[winner].append(fi)

    print(f"      Triangulos cross-part (seams): {seams}/{len(faces)}")
    return _reindex_partition(vertices, uvs, faces, part_face_lists, n_parts)


# ============================================================================
# Helper interno: re-indexa o particionamento
# ============================================================================

def _reindex_partition(
    vertices: List[Tuple[float, float, float]],
    uvs: List[Tuple[float, float]],
    faces: List[Tuple[int, int, int]],
    part_face_lists: List[List[int]],
    n_parts: int,
) -> Tuple[List, List, List[Tuple[int, int, int]], List[int]]:
    """
    A partir de uma atribuicao face -> part, re-indexa todos os vertices.

    Vertices em seams (compartilhados entre parts) sao DUPLICADOS — cada
    part recebe sua propria copia, com a mesma posicao e UV. Apos isso,
    os indices das faces sao convertidos para GLOBAL (offset cumulativo).
    """
    new_verts: List = []
    new_uvs_out: List = []
    part_local_faces: List[List[Tuple[int, int, int]]] = []
    part_sizes: List[int] = []

    for part_idx in range(n_parts):
        part_start = len(new_verts)
        old_to_local: dict = {}
        local_faces: List[Tuple[int, int, int]] = []

        for fi in part_face_lists[part_idx]:
            a, b, c = faces[fi]
            tri_local: List[int] = []
            for old_v in (a, b, c):
                if old_v not in old_to_local:
                    old_to_local[old_v] = len(new_verts) - part_start
                    new_verts.append(vertices[old_v])
                    new_uvs_out.append(uvs[old_v])
                tri_local.append(old_to_local[old_v])
            local_faces.append((tri_local[0], tri_local[1], tri_local[2]))

        part_sizes.append(len(new_verts) - part_start)
        part_local_faces.append(local_faces)

    global_faces: List[Tuple[int, int, int]] = []
    v_offset = 0
    for part_idx in range(n_parts):
        for (a, b, c) in part_local_faces[part_idx]:
            global_faces.append((a + v_offset, b + v_offset, c + v_offset))
        v_offset += part_sizes[part_idx]

    return new_verts, new_uvs_out, global_faces, part_sizes
