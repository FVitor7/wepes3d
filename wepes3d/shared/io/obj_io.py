"""
Reading of .obj files (Wavefront OBJ).

Minimal supported format:
  v  X Y Z      (float vertex)
  vt U V        (float UV)
  vn NX NY NZ   (float normal — IGNORED, normals are computed again)
  g NAME        (start of a group)
  o NAME        (start of an object)
  f a/b/c d/e/f g/h/i   (triangle with 3 1-based indices)
  f a d g       (triangle with vertex indices only)

1 UV PER VERTEX (the pipeline needs this):
  - When the faces use different v and vt indices (Blender export, UV
    seams), each unique (v, vt) pair becomes its own vertex — duplicated at
    the seams. Files that are already aligned (v == vt, like the ones our
    export writes) are kept as they are.
  - If the faces do not reference vt and the number of UVs is different from
    the number of vertices, the pipeline stops with a clear message
    (export the .obj again with UVs).

AUTOMATIC TRIANGULATION:
  - Faces with >3 vertices are triangulated automatically with FAN
    triangulation: the polygon [v0, v1, ..., vN-1] becomes the triangles
    (v0, v1, v2), (v0, v2, v3), ..., (v0, vN-2, vN-1).
  - Works well for CONVEX polygons (the usual case in Blender exports). For
    concave polygons the fan can create overlapping triangles — triangulate
    in Blender first (Mesh > Triangulate Faces).

1 UV PER VERTEX CONVERSION (`convert_obj_to_vertex_uv`):
  - Writes to disk the same alignment that `parse_obj` does while reading, in
    the `f i/i` format — useful to check in Blender what the import sees.
"""

from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class ObjMesh:
    """The essential content of an .obj file for the import pipeline."""
    vertices: List[Tuple[float, float, float]]
    uvs: List[Tuple[float, float]]
    faces: List[Tuple[int, int, int]]
    """Triangles: tuples of 3 0-based indices into the `vertices` array."""

    face_groups: List[int]
    """Index of the group of each face (parallel to `faces`)."""

    group_names: List[str]
    """Group names by index. group_names[i] = name of group `i`."""


def parse_obj(filepath: str) -> ObjMesh:
    """
    Minimal .obj parser.

    Groups: 'g NAME' or 'o NAME' lines start a new group. Each following `f`
    belongs to that group. Useful for `--use-groups`, which maps 1 group of
    the .obj -> 1 PS2 part.

    UVs: follows the `vt` index of each face corner (see `_unify_vertex_uv`)
    — before, the UV was taken from the vertex position, which mixed up the
    UVs of .obj files exported from Blender.
    """
    vertices, uvs, polygons, poly_groups, group_names = _read_obj(filepath)
    vertices, uvs, polygons = _unify_vertex_uv(vertices, uvs, polygons)

    faces: List[Tuple[int, int, int]] = []
    face_groups: List[int] = []

    triangulated_count = 0   # how many faces needed fan triangulation
    extra_tris_from_fan = 0  # how many extra triangles we created

    for poly, group in zip(polygons, poly_groups):
        # Fan triangulation: creates (poly[0], poly[i], poly[i+1])
        # For a tri (len=3) nothing changes.
        # For a quad (len=4) it creates 2 tris.
        # For an n-gon it creates (n - 2) tris.
        if len(poly) > 3:
            triangulated_count += 1
            extra_tris_from_fan += (len(poly) - 3)

        for i in range(1, len(poly) - 1):
            faces.append((poly[0], poly[i], poly[i + 1]))
            face_groups.append(group)

    if triangulated_count > 0:
        print(f"      [INFO] {triangulated_count} face(s) with >3 vertices triangulated "
              f"(fan triangulation) — +{extra_tris_from_fan} triangles.")

    return ObjMesh(vertices=vertices, uvs=uvs, faces=faces,
                   face_groups=face_groups, group_names=group_names)


def convert_obj_to_vertex_uv(input_path: str, output_path: str) -> None:
    """
    Rewrites an .obj with 1 UV per vertex: each unique (v, vt) pair becomes a
    vertex, and the faces use the SAME index for v and vt (`f i/i`).

    The import already does this alignment while reading (`parse_obj`); this
    function writes it to disk — useful to check in Blender what the import
    sees, or for tools that need v and vt to be aligned. It keeps groups
    (`o`/`g`) and polygons (it does not triangulate); it drops normals and
    materials. An .obj that is already aligned keeps the same vertex order.
    """
    vertices, uvs, polygons, poly_groups, group_names = _read_obj(input_path)
    if not uvs:
        raise ValueError(f"{input_path}: the .obj has no UVs ('vt' lines).")
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
          f"{len(polygons)} faces (1 UV per vertex).")


def _read_obj(filepath: str):
    """
    Reads v/vt/g/o/f. Returns (vertices, uvs, polygons, poly_groups,
    group_names); each polygon is the list of 0-based (v, vt) pairs of its
    corners — vt = v when the face does not reference a UV (`f 1 2 3` or
    `f 1//1 ...`). Faces with fewer than 3 vertices (degenerate) are ignored.
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
                # Collects ALL the corners of the face (does not stop at 3).
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
    Makes sure there is 1 UV per vertex: each unique (v, vt) pair used by the
    faces becomes its own vertex — the vertex is duplicated at UV seams.

    If every corner already uses vt == v (e.g. an .obj written by our export),
    it returns the vertices/UVs unchanged and in the same order. Otherwise
    the new vertices follow the order in which they first appear in the faces
    (vertices that no face uses are dropped). Returns (vertices, uvs,
    polygons), with each polygon as a list of indices.
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

    print(f"      [INFO] faces use different v/vt indices: {len(vertices)} vertices "
          f"-> {len(new_vertices)} (1 per v/vt pair; duplicated at UV seams).")
    return new_vertices, new_uvs, new_polygons
