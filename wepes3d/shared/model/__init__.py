"""
shared.model — the internal PES PS2 3D model (MAGIC_MODEL 03 00 FF FF).

  * parser          — reads/writes the model: Part/Model, parse_model, write_*,
                      detect_asset_type, locate_model.
  * reader          — UNIVERSAL geometry reader of a part/model (verts/UVs/
                      faces), format-aware (port of stadium_modifier).
  * strip           — encodes/decodes the strip data (triangle list/strip).
  * strip_connected — connected tristrips (coherent orientation) — default mode.
  * rebuilder       — rebuilds a part with new geometry (+ pointer patches).
"""

from .parser import (
    Part, Model, detect_asset_type, locate_model, parse_model,
    clone_part_structure, write_part, write_model,
)
from .reader import read_part_geometry, read_model_parts, read_model_geometry
from .strip import (
    triangles_to_pes_strip, pack_strip_indices, align_strip_to_v4,
    pad_to_length, decode_strip,
)
from .rebuilder import (
    update_vertex_count_in_header, rebuild_part, patch_total_parts, patch_parts_end,
)

__all__ = [
    "Part", "Model", "detect_asset_type", "locate_model", "parse_model",
    "clone_part_structure", "write_part", "write_model",
    "read_part_geometry", "read_model_parts", "read_model_geometry",
    "triangles_to_pes_strip", "pack_strip_indices", "align_strip_to_v4",
    "pad_to_length", "decode_strip",
    "update_vertex_count_in_header", "rebuild_part", "patch_total_parts",
    "patch_parts_end",
]
