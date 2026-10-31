"""
Reader of the PES6/WE PC model format (magic 20050420).

PC and PS2 are DIFFERENT binary formats — this reader does NOT use the PS2
engine (`shared/model`, `shared/pipeline`); only the common decompression
(`shared/io`).

Structure (reverse engineering, see pes6_bin_to_obj.py / pes6_trophy_to_obj.py):

  * FACE/HAIR: the payload has the model DIRECTLY — payload[8] points to the
    20050420 magic.
  * TROPHY: the payload is a nested container (outer 00060100, already
    decompressed -> 00060000) with SEVERAL 20050420 models, one per PART
    (cup, base, handles...).

In both cases each model is read the same way: we find the models by
scanning for the magic and parse each one with `parse_model` (inner pointers
are relative to the start of the model).

Vertex groups: marker `07 <m>` + 4xuint16 (total_tlist, vert_start,
total_verts, total_f). The 2nd byte changes (face 0x05, trophy 0x26); we find
the one that makes the sums match (sum total_verts == vc, sum total_tlist ==
tri_total). The strip indices are GLOBAL (do not add vert_start).
"""

import struct
from typing import List, Tuple

from .coords import raw_to_obj_vertex, raw_to_obj_uv

MODEL_MAGIC = bytes([0x20, 0x05, 0x04, 0x20])   # PES6 PC model

Vert = Tuple[float, float, float]
UV = Tuple[float, float]
Face = Tuple[int, int, int]


def find_parts(payload: bytes) -> List[int]:
    """Offsets of each PES6 PC model (magic 20050420) in the payload.

    Face -> 1 offset; trophy -> N (one per part). Robust scan (it does not
    depend on walking the container directory)."""
    parts = []
    pos = 0
    while True:
        f = payload.find(MODEL_MAGIC, pos)
        if f == -1:
            break
        parts.append(f)
        pos = f + 4
    return parts


def find_vertex_groups(hdr_block: bytes, vc: int, tri_total: int):
    """
    Table of vertex groups inside the header block of a model.

    Each group: `07 <m>` + 4xuint16 (total_tlist, vert_start, total_verts,
    total_f). We find the <m> marker by checking the sums. Returns a list of
    (total_tlist, vert_start, total_verts, total_f), or None.
    """
    candidates = {hdr_block[j + 1]
                  for j in range(len(hdr_block) - 9)
                  if hdr_block[j] == 0x07 and hdr_block[j + 1] != 0x00}
    for m in sorted(candidates):
        marker = bytes([0x07, m])
        entries = []
        pos = 0
        while True:
            f = hdr_block.find(marker, pos)
            if f == -1 or f + 10 > len(hdr_block):
                break
            tl, vsr, tv, tf = struct.unpack_from("<4H", hdr_block, f + 2)
            if 0 < tv <= vc and 0 < tl <= tri_total and vsr + tv <= vc:
                entries.append((tl, vsr, tv, tf))
            pos = f + 2
        if entries and sum(e[2] for e in entries) == vc \
                   and sum(e[0] for e in entries) == tri_total:
            return entries
    return None


def parse_model(payload: bytes, off1: int) -> Tuple[List[Vert], List[UV], List[Face]]:
    """
    Reads ONE PES6 PC model that starts at `off1` (magic 20050420).
    Returns (verts, uvs, faces), already in OBJ space.
    """
    magic = payload[off1:off1 + 4]
    if magic != MODEL_MAGIC:
        raise ValueError(f"offset {off1:#x} has no PES6 PC model magic "
                         f"(found {magic.hex()}).")

    end_of_header, _, _mat_info, vertex_off, idx_off, header_start = \
        struct.unpack_from("<6I", payload, off1 + 4)
    end_of_header += off1
    vertex_off    += off1
    idx_off       += off1
    header_start  += off1

    vc = struct.unpack_from("<H", payload, vertex_off + 8)[0]
    tri_total = struct.unpack_from("<H", payload, idx_off)[0]

    # --- vertex groups (they break the strip at the group borders) ---
    hdr_block = payload[header_start:end_of_header]
    groups = find_vertex_groups(hdr_block, vc, tri_total)
    if groups is None:
        groups = [(tri_total, 0, vc, 0)]   # fallback: a single group

    vg_ranges = []
    tri_counter = 0
    for total_tlist, _vs, _tv, _tf in groups:
        vg_ranges.append((tri_counter, tri_counter + total_tlist))
        tri_counter += total_tlist

    # --- vertices + UVs ---
    cursor = vertex_off + 8
    vc2, vs, _pad, _anim = struct.unpack_from("<H2BI", payload, cursor)
    cursor += 8

    verts: List[Vert] = []
    uvs: List[UV] = []
    for _ in range(vc2):
        raw_x, raw_y, raw_z = struct.unpack_from("<3f", payload, cursor)
        cursor += 12
        verts.append(raw_to_obj_vertex(raw_x, raw_y, raw_z))
        cursor += vs - 20            # padding / normals / weights
        u, v = struct.unpack_from("<2f", payload, cursor)
        cursor += 8
        uvs.append(raw_to_obj_uv(u, v))

    # --- indices (triangle strip per group) ---
    tlist = struct.unpack_from(f"<{tri_total}H", payload, idx_off + 2)
    faces: List[Face] = []
    for ts, te in vg_ranges:
        strip = tlist[ts:te]
        for i in range(len(strip) - 2):
            a, b, c = strip[i], strip[i + 1], strip[i + 2]
            if a != b and b != c and a != c:    # skips degenerate ones (restart)
                faces.append((c, b, a))          # reversed winding (= plugin)

    return verts, uvs, faces
