"""
ASSET-AGNOSTIC geometry: bounding box, auto-fit and normals.

The int16<->float conversions (specific to each asset) are NOT here — they are
in each `adapters/pesweps2/<asset>/profile.py`, exposed through CoordSpace. The
functions below receive the `int16_to_obj` converter when they need to turn
the template int16 values back into OBJ space.
"""

import math
from typing import Callable, List, Tuple


# ============================================================================
# Bounding box and auto-fit
# ============================================================================

def compute_obj_bbox(vertices: List[Tuple[float, float, float]]
                     ) -> Tuple[Tuple[float, float, float],
                                Tuple[float, float, float]]:
    """Returns (min_xyz, max_xyz) of the coordinates of a vertex array."""
    return (
        (min(v[0] for v in vertices),
         min(v[1] for v in vertices),
         min(v[2] for v in vertices)),
        (max(v[0] for v in vertices),
         max(v[1] for v in vertices),
         max(v[2] for v in vertices)),
    )


def compute_template_obj_bbox(template, int16_to_obj: Callable
                              ) -> Tuple[Tuple[float, float, float],
                                         Tuple[float, float, float]]:
    """Bbox of a template (Model) in OBJ space — turns the int16 vertices of
    all parts back into floats and takes min/max.

    `int16_to_obj`: the asset's stored->obj converter
    (`profile.coord.int16_to_obj_vertex`)."""
    all_x: List[float] = []
    all_y: List[float] = []
    all_z: List[float] = []
    for part in template.parts:
        for (s0, s1, s2) in part.vertices:
            x, y, z = int16_to_obj(s0, s1, s2)
            all_x.append(x)
            all_y.append(y)
            all_z.append(z)
    return (
        (min(all_x), min(all_y), min(all_z)),
        (max(all_x), max(all_y), max(all_z)),
    )


def auto_fit_vertices(vertices: List[Tuple[float, float, float]],
                      template, int16_to_obj: Callable
                      ) -> List[Tuple[float, float, float]]:
    """
    Rescales and moves the OBJ vertices so they fit inside the template
    bbox.

    Uses a UNIFORM scale (keeps the proportions of the imported face):
      - Computes the bbox of the OBJ and of the template (both in float OBJ
        space).
      - Scales uniformly with the MIN ratio (the whole face fits in the bbox).
      - Moves it so the centers match.

    Without this, an .obj with an arbitrary position/scale (from outside
    sources) ends up outside the PES PS2 frustum -> invisible face in the
    editor and in the game.
    """
    omin, omax = compute_obj_bbox(vertices)
    tmin, tmax = compute_template_obj_bbox(template, int16_to_obj)

    o_span = (omax[0] - omin[0], omax[1] - omin[1], omax[2] - omin[2])
    t_span = (tmax[0] - tmin[0], tmax[1] - tmin[1], tmax[2] - tmin[2])

    sx = t_span[0] / o_span[0] if o_span[0] > 0 else 1.0
    sy = t_span[1] / o_span[1] if o_span[1] > 0 else 1.0
    sz = t_span[2] / o_span[2] if o_span[2] > 0 else 1.0
    scale = min(sx, sy, sz)

    o_ctr = ((omin[0] + omax[0]) / 2,
             (omin[1] + omax[1]) / 2,
             (omin[2] + omax[2]) / 2)
    t_ctr = ((tmin[0] + tmax[0]) / 2,
             (tmin[1] + tmax[1]) / 2,
             (tmin[2] + tmax[2]) / 2)

    print(f"      OBJ bbox:      X[{omin[0]:.3f}..{omax[0]:.3f}] "
          f"Y[{omin[1]:.3f}..{omax[1]:.3f}] Z[{omin[2]:.3f}..{omax[2]:.3f}]")
    print(f"      Template bbox: X[{tmin[0]:.3f}..{tmax[0]:.3f}] "
          f"Y[{tmin[1]:.3f}..{tmax[1]:.3f}] Z[{tmin[2]:.3f}..{tmax[2]:.3f}]")
    print(f"      Uniform scale: {scale:.4f} "
          f"(sx={sx:.4f}, sy={sy:.4f}, sz={sz:.4f})")

    return [
        ((x - o_ctr[0]) * scale + t_ctr[0],
         (y - o_ctr[1]) * scale + t_ctr[1],
         (z - o_ctr[2]) * scale + t_ctr[2])
        for (x, y, z) in vertices
    ]


# ============================================================================
# Normals
# ============================================================================

def compute_vertex_normals(
    vertices: List[Tuple[float, float, float]],
    faces: List[Tuple[int, int, int]],
) -> List[Tuple[float, float, float]]:
    """
    Computes SMOOTH per-vertex normals as an area-weighted average of the
    triangles around each vertex.

    For each face, face_normal = cross(b-a, c-a). The length of the cross
    product is 2x the triangle area, so adding this normal already weights
    it by area. We normalize at the end.

    Result: each vertex gets the average of the normals of the faces that
    use it, weighted by area. A good default for faces with no explicit
    smoothing information.
    """
    n = len(vertices)
    sx = [0.0] * n
    sy = [0.0] * n
    sz = [0.0] * n

    for (a, b, c) in faces:
        ax, ay, az = vertices[a]
        bx, by, bz = vertices[b]
        cx, cy, cz = vertices[c]

        e1x, e1y, e1z = bx - ax, by - ay, bz - az
        e2x, e2y, e2z = cx - ax, cy - ay, cz - az

        fnx = e1y * e2z - e1z * e2y
        fny = e1z * e2x - e1x * e2z
        fnz = e1x * e2y - e1y * e2x

        for vi in (a, b, c):
            sx[vi] += fnx
            sy[vi] += fny
            sz[vi] += fnz

    result: List[Tuple[float, float, float]] = []
    for i in range(n):
        length = math.sqrt(sx[i] ** 2 + sy[i] ** 2 + sz[i] ** 2)
        if length > 1e-10:
            result.append((sx[i] / length, sy[i] / length, sz[i] / length))
        else:
            result.append((0.0, 1.0, 0.0))   # fallback for isolated vertices
    return result
