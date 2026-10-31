"""
Parser of the decompressed payload: reads parts, vertices, UVs, normals, strip.

Payload layout (simple face.bin, 8 parts):

    [pre_parts: 272 bytes]   - global header + pointers (incl. parts_end)
    [parts:    16560 bytes]  - 8 parts of ~2048..2080 bytes each
    [post_parts: 21632 bytes] - header + texture

Each part is:

    [part_header: 176 bytes]  (rel offset 0x00 .. 0xB0)
    [VIF prologue: 96 bytes]  (rel offset 0xB0 .. 0x110)
    [VIF unpack tag of the vertices: 4 bytes]
    [vertices: vc × 6 bytes]
    [padding (2 bytes if vc is odd)]
    [VIF unpack tag of the normals: 4 bytes]
    [normals: vc × 6 bytes]
    [padding (2 bytes if vc is odd)]
    [VIF unpack tag of the UVs: 4 bytes]
    [UVs: vc × 4 bytes]
    [padding up to VIF_STRIP_MARKER]
    [VIF_STRIP_MARKER: 8 bytes]
    [VIF unpack tag of the strip: 4 bytes]
    [strip data: strip_num × 8 bytes]
    [post_strip + DMA pad]

See `docs/02-payload-anatomy.md` for the full description of each field.
"""

import struct
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..constants import (
    MAGIC_MODEL, CONTAINER_MAGIC, VIF_STRIP_MARKER, PARTS_INFO_OFFSET,
    TEXTURE_INDEX_IN_PART, VERTEX_IN_PART_OFFSET,
)


@dataclass
class Part:
    """One part of the model: a block with geometry + VIF microcode parameters."""

    offset_in_payload: int
    size: int
    header_bytes: bytes
    """Bytes 0x00 .. vertices_start (part header + VIF prologue + vertex tag).
    Kept almost untouched between rebuilds — we only update the derived
    fields (part_size, QWC, strip_indices_total, vbe, ss, se, vc).
    """

    tex_id: int
    vertex_count: int
    part_info_start_raw: int
    """Relative offset of the VIF prologue (same as `header[0x08]`). Usually
    0xB0 in the simple template."""

    vertices: List[Tuple[int, int, int]]
    """(y, z, x) int16 — the .bin order (X is the LAST one in the stored triplet)."""

    normals: List[Tuple[int, int, int]]
    """(nx, ny, nz) int16 — normal order, DIFFERENT from the vertices."""

    uvs: List[Tuple[int, int]]
    """(u, v) int16."""

    strip_indices: List[int]
    """Raw int16 with bit 15 = ADC flag (restart in the decoder)."""

    pad_after_vertices: bytes
    pre_normals_tag: bytes
    pad_after_normals: bytes
    pre_uvs_tag: bytes
    pad_after_uvs: bytes
    pre_strip_bytes: bytes
    """Bytes between the UVs and strip_data: VIF_STRIP_MARKER + VIF UNPACK tag
    of the strip (12 bytes in total)."""

    post_strip_bytes: bytes
    """Bytes after strip_data up to the end of the part. Usually a STMOD
    mode=0 (`00 00 00 05`) followed by zero padding for the DMA alignment."""


@dataclass
class Model:
    """Full model: parts + the bytes around them, kept untouched."""

    payload: bytes
    """Original decompressed payload — optional, used for debugging."""

    offset_file_1: int
    """Offset where MAGIC_MODEL starts in the payload. Usually 0x10."""

    pre_parts_bytes: bytes
    """Bytes 0x00 .. parts_start. Includes the outer header + model header +
    metadata (and, in "rich" files, the 12 KB bones area)."""

    parts: List[Part]

    post_parts_bytes: bytes
    """Bytes after the last part: texture + metadata. Kept untouched."""


def detect_asset_type(payload: bytes) -> str:
    """Returns 'face' (direct model) or 'trophy' (nested container) by looking
    at the magic at `payload[8]` (offset_file_1)."""
    offset_file_1 = struct.unpack_from("<I", payload, 8)[0]
    magic = payload[offset_file_1:offset_file_1 + 4]
    if magic == MAGIC_MODEL:
        return "face"
    if magic == CONTAINER_MAGIC:
        return "trophy"
    raise ValueError(f"Unknown magic at offset_file_1=0x{offset_file_1:X}: "
                     f"{magic.hex()} (neither face {MAGIC_MODEL.hex()} nor "
                     f"trophy {CONTAINER_MAGIC.hex()})")


