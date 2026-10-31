"""
shared.io — entrada/saida de arquivo.

  * bin_io      — compressao/descompressao do .bin do PES (zlib + header).
  * pes_archive — "sistema de arquivos" PES (blocos comprimidos / containers).
  * obj_io      — leitura de .obj (Wavefront).
  * obj_write   — escrita de .obj (+ .mtl).
"""

from .bin_io import decompress_bin, compress_bin, decompress_payload
from .pes_archive import (
    load_blocks, model_offsets, is_container,
    PES_ZLIB_MAGIC, PES_FOLDER_MAGIC, HEADER_SIZE,
)
from .obj_io import parse_obj, ObjMesh
from .obj_write import write_obj

__all__ = [
    "decompress_bin", "compress_bin", "decompress_payload",
    "load_blocks", "model_offsets", "is_container",
    "PES_ZLIB_MAGIC", "PES_FOLDER_MAGIC", "HEADER_SIZE",
    "parse_obj", "ObjMesh", "write_obj",
]
