"""
Compression and decompression of PES PS2 .bin files.

A PES PS2 .bin file has:
  [outer_header: 16 bytes] [ps2_extra: 16 bytes] [zlib_payload]

The decompressed payload is the "real" content — what the parser reads.
The outer_header stores:
  - bytes [4..8]: size of the compressed payload
  - bytes [8..12]: size of the decompressed payload

The other header bytes are kept untouched in a roundtrip (they belong to the
PES file system and do not matter for the 3D model).
"""

import struct
import zlib
from typing import Tuple


def decompress_bin(filepath: str) -> Tuple[bytes, bytes, bytes]:
    """
    Reads and decompresses a PES PS2 .bin file.

    Returns:
        payload: decompressed bytes (the "real" content of the model).
        outer_full_header: the first 32 bytes (outer_header + ps2_extra).
        trailing: data after the zlib blob (usually empty, kept for the
            roundtrip).
    """
    with open(filepath, 'rb') as f:
        outer_header = f.read(16)
        ps2_extra = f.read(16)
        zlib_blob = f.read()

    decompressor = zlib.decompressobj()
    payload = decompressor.decompress(zlib_blob)
    trailing = decompressor.unused_data

    return payload, outer_header + ps2_extra, trailing


def decompress_payload(block: bytes) -> bytes:
    """
    Decompresses a .bin block given as BYTES (instead of a path).

    `block` must start with the 32-byte header (magic 00 06 01 00 + sizes),
    followed by the zlib blob. Bytes after the zlib stream (e.g. the next
    block of a container) are ignored. Useful for compressed blocks inside a
    00 06 00 00 container (stadiums).
    """
    decompressor = zlib.decompressobj()
    return decompressor.decompress(block[32:])


def compress_bin(payload: bytes, outer_full_header: bytes, trailing: bytes,
                 output_path: str) -> None:
    """
    Compresses a payload and writes it in the PES PS2 .bin format.

    Updates the size fields in the outer header:
      - byte[4..8]:  uint32 LE = size of the compressed payload
      - byte[8..12]: uint32 LE = size of the decompressed payload

    The other header bytes are kept as they were.
    """
    compressed = zlib.compress(payload, 9)

    new_header = bytearray(outer_full_header)
    struct.pack_into("<I", new_header, 4, len(compressed))
    struct.pack_into("<I", new_header, 8, len(payload))

    with open(output_path, 'wb') as f:
        f.write(new_header)
        f.write(compressed)
        f.write(trailing)
