"""
shared.io — file input/output.

  * bin_io      — compression/decompression of the PES .bin (zlib + header).
  * pes_archive — PES "file system" (compressed blocks / containers).
  * obj_io      — reading of .obj (Wavefront) + 1 UV per vertex conversion.
  * obj_write   — writing of .obj (+ .mtl).
"""

from .bin_io import decompress_bin, compress_bin, decompress_payload
from .pes_archive import (
    load_blocks, model_offsets, is_container,
    PES_ZLIB_MAGIC, PES_FOLDER_MAGIC, HEADER_SIZE,
)
from .obj_io import parse_obj, ObjMesh, convert_obj_to_vertex_uv
from .obj_write import write_obj

__all__ = [
    "decompress_bin", "compress_bin", "decompress_payload",
    "load_blocks", "model_offsets", "is_container",
    "PES_ZLIB_MAGIC", "PES_FOLDER_MAGIC", "HEADER_SIZE",
    "parse_obj", "ObjMesh", "convert_obj_to_vertex_uv", "write_obj",
]
