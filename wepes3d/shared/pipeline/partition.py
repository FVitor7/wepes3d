"""
Splitting the mesh into PS2 parts.

The .bin has N parts (in the face.bin template = 8 parts × 87 vertices = 696
vertices in total). Each part is an "island" — every triangle of a part has
its 3 vertices INSIDE the part (triangles do not cross part borders).

When the imported .obj has more or fewer vertices than the template, they
must be DISTRIBUTED again. Three strategies are supported:

  1. BFS by adjacency          — `partition_mesh_by_faces`
     Grows parts from a seed face, expanding through the neighbours.
     A good default when the user gives no extra information.

  2. By OBJ groups             — `partition_by_obj_groups`
     Each 'g'/'o' group of the .obj becomes a part. Manual control in
     Blender: split the face into N objects before exporting.

  3. Nearest neighbour of the template — `partition_by_template`
     Each .obj vertex goes to the part of the closest template vertex. Keeps
     the anatomical layout that PES expects.

In all cases, vertices on "seams" (borders between parts) are DUPLICATED,
with the same UV and position — only the index is duplicated.
"""

from collections import defaultdict, deque, Counter
from typing import Callable, List, Optional, Tuple


# ============================================================================
# (start, end) ranges per part
# ============================================================================

def compute_new_ranges_from_sizes(sizes: List[int]) -> List[Tuple[int, int]]:
    """Converts a list of sizes into ranges [(start, end_exclusive)]."""
    ranges = []
    cumulative = 0
    for s in sizes:
        ranges.append((cumulative, cumulative + s))
        cumulative += s
    return ranges


# ============================================================================
# Assigning triangles to parts (after the ranges are set)
# ============================================================================

def assign_triangles_to_parts(
    faces: List[Tuple[int, int, int]],
    part_ranges: List[Tuple[int, int]],
) -> List[List[Tuple[int, int, int]]]:
    """
    Assigns each triangle to its part: ALL 3 vertices must be inside the same
    range. Triangles that cross a border raise a ValueError with a clear
    message.

    Returns LOCAL triangles (indices relative to the start of the part).
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
                f"Triangle {tri_idx}: vertex(es) outside the ranges "
                f"(v{a}->p{pa}, v{b}->p{pb}, v{c}->p{pc})"
            )
        if pa != pb or pa != pc:
            raise ValueError(
                f"Triangle {tri_idx} (v{a}, v{b}, v{c}) crosses a part border:\n"
                f"  v{a} -> part {pa}\n  v{b} -> part {pb}\n  v{c} -> part {pc}\n"
                f"Use --allow-recount to compute the borders again automatically."
            )
        start = part_ranges[pa][0]
        per_part[pa].append((a - start, b - start, c - start))

    return per_part


# ============================================================================
# Strategy 1: BFS by face adjacency
# ============================================================================

def partition_mesh_by_faces(
    vertices: List[Tuple[float, float, float]],
    uvs: List[Tuple[float, float]],
    faces: List[Tuple[int, int, int]],
    n_parts: int,
    max_verts: Optional[int] = None,
) -> Tuple[List, List, List[Tuple[int, int, int]], List[int]]:
    """
    Splits into n_parts with a BFS over face adjacency.

    1. Builds a graph: face -> neighbour faces (sharing 1+ vertex).
    2. For each part, runs a BFS from an unassigned face until it reaches the
       target (n_faces / n_parts). The last part takes all the faces left.
    3. Re-indexes: vertices used in several parts are DUPLICATED.

    max_verts: a HARD limit of vertices per part (the seam copies count too).
    A face that would go over it is skipped and stays for a later part. When
    the n_parts parts are full, MORE parts are created, so the result can have
    more than n_parts parts (see len(sizes_per_part)). A mesh that never
    reaches the limit gives exactly the same result as max_verts=None.

    Returns (new_vertices, new_uvs, new_faces_global, sizes_per_part).
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
    part_face_lists: List[List[int]] = []

    # Without max_verts the last planned part takes everything, so the loop
    # stops at n_parts. With it, extra parts are created while faces are left
    # (each new part takes at least its first face: 3 vertices <= max_verts).
    while len(part_face_lists) < n_parts or unassigned:
        part_idx = len(part_face_lists)
        part_faces: List[int] = []
        part_face_lists.append(part_faces)
        if not unassigned:
            continue
        local_target = target if part_idx < n_parts - 1 else len(unassigned)

        used: set = set()          # vertices already in this part
        # Seeds in increasing order (= min(unassigned) at each step)
        for seed in sorted(unassigned):
            if len(part_faces) >= local_target:
                break
            if seed not in unassigned:
                continue
            queue: deque = deque([seed])
            while queue and len(part_faces) < local_target:
                fi = queue.popleft()
                if fi not in unassigned:
                    continue
                new_verts = set(faces[fi]) - used
                if max_verts is not None and len(used) + len(new_verts) > max_verts:
                    continue       # does not fit: it stays for a later part
                part_faces.append(fi)
                unassigned.discard(fi)
                used |= new_verts
                for fj in face_adj[fi]:
                    if fj in unassigned:
                        queue.append(fj)

    return _reindex_partition(vertices, uvs, faces, part_face_lists,
                              len(part_face_lists))


