"""
shared.geometry — matematica de espaco (asset-agnostica).

  * coords    — CoordSpace (int16<->float por asset) + conversao de UV + clamp16.
  * transform — bounding box, auto-fit (encaixa no bbox do template) e calculo
                de normais por vertice.
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
