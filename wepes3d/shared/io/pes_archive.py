"""
Reading of the PES PS2 "file system" (shared by stadiums and kits).

Two wrappers:
  * compressed block — magic 00 06 01 00 (same as face/trophy/.str): 32-byte
    header + zlib. It decompresses into ONE payload.
  * container        — magic 00 06 00 00: a PES "folder", possibly NESTED
    (a container inside a container) down to the compressed blocks. Each
    block decompresses into a payload with 0..N models.

`load_blocks(path)` returns the list of decompressed payloads:
  - 00 06 01 00: decompresses it directly (1 payload);
  - 00 06 00 00: SCANS the file for ALL valid 00 06 01 00 blocks (at any
    depth) and decompresses each one — it handles nesting without walking the
    TOCs; each candidate is checked by decompressing it (size == the
    decomp_size field of the header).

A decompressed payload is a "model folder": [0] = total, [4] = TOC offset,
TOC[i] (uint32) = ABSOLUTE offset of model i (`MAGIC_MODEL` 03 00 FF FF).
`model_offsets(payload)` reads this (and skips entries that are not models).
"""

import struct
import zlib
from typing import List

from .bin_io import decompress_bin, decompress_payload
from ..constants import MAGIC_MODEL

PES_ZLIB_MAGIC = bytes([0x00, 0x06, 0x01, 0x00])     # compressed block
PES_FOLDER_MAGIC = bytes([0x00, 0x06, 0x00, 0x00])   # container
HEADER_SIZE = 32


def is_container(data: bytes) -> bool:
    return data[:4] == PES_FOLDER_MAGIC


def _scan_zlib_blocks(data: bytes) -> List[bytes]:
    """Finds and decompresses all valid 00 06 01 00 blocks in `data`.

    A candidate is accepted when its zlib stream (at +32) decompresses
    without error and the size matches decomp_size (header +8). It then
    jumps by comp_size (header +4), so it does not scan inside the block
    again."""
    out: List[bytes] = []
    pos = 0
    n = len(data)
    while True:
        i = data.find(PES_ZLIB_MAGIC, pos)
        if i < 0 or i + 32 > n:
            break
        comp_size = struct.unpack_from("<I", data, i + 4)[0]
        decomp_size = struct.unpack_from("<I", data, i + 8)[0]
        advanced = False
        if 0 < decomp_size and 0 < comp_size <= n - (i + 32):
            try:
                raw = zlib.decompressobj().decompress(data[i + 32:])
                if len(raw) == decomp_size:
                    out.append(raw)
                    pos = i + 32 + comp_size
                    advanced = True
            except zlib.error:
                pass
        if not advanced:
            pos = i + 4
    return out


def load_blocks(path: str) -> List[bytes]:
    """List of decompressed payloads (1 for a compressed block, N for a
    container, at any depth)."""
    with open(path, "rb") as f:
        data = f.read()
    magic = data[:4]

    if magic == PES_ZLIB_MAGIC:
        payload, _, _ = decompress_bin(path)
        return [payload]

    if magic == PES_FOLDER_MAGIC:
        return _scan_zlib_blocks(data)

    raise ValueError(
        f"unknown magic: {magic.hex()} "
        f"(expected {PES_ZLIB_MAGIC.hex()} compressed or {PES_FOLDER_MAGIC.hex()} container)")


def model_offsets(payload: bytes) -> List[int]:
    """ABSOLUTE offsets of each model (`MAGIC_MODEL`) in the decompressed
    payload. Layout: [0] = total, [4] = TOC offset, TOC[i] (uint32) = offset
    of model i. Entries that do not point to `MAGIC_MODEL` (textures/data)
    are ignored."""
    if len(payload) < 8:
        return []
    total = struct.unpack_from("<I", payload, 0)[0]
    toc = struct.unpack_from("<I", payload, 4)[0]
    offsets: List[int] = []
    for i in range(total):
        pos = toc + 4 * i
        if pos + 4 > len(payload):
            break
        o = struct.unpack_from("<I", payload, pos)[0]
        if 0 <= o + 4 <= len(payload) and payload[o:o + 4] == MAGIC_MODEL:
            offsets.append(o)
    return offsets
