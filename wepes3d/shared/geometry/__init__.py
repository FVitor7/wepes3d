"""
shared.geometry — space math (asset-agnostic).

  * coords    — CoordSpace (int16<->float per asset) + UV conversion + clamp16.
  * transform — bounding box, auto-fit (fits into the template bbox) and
                per-vertex normals.
"""

from .coords import (
    CoordSpace, clamp16, obj_to_int16_uv, int16_to_obj_uv,
)
from .transform import (
    compute_obj_bbox, compute_template_obj_bbox,
    auto_fit_vertices, compute_vertex_normals,
)

__all__ = [
    "CoordSpace", "clamp16", "obj_to_int16_uv", "int16_to_obj_uv",
    "compute_obj_bbox", "compute_template_obj_bbox",
    "auto_fit_vertices", "compute_vertex_normals",
]
