"""
Rebuilding of a part with new geometry.

Updates ALL the derived fields that change when `vc` or `strip_num` changes.
Full list (see `docs/02-payload-anatomy.md` for details):

Part header (rel 0x00..0xB0):
  - 0x00 (uint32) = part_size                                  (computed again)
  - 0x0C (uint32) = QWC = (part_size - part_info_start) / 16   (DMA chain)
  - 0x10 (uint32) = strip_indices_total = strip_num × 4
  - 0x2C (uint32) = vbe = 4 × vc + 4   ⚠ copy of [0xC2]
  - 0x30 (uint32) = ss  = 4 × vc + 8   ⚠ copy of [0xC8]

VIF prologue (rel 0xB0..0x110):
  - 0xC2 (uint16) = vbe (vertex_block_end)
  - 0xC8 (uint16) = ss  (strip_start)
  - 0xCA (uint16) = se  (strip_end = ss + strip_num)
  - 0xF6 (uint16) = vbe (2nd copy)
  - 0xF8 (uint16) = vbe (3rd copy)
  - 0x108 (uint8) = vc  (vertex_count, first byte of the qword)

VIF UNPACK tags:
  - vertex tag  (rel 0x110), byte[2] = vc
  - normals tag (after vertices + pad), byte[2] = vc
  - UVs tag     (after normals + pad), byte[2] = vc
  - strip tag   (after VIF_STRIP_MARKER), IMMED = 0xC000 | ss, byte[2] = strip_num
"""

import struct
from typing import List, Optional, Tuple

from ..constants import (
    DMA_ALIGN, MAX_VERTEX_COUNT_PER_PART, MAX_STRIP_NUM,
    PARTS_END_REL_OFFSET, VERTEX_IN_PART_OFFSET,
)
from .parser import Part
from .strip import (
    align_strip_to_v4, pack_strip_indices, pad_to_length,
    triangles_to_pes_strip, STRIP_PADDING_VALUE,
)


# ============================================================================
# Header update for a new vertex count
# ============================================================================

def update_vertex_count_in_header(
    header_bytes: bytes,
    part_info_start_raw: int,
    pre_normals_tag: bytes,
    pre_uvs_tag: bytes,
    new_count: int,
) -> Tuple[bytes, bytes, bytes]:
    """
    Updates the `vc` fields in the header and in the VIF UNPACK tags.

    Why the IMMED of the normals and UVs does NOT change with vc:

    The STCYCL CL=4 WL=1 at the end of the VIF prologue (rel 0x10C) makes each
    V3-16/V2-16 element use 1 "active" qword + 3 skipped qwords. Vertices,
    normals and UVs are INTERLEAVED in the same 4-qword block:

        qw[4 + 4n + 0] = vertex n     (IMMED ADDR = 4)
        qw[4 + 4n + 1] = normal n     (IMMED ADDR = 5)
        qw[4 + 4n + 2] = (skip/empty)
        qw[4 + 4n + 3] = uv n         (IMMED ADDR = 7)

    So the IMMED ADDR of the normals (5) and UVs (7) are CONSTANT — only the
    NUM of the tag changes with vc.

    Historical bug: old versions remapped the IMMEDs as if the layout were
    SEQUENTIAL (normals starting after the vertices in VU memory). This
    caused "unknown vifcmd" crashes in PCSX2 when vc != 87.
    """
    if new_count > MAX_VERTEX_COUNT_PER_PART:
        raise ValueError(
            f"Vertex count ({new_count}) is above the max ({MAX_VERTEX_COUNT_PER_PART}). "
            f"The NUM field of the VIF UNPACK is a uint8."
        )

    vc_offset = part_info_start_raw + VERTEX_IN_PART_OFFSET

    new_header = bytearray(header_bytes)
    struct.pack_into("<H", new_header, vc_offset, new_count)
    if vc_offset + 10 < len(new_header):
        new_header[vc_offset + 10] = new_count & 0xFF

    new_pre_normals = bytearray(pre_normals_tag)
    new_pre_normals[2] = new_count & 0xFF

    new_pre_uvs = bytearray(pre_uvs_tag)
    new_pre_uvs[2] = new_count & 0xFF

    return bytes(new_header), bytes(new_pre_normals), bytes(new_pre_uvs)