# ============================================================================
# Strategy 2: by OBJ groups
# ============================================================================

def partition_by_obj_groups(
    vertices: List[Tuple[float, float, float]],
    uvs: List[Tuple[float, float]],
    faces: List[Tuple[int, int, int]],
    face_groups: List[int],
    n_groups: int,
) -> Tuple[List, List, List[Tuple[int, int, int]], List[int]]:
    """
    Each 'g'/'o' group of the .obj becomes a part. The number of groups must
    be the same as the number of parts you want. Gives fine manual control in
    Blender: split the mesh into N objects and export a multi-object OBJ.
    """
    part_face_lists: List[List[int]] = [[] for _ in range(n_groups)]
    for fi, gidx in enumerate(face_groups):
        if gidx < n_groups:
            part_face_lists[gidx].append(fi)
    return _reindex_partition(vertices, uvs, faces, part_face_lists, n_groups)


# ============================================================================
# Strategy 3: nearest neighbour of the template
# ============================================================================

def partition_by_template(
    vertices: List[Tuple[float, float, float]],
    uvs: List[Tuple[float, float]],
    faces: List[Tuple[int, int, int]],
    template,
    int16_to_obj: Callable,
) -> Tuple[List, List, List[Tuple[int, int, int]], List[int]]:
    """
    Each vertex of the new mesh gets the same part_idx as the closest template
    vertex (in OBJ space). Each triangle goes where the MAJORITY of the 3
    votes of its vertices points.

    Precondition: the vertices must be in the same space as the template —
    use it together with `auto_fit_vertices`, which centers/scales them.

    Advantage: keeps the anatomical layout that PES expects (P0 = front right
    side, P1 = front left side, etc.). Plain BFS can create unbalanced parts
    that do not match the anatomical regions.
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

    print(f"      Cross-part triangles (seams): {seams}/{len(faces)}")
    return _reindex_partition(vertices, uvs, faces, part_face_lists, n_parts)


# ============================================================================
# Internal helper: re-indexes the partition
# ============================================================================

def _reindex_partition(
    vertices: List[Tuple[float, float, float]],
    uvs: List[Tuple[float, float]],
    faces: List[Tuple[int, int, int]],
    part_face_lists: List[List[int]],
    n_parts: int,
) -> Tuple[List, List, List[Tuple[int, int, int]], List[int]]:
    """
    From a face -> part assignment, re-indexes all vertices.

    Vertices on seams (shared between parts) are DUPLICATED — each part gets
    its own copy, with the same position and UV. After that, the face indices
    are turned into GLOBAL indices (cumulative offset).
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
