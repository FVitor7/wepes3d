"""
Reproductions of the engineering audit (docs/audit/2026-11-engineering-audit.md).

Each test checks the CORRECT behaviour. Tests that fail today are marked
`known_bug(...)` = `xfail(strict=True, raises=AssertionError)`:

- today they fail on purpose (pytest shows "x"), so CI stays green;
- when a fix lands, the test passes, pytest reports XPASS as a failure, and you
  remove the marker.

The ID in each name (a01, a02, ...) is the finding ID in the report. These
tests only use files from tests/seed/ and small synthetic meshes.
"""

import math
import struct

import pytest

from wepes3d import (
    decompress_bin, export_face, export_pc, export_trophy, import_face,
    import_trophy, locate_model, parse_model, parse_obj, trophy_section_offsets,
)
from wepes3d.shared.model.rebuilder import rebuild_part


def known_bug(finding, reason):
    return pytest.mark.xfail(strict=True, raises=AssertionError,
                             reason=f"{finding}: {reason}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sphere(write_obj, rings=12, segments=24, name="sphere.obj"):
    """A closed UV sphere with OUTWARD (counter-clockwise) triangles."""
    verts, uvs, faces = [], [], []
    for i in range(rings + 1):
        th = math.pi * i / rings
        for j in range(segments + 1):
            ph = 2 * math.pi * j / segments
            verts.append((math.sin(th) * math.cos(ph), math.cos(th),
                          math.sin(th) * math.sin(ph)))
            uvs.append((j / segments, 1 - i / rings))
    for i in range(rings):
        for j in range(segments):
            a = i * (segments + 1) + j
            faces += [(a, a + segments + 2, a + 1), (a, a + segments + 1, a + segments + 2)]
    faces = [t for t in faces if len({verts[k] for k in t}) == 3]
    return write_obj(verts, uvs, faces, name=name)


def _key(obj, tri):
    return tuple(tuple(round(c, 4) for c in obj.vertices[i]) for i in tri)


def _rot(t):
    a, b, c = t
    return min((a, b, c), (b, c, a), (c, a, b))


def _winding_flips(src_obj, new_obj):
    """Triangles of new_obj whose winding is the opposite of src_obj
    (matched by vertex POSITION, because indices change after a rebuild)."""
    a, b = parse_obj(src_obj), parse_obj(new_obj)
    want = {frozenset(_key(a, t)): _rot(_key(a, t)) for t in a.faces}
    return sum(1 for t in b.faces
               if frozenset(_key(b, t)) in want
               and want[frozenset(_key(b, t))] != _rot(_key(b, t)))


def _colour_program(payload, part):
    """The trophy 'colour' VIF program between the UVs and the strip marker:
    STMASK, UNPACK S-16 masked (one colour address per vertex),
    STCYCL 1/1, UNPACK V4-8 (the colour qword). Returns
    (s16_num, set_of_addresses, colour_address)."""
    gap = part.pad_after_uvs
    s16 = colour = None
    i = 0
    while i + 4 <= len(gap):
        imm, num, cmd = struct.unpack_from("<HBB", gap, i)
        i += 4
        cmd &= 0x7F
        if cmd == 0x20:                         # STMASK + 1 data word
            i += 4
        elif cmd == 0x71:                       # UNPACK S-16, masked
            s16 = (num, set(struct.unpack_from(f"<{num}H", gap, i)))
            i += (2 * num + 3) & ~3
        elif cmd == 0x6E:                       # UNPACK V4-8
            colour = imm & 0x3FF
            i += 4 * num
    return s16[0], s16[1], colour


# ---------------------------------------------------------------------------
# A-01 — trophy sec0: the colour program is not updated
# ---------------------------------------------------------------------------

def test_a01_original_trophy_parts_follow_the_colour_layout(trophy_bin):
    """The invariant of every real sec0 part (checked on 6 trophies)."""
    payload, _, _ = decompress_bin(trophy_bin)
    model = parse_model(payload, trophy_section_offsets(payload)[0])
    for part in model.parts:
        vc = part.vertex_count
        num, addrs, colour = _colour_program(payload, part)
        ss = struct.unpack_from("<H", part.header_bytes, 0xC8)[0]
        assert (num, addrs, colour, ss) == (vc, {4 * vc + 8}, 4 * vc + 8, 4 * vc + 9)


@known_bug("A-01", "the colour program keeps the template vc and addresses")
def test_a01_rebuilt_trophy_parts_keep_the_colour_layout(trophy_bin, write_obj, tmp_path):
    obj = _sphere(write_obj)
    out = str(tmp_path / "out.bin")
    import_trophy(trophy_bin, obj, out, section=0, allow_recount=True,
                  recalculate_normals=True, auto_fit=True)
    payload, _, _ = decompress_bin(out)
    model = parse_model(payload, trophy_section_offsets(payload)[0])
    for part in model.parts:
        vc = part.vertex_count
        num, addrs, colour = _colour_program(payload, part)
        ss = struct.unpack_from("<H", part.header_bytes, 0xC8)[0]
        assert (num, addrs, colour, ss) == (vc, {4 * vc + 8}, 4 * vc + 8, 4 * vc + 9)


# ---------------------------------------------------------------------------
# A-02 — sections with V3-32 vertices are rewritten even without edits
# ---------------------------------------------------------------------------

@known_bug("A-02", "parse_model reads V3-32 vertices as V3-16, so every part is rebuilt")
def test_a02_unedited_roundtrip_of_a_v3_32_section_is_zero_diff(trophy_bin, tmp_path):
    obj = str(tmp_path / "sec4.obj")
    out = str(tmp_path / "rt.bin")
    export_trophy(trophy_bin, obj, section=4)
    import_trophy(trophy_bin, obj, out, section=4)
    assert decompress_bin(out)[0] == decompress_bin(trophy_bin)[0]


# ---------------------------------------------------------------------------
# A-04 — parts with 0 vertices (UNPACK NUM=0 means 256 for the VIF)
# ---------------------------------------------------------------------------

@known_bug("A-04", "a small mesh leaves parts with vc=0 and UNPACK NUM=0")
def test_a04_small_mesh_creates_no_empty_part(face_bin, write_obj, tmp_path):
    verts = [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (1.0, 1.0, 0.0), (0.0, 1.0, 0.0)]
    uvs = [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
    obj = write_obj(verts, uvs, [(0, 1, 2), (0, 2, 3)], name="quad.obj")
    out = str(tmp_path / "out.bin")
    import_face(face_bin, obj, out, allow_recount=True)
    payload, _, _ = decompress_bin(out)
    for part in parse_model(payload).parts:
        assert part.vertex_count > 0
        assert part.pre_normals_tag[2] != 0 and part.pre_uvs_tag[2] != 0


# ---------------------------------------------------------------------------
# A-05 — the strip address has 10 bits
# ---------------------------------------------------------------------------

@known_bug("A-05", "vc=254 gives ss=1024, written as ADDR 0 in the strip tag")
def test_a05_strip_address_fits_or_the_part_is_refused(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    part = parse_model(payload).parts[0]
    vc = 254
    tris = [(i, i + 1, i + 2) for i in range(0, vc - 2, 3)]
    try:
        new = rebuild_part(part, [(0, 0, 0)] * vc, [(0, 0, 32767)] * vc,
                           [(0, 0)] * vc, tris, new_count=vc, strip_mode="list")
    except ValueError:
        return                                   # refused: correct
    imm = struct.unpack_from("<H", new.pre_strip_bytes, len(new.pre_strip_bytes) - 4)[0]
    assert imm & 0x3FF == 4 * vc + 8


# ---------------------------------------------------------------------------
# A-06 — re-encoded strips lose the winding (absolute parity)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("mode", ["connected", "list"])
@known_bug("A-06", "the encoders reset the parity per strip; the decoder does not")
def test_a06_reencoded_parts_keep_the_winding(face_bin, face_obj, tmp_path, mode):
    out = str(tmp_path / "out.bin")
    again = str(tmp_path / "again.obj")
    import_face(face_bin, face_obj, out, preserve_strips=False, strip_mode=mode)
    export_face(out, again)
    assert _winding_flips(face_obj, again) == 0


# ---------------------------------------------------------------------------
# A-08 — trophy normals: length 4096 and the sign of the template
# ---------------------------------------------------------------------------

@known_bug("A-08", "trophy normals are written with length 32767 and the opposite sign")
def test_a08_recalculated_trophy_normals_match_the_original(trophy_bin, tmp_path):
    obj = str(tmp_path / "sec0.obj")
    out = str(tmp_path / "out.bin")
    export_trophy(trophy_bin, obj, section=0)
    import_trophy(trophy_bin, obj, out, section=0, recalculate_normals=True)
    p0, _, _ = decompress_bin(trophy_bin)
    p1, _, _ = decompress_bin(out)
    m0 = parse_model(p0, trophy_section_offsets(p0)[0])
    m1 = parse_model(p1, trophy_section_offsets(p1)[0])
    cos, lengths = [], []
    for a, b in zip(m0.parts, m1.parts):
        for n0, n1 in zip(a.normals, b.normals):
            l0, l1 = math.hypot(*n0), math.hypot(*n1)
            lengths.append(l1)
            cos.append(sum(x * y for x, y in zip(n0, n1)) / (l0 * l1))
    cos.sort()
    assert cos[len(cos) // 2] > 0.9
    assert abs(sorted(lengths)[len(lengths) // 2] - 4096) < 8


# ---------------------------------------------------------------------------
# A-10 — the export reader assumes the last vertex of a part is used
# ---------------------------------------------------------------------------

@known_bug("A-10", "the 'diff' heuristic shifts every index when the last vertex is unused")
def test_a10_export_of_a_part_whose_last_vertex_is_unused(face_bin, face_obj, write_obj, tmp_path):
    src = parse_obj(face_obj)
    keep = [t for t in src.faces if 86 not in t]          # v86 = last vertex of part 0
    obj = write_obj(src.vertices, src.uvs, keep, name="no_v86.obj")
    out = str(tmp_path / "out.bin")
    again = str(tmp_path / "again.obj")
    import_face(face_bin, obj, out)
    export_face(out, again)
    new = parse_obj(again)
    imported = {frozenset(_key(src, t)) for t in keep}
    exported = {frozenset(_key(new, t)) for t in new.faces}
    assert exported == imported


# ---------------------------------------------------------------------------
# A-11 — PES6 PC export: strips are decoded without the winding alternation
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("seed", ["pc_trophy_str", "pc_face_bin"])
@known_bug("A-11", "every PC strip triangle is written as (c, b, a)")
def test_a11_pc_export_has_a_coherent_winding(request, seed, tmp_path):
    obj = str(tmp_path / "pc.obj")
    export_pc(request.getfixturevalue(seed), obj, model=0)
    mesh = parse_obj(obj)
    directed = {}
    for t in mesh.faces:
        p = _key(mesh, t)
        for k in range(3):
            directed.setdefault(frozenset((p[k], p[(k + 1) % 3])), []).append((p[k], p[(k + 1) % 3]))
    pairs = [e for e in directed.values() if len(e) == 2]
    coherent = sum(1 for a, b in pairs if a != b)
    assert coherent / len(pairs) > 0.75


# ---------------------------------------------------------------------------
# A-12 / A-20 — .obj parser
# ---------------------------------------------------------------------------

@known_bug("A-12", "negative (relative) indices are read as wrong vertices")
def test_a12_negative_obj_indices(tmp_path):
    p = tmp_path / "neg.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nv 9 9 9\n"
                 "vt 0 0\nvt 1 0\nvt 0 1\nvt 1 1\n"
                 "f -3/-3 -2/-2 -1/-1\n")
    assert parse_obj(str(p)).faces == [(1, 2, 3)]


@known_bug("A-20", "'vt u' (one component) is valid OBJ but raises IndexError")
def test_a20_vt_with_one_component(tmp_path):
    p = tmp_path / "vt1.obj"
    p.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0.5\nvt 0.2 0.3\nvt 1 1\nf 1/1 2/2 3/3\n")
    try:
        mesh = parse_obj(str(p))
    except IndexError:
        mesh = None
    assert mesh is not None and mesh.uvs[0][0] == 0.5


# ---------------------------------------------------------------------------
# A-13 — --use-groups with a normal Blender export
# ---------------------------------------------------------------------------

@known_bug("A-13", "the implicit 'default' group is counted: 8 objects = 9 groups")
def test_a13_use_groups_with_one_object_per_part(face_bin, write_obj, tmp_path):
    verts, uvs, faces, groups = [], [], [], []
    for k in range(8):                       # 8 objects, each with 'o' (Blender style)
        b = len(verts)
        verts += [(4.0 * k, 0.0, 0.0), (4.0 * k + 1, 0.0, 0.0),
                  (4.0 * k + 1, 1.0, 0.0), (4.0 * k, 1.0, 0.0)]
        uvs += [(0.0, 0.0), (1.0, 0.0), (1.0, 1.0), (0.0, 1.0)]
        faces += [(b, b + 1, b + 2), (b, b + 2, b + 3)]
        groups += [f"obj{k}"] * 2
    obj = write_obj(verts, uvs, faces, groups=groups, name="blender8.obj")
    try:
        import_face(face_bin, obj, str(tmp_path / "out.bin"),
                    allow_recount=True, use_groups=True)
        ok = True
    except SystemExit:
        ok = False
    assert ok


# ---------------------------------------------------------------------------
# A-14 — normals at part seams
# ---------------------------------------------------------------------------

@known_bug("A-14", "normals are averaged per part, so copies of a point get different normals")
def test_a14_copies_of_the_same_point_get_the_same_normal(trophy_bin, write_obj, tmp_path):
    obj = _sphere(write_obj, rings=16, segments=32)
    out = str(tmp_path / "out.bin")
    import_trophy(trophy_bin, obj, out, section=0, allow_recount=True,
                  recalculate_normals=True, auto_fit=True, max_verts_per_part=120)
    payload, _, _ = decompress_bin(out)
    seen = {}
    for part in parse_model(payload, trophy_section_offsets(payload)[0]).parts:
        for v, n in zip(part.vertices, part.normals):
            seen.setdefault(v, set()).add(n)
    worst = 0.0
    for normals in seen.values():
        ns = [tuple(c / math.hypot(*n) for c in n) for n in normals]
        for a in ns:
            for b in ns:
                cos = max(-1.0, min(1.0, sum(x * y for x, y in zip(a, b))))
                worst = max(worst, math.degrees(math.acos(cos)))
    assert worst < 1.0


# ---------------------------------------------------------------------------
# A-16 — zero-diff detection ignores the winding
# ---------------------------------------------------------------------------

@known_bug("A-16", "triangles are compared as frozensets, so a flip is not seen")
def test_a16_a_winding_edit_is_not_discarded(face_bin, face_obj, write_obj, tmp_path):
    src = parse_obj(face_obj)
    flipped = [(a, c, b) if max(a, b, c) < 87 else (a, b, c) for a, b, c in src.faces]
    obj = write_obj(src.vertices, src.uvs, flipped, name="flipped.obj")
    out = str(tmp_path / "out.bin")
    import_face(face_bin, obj, out)
    assert decompress_bin(out)[0] != decompress_bin(face_bin)[0]


# ---------------------------------------------------------------------------
# A-25 — truncated .bin files load without an error
# ---------------------------------------------------------------------------

@known_bug("A-25", "a truncated zlib stream gives a partial payload, with no error")
def test_a25_truncated_bin_is_rejected(face_bin, tmp_path):
    data = open(face_bin, "rb").read()
    cut = tmp_path / "cut.bin"
    cut.write_bytes(data[: len(data) // 2])
    try:
        payload, header, _ = decompress_bin(str(cut))
    except Exception:
        return                                   # rejected: correct
    assert len(payload) == struct.unpack_from("<I", header, 8)[0]


# ---------------------------------------------------------------------------
# Checks that PASS: the parts of the rebuilder that are right
# ---------------------------------------------------------------------------

def test_face_recount_keeps_the_derived_fields_consistent(face_bin, write_obj, tmp_path):
    obj = _sphere(write_obj)
    out = str(tmp_path / "out.bin")
    import_face(face_bin, obj, out, allow_recount=True, recalculate_normals=True, auto_fit=True)
    payload, _, _ = decompress_bin(out)
    model = parse_model(payload)
    for part in model.parts:
        h = part.header_bytes
        vc, pis = part.vertex_count, part.part_info_start_raw
        sn = len(part.strip_indices) // 4
        imm = struct.unpack_from("<H", part.pre_strip_bytes, len(part.pre_strip_bytes) - 4)[0]
        assert struct.unpack_from("<I", h, 0x0C)[0] == (part.size - pis) // 16
        assert struct.unpack_from("<I", h, 0x10)[0] == sn * 4
        assert struct.unpack_from("<I", h, 0x2C)[0] == 4 * vc + 4
        assert struct.unpack_from("<H", h, 0xC8)[0] == imm & 0x3FF
        assert struct.unpack_from("<H", h, 0xCA)[0] == (imm & 0x3FF) + sn
    end = len(model.pre_parts_bytes) + sum(p.size for p in model.parts)
    assert struct.unpack_from("<I", payload, 0x0C)[0] == end
    assert struct.unpack_from("<I", payload, locate_model(payload) + 0x2C)[0] == end - 0x10


def test_trophy_recount_of_a_simple_section_keeps_the_rest_intact(trophy_bin, write_obj, tmp_path):
    obj = _sphere(write_obj)
    out = str(tmp_path / "out.bin")
    import_trophy(trophy_bin, obj, out, section=1, allow_recount=True, auto_fit=True,
                  max_verts_per_part=100)
    p0, _, _ = decompress_bin(trophy_bin)
    p1, _, _ = decompress_bin(out)
    s0, s1 = trophy_section_offsets(p0), trophy_section_offsets(p1)

    def section_bytes(payload, off):
        model = parse_model(payload, off)
        return payload[off:len(model.pre_parts_bytes) + sum(p.size for p in model.parts)]

    for k in range(len(s0)):
        if k != 1:
            assert section_bytes(p0, s0[k]) == section_bytes(p1, s1[k])
    t0 = struct.unpack_from("<I", p0, 0x0C)[0]
    t1 = struct.unpack_from("<I", p1, 0x0C)[0]
    assert p0[t0:] == p1[t1:]