def locate_model(payload: bytes) -> int:
    """
    Returns the ABSOLUTE offset in the payload where the MAGIC_MODEL (0300ffff)
    of the 3D model starts — the point from which the parts structure is the
    same for faces and trophies.

      FACE   : direct model at offset_file_1 (payload[8]).
      TROPHY : container at offset_file_1 -> base = offset_file_1 + 32 ->
               offset_mdl = base + uint32(base+8).
    """
    offset_file_1 = struct.unpack_from("<I", payload, 8)[0]
    magic = payload[offset_file_1:offset_file_1 + 4]
    if magic == MAGIC_MODEL:
        return offset_file_1
    if magic == CONTAINER_MAGIC:
        base = offset_file_1 + 32
        off_mdl = struct.unpack_from("<I", payload, base + 8)[0] + base
        mdl_magic = payload[off_mdl:off_mdl + 4]
        if mdl_magic != MAGIC_MODEL:
            raise ValueError(
                f"Container without a valid MDL: magic@0x{off_mdl:X}={mdl_magic.hex()}")
        return off_mdl
    raise ValueError(f"Unknown magic: {magic.hex()}")


def parse_model(payload: bytes, model_offset: Optional[int] = None) -> Model:
    """
    Reads the decompressed payload and returns the filled `Model` structure.

    `model_offset`: offset of the MAGIC_MODEL. If None, it is found
    automatically (`locate_model`) — works for faces (direct model) and
    trophies (container). The `Model.offset_file_1` field stores this offset
    of the MODEL (not payload[8]).
    """
    if model_offset is None:
        model_offset = locate_model(payload)
    offset_file_1 = model_offset
    magic = payload[offset_file_1:offset_file_1 + 4]
    if magic != MAGIC_MODEL:
        raise ValueError(f"Wrong magic: {magic.hex()}")

    total_parts, parts_start_rel = struct.unpack_from(
        "<II", payload, offset_file_1 + PARTS_INFO_OFFSET
    )
    parts_start_abs = parts_start_rel + offset_file_1
    pre_parts_bytes = payload[:parts_start_abs]

    parts: List[Part] = []
    cursor = parts_start_abs
    for _ in range(total_parts):
        part = _parse_part(payload, cursor)
        parts.append(part)
        cursor += part.size

    post_parts_bytes = payload[cursor:]
    return Model(
        payload=payload,
        offset_file_1=offset_file_1,
        pre_parts_bytes=pre_parts_bytes,
        parts=parts,
        post_parts_bytes=post_parts_bytes,
    )


