"""
UNIVERSAL geometry reader of the PES PS2 model (verts/UVs/faces).

Three levels:
  * read_part_geometry  — one part -> (verts_raw int16, uvs_raw int16, faces_local).
                          Format-aware (port of `stadium_modifier.read_ps2_mdl_part`),
                          no fallback; covers faces, trophy sec0..8, stadiums and kits.
  * read_model_parts    — all parts of a model, already in OBJ space (receives
                          the CoordSpace), NOT merged (1 entry per part).
  * read_model_geometry — the same, but MERGED into one (verts, uvs, faces).

Shared by face/trophy (export), stadiums and kits.
"""

import struct

from ..constants import VIF_STRIP_MARKER
from .parser import parse_model

# Submesh separator = STCYCL CL=4 WL=1 (4 bytes): it starts each geometry
# sub-block of a part.
_SUBMESH_SEP = bytes([0x04, 0x01, 0x00, 0x01])
_VSIZE = {0x69: 6, 0x68: 12, 0x65: 4, 0x6D: 8}   # bytes per element for each UNPACK CMD


def read_part_geometry(payload, part):
    """
    UNIVERSAL geometry reader of one part (verts/UVs/faces), format-aware — no
    fallback. It uses the algorithm of `stadium_modifier.py`
    (read_ps2_mdl_part), the most complete decoder of the community. It
    covers ALL the observed cases (faces, trophy sec0..8, stadiums, kits)
    because the simple case is just `total_submesh == 1`:

      - Structure: at `v_address` (= part + part_info_start) there is a
        sub-header; `total_submesh` at v_address+44; a table of descriptors
        (36 bytes each); the STCYCL CL=4 WL=1 marker (`_SUBMESH_SEP`); then N
        submeshes.
      - Each submesh starts with a VIF tag `H2B` (IMMED, NUM, CMD); the CMD
        gives the vertex format: 0x69=V3-16 (int16, 6B), 0x68=V3-32 (int32,
        12B). Normals and UVs follow (the UVs may have an extra block:
        `uv_type - v_type == 2`).
      - The strip indexes the UNION of the submeshes by VU ADDRESS; the fix
        `diff = max(idx) - total_verts + 1` gives back the global index
        without needing the base address (single block: diff == 0). Decoded
        with a sliding window and alternating winding.

    Scale/axes are NOT applied here (that is the job of `profile.coord`): it
    returns raw ints. Returns (verts_raw[(s0,s1,s2)], uvs_raw[(u,v)],
    faces_local), or None if the structure does not match.
    """
    off = part.offset_in_payload
    size = part.size
    v_addr = off + part.part_info_start_raw
    tstrip_size = struct.unpack_from("<I", payload, off + 16)[0]
    if v_addr + 48 > off + size:
        return None
    total_sub = struct.unpack_from("<I", payload, v_addr + 44)[0]
    if not (1 <= total_sub < 4096):
        return None
    p = v_addr + 56 + 36 * total_sub
    if payload[p:p + 4] != _SUBMESH_SEP:
        return None
    p += 4

    verts, uvs = [], []
    end = off + size
    uv_end = p
    for sub in range(total_sub):
        if p + 4 > end:
            return None
        v_type, v_num, v_fmt = struct.unpack_from("<H2B", payload, p); p += 4
        vs = _VSIZE.get(v_fmt, 6)
        for _ in range(v_num):
            if v_fmt == 0x68:
                verts.append(struct.unpack_from("<iii", payload, p))
            else:
                verts.append(struct.unpack_from("<hhh", payload, p))
            p += vs
        if v_num % 2 and v_fmt == 0x69:
            p += 2
        _, _, n_fmt = struct.unpack_from("<H2B", payload, p); p += 4
        p += v_num * _VSIZE.get(n_fmt, 6)
        if v_num % 2 and n_fmt == 0x69:
            p += 2
        uv_type, _, uv_fmt = struct.unpack_from("<H2B", payload, p); p += 4
        if uv_type - v_type == 2:                 # extra block (color/2nd uv)
            p += v_num * _VSIZE.get(uv_fmt, 4)
            if v_num % 2 and uv_fmt == 0x69:
                p += 2
            uv_type, _, uv_fmt = struct.unpack_from("<H2B", payload, p); p += 4
        for _ in range(v_num):
            uvs.append(struct.unpack_from("<hh", payload, p)); p += 4
        uv_end = p
        while sub < total_sub - 1:                # skips to the next separator
            if payload[p:p + 4] == _SUBMESH_SEP:
                p += 4
                break
            p += 4
            if p > end:
                return None

    vcounter = len(verts)
    ts = payload[uv_end:end].find(VIF_STRIP_MARKER)
    if ts < 0:
        return None
    sp = uv_end + ts + 8 + 4                       # marker(8) + tag(4)
    idx = list(struct.unpack_from(f"<{tstrip_size}H", payload, sp))

    def gv(c):
        return ((c & 0x7FFF) // 4) - 1
    if not idx:
        return None
    # diff is computed over ALL indices (kicks AND restarts), like the stadium
    # decoder. Using only kicks gave off-by-1 errors in some parts (mixed-up
    # geometry).
    diff = max(gv(c) for c in idx) - vcounter + 1
    faces = []
    rev = True
    for i in range(2, len(idx)):
        c = idx[i]
        if (c & 0x8000) == 0:
            t1, t2, t3 = gv(idx[i]) - diff, gv(idx[i-1]) - diff, gv(idx[i-2]) - diff
            if t1 != t2 and t2 != t3 and t1 != t3 and all(0 <= t < vcounter for t in (t1, t2, t3)):
                faces.append((t3, t2, t1) if rev else (t1, t2, t3))
        rev = not rev
    return verts, uvs, faces


def read_model_parts(coord, payload, model_offset, dedup=False):
    """
    Reads the parts of a model WITHOUT merging them: returns
    (parts, skipped, total) where parts = [(verts_obj, uvs_obj, faces_local), ...].

    `dedup=True` skips parts whose raw GEOMETRY (int16 vertices) is the same
    as one already read — these are the "double-sided" panels that the PS2
    duplicates to draw both sides of the cloth. Useful for a cleaner .obj.
    """
    model = parse_model(payload, model_offset)
    parts = []
    seen = set()
    skipped = 0
    for part in model.parts:
        geom = read_part_geometry(payload, part)
        if geom is None:
            skipped += 1
            continue
        pverts, puvs, local_faces = geom
        if dedup:
            key = tuple(pverts)
            if key in seen:
                continue
            seen.add(key)
        verts = [coord.int16_to_obj_vertex(s0, s1, s2) for (s0, s1, s2) in pverts]
        uvs = [coord.int16_to_obj_uv(u, v) for (u, v) in puvs]
        parts.append((verts, uvs, list(local_faces)))
    return parts, skipped, len(model.parts)


def read_model_geometry(coord, payload, model_offset, dedup=False):
    """
    Reads ALL parts of a model (`MAGIC_MODEL` at `model_offset`) and returns
    the MERGED geometry in OBJ space: (verts, uvs, faces, skipped, nparts).

    Core shared by face/trophy (export), stadiums and kits. Each part goes
    through the universal reader `read_part_geometry`; `coord` (from the
    AssetProfile) applies scale/axes. `dedup` removes double-sided panels
    (see read_model_parts).
    """
    parts, skipped, total = read_model_parts(coord, payload, model_offset, dedup=dedup)
    verts, uvs, faces = [], [], []
    vcount = 0
    for pverts, puvs, local_faces in parts:
        verts.extend(pverts)
        uvs.extend(puvs)
        faces.extend((a + vcount, b + vcount, c + vcount) for (a, b, c) in local_faces)
        vcount += len(pverts)
    return verts, uvs, faces, skipped, total
