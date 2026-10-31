"""
shared.model — o modelo 3D interno do PES PS2 (MAGIC_MODEL 03 00 FF FF).

  * parser          — parse/escreve o modelo: Part/Model, parse_model, write_*,
                      detect_asset_type, locate_model.
  * reader          — leitor UNIVERSAL de geometria de uma part/modelo (verts/
                      UVs/faces), ciente do formato (porta do stadium_modifier).
  * strip           — codifica/decodifica o strip data (triangle list/strip).
  * strip_connected — tristrips conectados (orientacao coerente) — modo padrao.
  * rebuilder       — reconstroi uma part com geometria nova (+ patch de ponteiros).
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