# ============================================================================
# Main rebuild
# ============================================================================

def rebuild_part(
    part: Part,
    new_vertices: List[Tuple[int, int, int]],
    new_normals: List[Tuple[int, int, int]],
    new_uvs: List[Tuple[int, int]],
    new_triangles: List[Tuple[int, int, int]],
    new_count: Optional[int] = None,
    strip_mode: str = "connected",
) -> Part:
    """
    Rebuilds a part with new geometry and computes all the derived fields
    again (size, QWC, vbe, ss, se, vc in the tags).

    If `new_count` is different from `part.vertex_count`, it updates the VIF
    tags and the header. Otherwise it keeps the original size (it pads the
    strip with -32768).

    strip_mode:
      "connected" (default) - connected tristrips (strip_connected.py), ~35%
                    smaller; checked in the game. `new_triangles` must already
                    face forward (orient_for_front). See docs/05.
      "list"      - triangle list, 3 indices/triangle. Robust (legacy format).
    """
    vc = len(new_vertices)
    assert vc == len(new_normals), "vertices and normals must have the same size"
    assert vc == len(new_uvs), "vertices and UVs must have the same size"

    if new_count is None:
        new_count = vc

    # 1. Updates the VIF tags if vc changed
    if new_count != part.vertex_count:
        new_header, new_pre_normals_tag, new_pre_uvs_tag = update_vertex_count_in_header(
            part.header_bytes,
            part.part_info_start_raw,
            part.pre_normals_tag,
            part.pre_uvs_tag,
            new_count,
        )
    else:
        new_header = part.header_bytes
        new_pre_normals_tag = part.pre_normals_tag
        new_pre_uvs_tag = part.pre_uvs_tag

    # 2. Padding after the vertices/normals (2 bytes if vc is odd — aligns to 4)
    new_pad_v = b'\x00\x00' if new_count % 2 != 0 else b''
    new_pad_n = b'\x00\x00' if new_count % 2 != 0 else b''

    # 3. Encodes the strip
    if strip_mode == "connected":
        from .strip_connected import (
            build_connected_strips, connected_strips_to_indices,
        )
        new_strip_indices = connected_strips_to_indices(
            build_connected_strips(new_triangles))
        if not new_strip_indices:
            new_strip_indices = triangles_to_pes_strip(new_triangles)
    else:
        new_strip_indices = triangles_to_pes_strip(new_triangles)

    # If vc did not change, keep the original strip size with padding — this
    # stops part_size from changing, so the absolute pointers in pre_parts
    # (which point to parts_end) stay correct.
    if new_count == part.vertex_count:
        orig_strip_count = len(part.strip_indices)
        new_strip_indices = pad_to_length(new_strip_indices, orig_strip_count)

    # Aligns to a multiple of 4 (= 1 V4-16 = 8 bytes)
    new_strip_indices = align_strip_to_v4(new_strip_indices)

    # NUM=0 in the VIF UNPACK is invalid (it is read as 256 elements).
    # If the strip is empty, put a placeholder of 4 paddings.
    if not new_strip_indices:
        new_strip_indices = [STRIP_PADDING_VALUE] * 4

    new_strip_bytes = pack_strip_indices(new_strip_indices)

    new_num_v4 = len(new_strip_bytes) // 8
    if new_num_v4 > MAX_STRIP_NUM:
        raise ValueError(
            f"Strip too long (NUM={new_num_v4} > {MAX_STRIP_NUM}). "
            f"Triangle list uses 3 indices/triangle; NUM (uint8) allows at most "
            f"{MAX_STRIP_NUM} V4-16 elements = {MAX_STRIP_NUM * 4} indices, "
            f"that is ~{MAX_STRIP_NUM * 4 // 3} triangles per part. "
            f"Split this part into more parts or decimate the mesh."
        )

    # 4. Updates the VIF UNPACK tag of the strip:
    #    bytes [-4..-2] = IMMED = 0xC000 | strip_start (= 4*vc + 8)
    #    bytes [-2..]   = NUM + CMD (0x6D = V4-16)
    new_pre_strip = bytearray(part.pre_strip_bytes)
    new_strip_start = 4 * new_count + 8
    new_strip_immed = 0xC000 | (new_strip_start & 0x03FF)
    struct.pack_into("<H", new_pre_strip, len(new_pre_strip) - 4, new_strip_immed)
    new_tag_value = 0x6D00 + new_num_v4
    struct.pack_into("<H", new_pre_strip, len(new_pre_strip) - 2, new_tag_value)
    new_pre_strip = bytes(new_pre_strip)

    # 5. Computes the new size + DMA padding
    new_size = (
        len(new_header)
        + new_count * 6
        + len(new_pad_v)
        + 4
        + new_count * 6
        + len(new_pad_n)
        + 4
        + new_count * 4
        + len(part.pad_after_uvs)
        + len(new_pre_strip)
        + len(new_strip_bytes)
        + len(part.post_strip_bytes)
    )
    align_pad = 0
    if new_size % DMA_ALIGN != 0:
        align_pad = DMA_ALIGN - (new_size % DMA_ALIGN)
        new_size += align_pad
    new_post_strip = part.post_strip_bytes + b'\x00' * align_pad

    # 6. Updates the derived fields in the header
    hdr = bytearray(new_header)
    struct.pack_into("<I", hdr, 0x00, new_size)
    struct.pack_into("<I", hdr, 0x0C,
                     (new_size - part.part_info_start_raw) // 16)  # QWC
    struct.pack_into("<I", hdr, 0x10, new_num_v4 * 4)              # strip_indices_total

    # VU microcode parameters
    vertex_block_end = 4 * new_count + 4
    strip_start = vertex_block_end + 4
    strip_end = strip_start + new_num_v4

    struct.pack_into("<H", hdr, 0xC2, vertex_block_end)
    struct.pack_into("<H", hdr, 0xC8, strip_start)
    struct.pack_into("<H", hdr, 0xCA, strip_end)
    struct.pack_into("<H", hdr, 0xF6, vertex_block_end)
    struct.pack_into("<H", hdr, 0xF8, vertex_block_end)

    # Copies of vbe and ss in the header (Bug 10 — with the template's vc=87
    # they look constant because they are always 352/356, but they change in
    # h2/h4 and face_X.)
    struct.pack_into("<I", hdr, 0x2C, vertex_block_end)
    struct.pack_into("<I", hdr, 0x30, strip_start)

    new_header = bytes(hdr)

    return Part(
        offset_in_payload=part.offset_in_payload,
        size=new_size,
        header_bytes=new_header,
        tex_id=part.tex_id,
        vertex_count=new_count,
        part_info_start_raw=part.part_info_start_raw,
        vertices=new_vertices,
        normals=new_normals,
        uvs=new_uvs,
        strip_indices=new_strip_indices,
        pad_after_vertices=new_pad_v,
        pre_normals_tag=new_pre_normals_tag,
        pad_after_normals=new_pad_n,
        pre_uvs_tag=new_pre_uvs_tag,
        pad_after_uvs=part.pad_after_uvs,
        pre_strip_bytes=new_pre_strip,
        post_strip_bytes=new_post_strip,
    )


# ============================================================================
# Patches in pre_parts (global header)
# ============================================================================

def patch_total_parts(pre_parts_bytes: bytes, offset_file_1: int,
                      new_total: int) -> bytes:
    """Updates `total_parts` in the model header (offset_file_1 + 0x20)."""
    arr = bytearray(pre_parts_bytes)
    struct.pack_into("<I", arr, offset_file_1 + 0x20, new_total)
    return bytes(arr)


def patch_parts_end(payload: bytes, offset_file_1: int, new_parts_end: int) -> bytes:
    """Updates the end of the parts in the model header (offset_file_1 + 0x2C),
    which is stored RELATIVE to the model: `new_parts_end - offset_file_1`."""
    arr = bytearray(payload)
    struct.pack_into("<I", arr, offset_file_1 + PARTS_END_REL_OFFSET,
                     new_parts_end - offset_file_1)
    return bytes(arr)