def _parse_part(payload: bytes, offset: int) -> Part:
    """Reads one part from an absolute offset in the payload."""
    part_size = struct.unpack_from("<I", payload, offset)[0]
    tex_id = struct.unpack_from("<I", payload, offset + TEXTURE_INDEX_IN_PART)[0]
    part_info_start_raw = struct.unpack_from("<I", payload, offset + 8)[0]

    vertex_count_pos = offset + part_info_start_raw + VERTEX_IN_PART_OFFSET
    vertex_count = struct.unpack_from("<H", payload, vertex_count_pos)[0]
    vertices_start = vertex_count_pos + 12

    header_bytes = payload[offset:vertices_start]

    # Vertices (y, z, x) int16
    vertices: List[Tuple[int, int, int]] = []
    cursor = vertices_start
    for _ in range(vertex_count):
        y, z, x = struct.unpack_from("<hhh", payload, cursor)
        vertices.append((y, z, x))
        cursor += 6

    # Padding after the vertices (2 bytes if vc is odd)
    pad_v_size = 2 if vertex_count % 2 != 0 else 0
    pad_after_vertices = payload[cursor:cursor + pad_v_size]
    cursor += pad_v_size

    # VIF UNPACK tag of the normals (4 bytes)
    pre_normals_tag = payload[cursor:cursor + 4]
    cursor += 4

    # Normals (nx, ny, nz) int16
    normals: List[Tuple[int, int, int]] = []
    for _ in range(vertex_count):
        nx, ny, nz = struct.unpack_from("<hhh", payload, cursor)
        normals.append((nx, ny, nz))
        cursor += 6

    pad_n_size = 2 if vertex_count % 2 != 0 else 0
    pad_after_normals = payload[cursor:cursor + pad_n_size]
    cursor += pad_n_size

    # VIF UNPACK tag of the UVs
    pre_uvs_tag = payload[cursor:cursor + 4]
    cursor += 4

    # UVs (u, v) int16
    uvs: List[Tuple[int, int]] = []
    for _ in range(vertex_count):
        u, v = struct.unpack_from("<hh", payload, cursor)
        uvs.append((u, v))
        cursor += 4

    # Looks for the VIF_STRIP_MARKER in the rest of the part
    part_end = offset + part_size
    remaining = payload[cursor:part_end]
    marker_pos = remaining.find(VIF_STRIP_MARKER)
    if marker_pos == -1:
        raise ValueError(f"VIF_STRIP_MARKER not found in part @ 0x{offset:x}")

    pad_after_uvs = remaining[:marker_pos]
    strip_block_start = cursor + marker_pos

    # After the marker (8 bytes) comes the VIF UNPACK V4-16 tag of the strip
    tag_pos = strip_block_start + 8 + 2  # +2 to skip the IMMED bytes of the tag
    tag_value = struct.unpack_from("<H", payload, tag_pos)[0]
    num_v4_elements = tag_value - 0x6D00  # CMD 0x6D = V4-16; what is left is NUM
    strip_data_bytes = num_v4_elements * 8

    pre_strip_bytes = payload[strip_block_start:tag_pos + 2]
    strip_data_start = tag_pos + 2
    strip_data_end = strip_data_start + strip_data_bytes

    num_indices = strip_data_bytes // 2
    strip_indices = list(struct.unpack_from(
        f"<{num_indices}h", payload, strip_data_start))

    post_strip_bytes = payload[strip_data_end:part_end]

    return Part(
        offset_in_payload=offset,
        size=part_size,
        header_bytes=header_bytes,
        tex_id=tex_id,
        vertex_count=vertex_count,
        part_info_start_raw=part_info_start_raw,
        vertices=vertices,
        normals=normals,
        uvs=uvs,
        strip_indices=strip_indices,
        pad_after_vertices=pad_after_vertices,
        pre_normals_tag=pre_normals_tag,
        pad_after_normals=pad_after_normals,
        pre_uvs_tag=pre_uvs_tag,
        pad_after_uvs=pad_after_uvs,
        pre_strip_bytes=pre_strip_bytes,
        post_strip_bytes=post_strip_bytes,
    )


def clone_part_structure(donor: Part) -> Part:
    """
    Creates an empty Part that copies the whole VIF structure of `donor`
    (tags, padding, pre/post strip), but with no geometry. The geometry is
    filled in later by `rebuilder.rebuild_part()`. Used to create extra parts
    beyond the ones in the template.
    """
    return Part(
        offset_in_payload=0,
        size=donor.size,
        header_bytes=donor.header_bytes,
        tex_id=donor.tex_id,
        vertex_count=donor.vertex_count,
        part_info_start_raw=donor.part_info_start_raw,
        vertices=[],
        normals=[],
        uvs=[],
        strip_indices=[],
        pad_after_vertices=donor.pad_after_vertices,
        pre_normals_tag=donor.pre_normals_tag,
        pad_after_normals=donor.pad_after_normals,
        pre_uvs_tag=donor.pre_uvs_tag,
        pad_after_uvs=donor.pad_after_uvs,
        pre_strip_bytes=donor.pre_strip_bytes,
        post_strip_bytes=donor.post_strip_bytes,
    )


def write_part(part: Part) -> bytes:
    """Serializes a Part back into bytes, in the same order as the parser."""
    out = bytearray()
    out += part.header_bytes
    for (y, z, x) in part.vertices:
        out += struct.pack("<hhh", y, z, x)
    out += part.pad_after_vertices
    out += part.pre_normals_tag
    for (nx, ny, nz) in part.normals:
        out += struct.pack("<hhh", nx, ny, nz)
    out += part.pad_after_normals
    out += part.pre_uvs_tag
    for (u, v) in part.uvs:
        out += struct.pack("<hh", u, v)
    out += part.pad_after_uvs
    out += part.pre_strip_bytes
    for idx in part.strip_indices:
        out += struct.pack("<h", idx)

    # If something went wrong and the content is smaller than part.size, fill
    # it with zeros. It usually does not happen — just a safety net for
    # imperfect roundtrips.
    written = len(out) + len(part.post_strip_bytes)
    if written < part.size:
        out += b'\x00' * (part.size - written)
    out += part.post_strip_bytes
    return bytes(out)


def write_model(model: Model) -> bytes:
    """Serializes the whole Model: pre_parts + all parts + post_parts."""
    out = bytearray()
    out += model.pre_parts_bytes
    for part in model.parts:
        out += write_part(part)
    out += model.post_parts_bytes
    return bytes(out)
