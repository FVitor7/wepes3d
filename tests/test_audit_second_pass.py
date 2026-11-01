"""
Second, adversarial pass of the audit (docs/audit/2026-11-second-pass-review.md).

Two kinds of tests:

- PASSING tests are attacks on conclusions of the first audit that did NOT
  break them (property tests on random meshes, an independent decoder, the
  game's own normals). They protect what is right.
- `known_bug(...)` tests (strict xfail) reproduce the NEW findings (B-xx),
  plus one property-level proof of finding A-06.
"""

import random
import struct
import zlib
from collections import Counter

import pytest

from wepes3d import decompress_bin, import_face, parse_model, trophy_section_offsets
from wepes3d.shared.io import load_blocks, model_offsets
from wepes3d.shared.model.reader import read_part_geometry
from wepes3d.shared.model.strip import decode_strip
from wepes3d.shared.model.strip_connected import (
    build_connected_strips, connected_strips_to_indices, orient_coherent,
)


def known_bug(finding, reason):
    return pytest.mark.xfail(strict=True, raises=AssertionError,
                             reason=f"{finding}: {reason}")


# ---------------------------------------------------------------------------
# An independent decoder: strip index -> vertex by the exact VU address
# ---------------------------------------------------------------------------

def _address_decoder(payload, part):
    """Reads the submesh tags (IMMED = VU address of vertex 0, stride 4) and
    maps every strip index to a global vertex. Returns (vertex_count,
    [(abs_index, (a, b, c), normals)]) where (a, b, c) is in window order."""
    off, pis = part.offset_in_payload, part.part_info_start_raw
    total_sub = struct.unpack_from("<I", payload, off + pis + 44)[0]
    p = off + pis + 56 + 36 * total_sub + 4
    sizes = {0x69: 6, 0x68: 12, 0x65: 4, 0x6E: 4, 0x6A: 3, 0x6C: 16, 0x6D: 8}

    def skip(pos):
        """Skips one UNPACK (tag + data, padded to 4 bytes)."""
        _, num, cmd = struct.unpack_from("<HBB", payload, pos)
        return pos + 4 + (sizes[cmd & 0x6F] * num + 3) // 4 * 4

    addr, normals, base = {}, [], 0
    for k in range(total_sub):
        imm, num, cmd = struct.unpack_from("<HBB", payload, p)
        for n in range(num):
            addr[(imm & 0x3FF) + 4 * n] = base + n
        p = skip(p)                                   # vertices
        _, _, ncmd = struct.unpack_from("<HBB", payload, p)
        fmt, nsize = ("<hhh", 6) if ncmd & 0x6F == 0x69 else ("<iii", 12)
        normals += [struct.unpack_from(fmt, payload, p + 4 + nsize * n) for n in range(num)]
        p = skip(p)                                   # normals
        while (struct.unpack_from("<H", payload, p)[0] & 0x3FF) - (imm & 0x3FF) != 3:
            p = skip(p)                               # extra block (colour / 2nd UV)
        p = skip(p)                                   # UVs
        base += num
        if k < total_sub - 1:
            p = payload.find(bytes([4, 1, 0, 1]), p, off + part.size) + 4
    marker = payload.find(bytes([1, 0, 0, 5, 1, 1, 0, 1]), p, off + part.size)
    _, sn, _ = struct.unpack_from("<HBB", payload, marker + 8)
    raw = struct.unpack_from(f"<{sn * 4}H", payload, marker + 12)
    fired = []
    for i in range(2, len(raw)):
        if raw[i] & 0x8000:
            continue
        t = tuple(addr.get(raw[k] & 0x7FFF) for k in (i - 2, i - 1, i))
        if None not in t and len(set(t)) == 3:
            fired.append((i, t))
    return base, fired, normals


def _all_seed_models(trophy_bin, kit_bin, stadium_str, adboard_bin, face_bin):
    payload, _, _ = decompress_bin(face_bin)
    yield "face", payload, parse_model(payload)
    payload, _, _ = decompress_bin(trophy_bin)
    for k, off in enumerate(trophy_section_offsets(payload)):
        yield f"trophy sec{k}", payload, parse_model(payload, off)
    for path in (kit_bin, stadium_str, adboard_bin):
        for payload in load_blocks(path):
            for off in model_offsets(payload):
                yield path, payload, parse_model(payload, off)


# ---------------------------------------------------------------------------
# Attacks that did not break the first audit (these PASS)
# ---------------------------------------------------------------------------

def test_reader_matches_an_address_based_decoder(trophy_bin, kit_bin, stadium_str,
                                                 adboard_bin, face_bin):
    """The universal reader guesses the base address; the decoder above
    reads it. They must give the same triangles on every real seed part."""
    checked = 0
    for label, payload, model in _all_seed_models(trophy_bin, kit_bin, stadium_str,
                                                  adboard_bin, face_bin):
        for part in model.parts:
            vc, fired, _ = _address_decoder(payload, part)
            verts, _, faces = read_part_geometry(payload, part)
            assert len(verts) == vc, label
            assert Counter(frozenset(t) for t in faces) == \
                Counter(frozenset(t) for _, t in fired), label
            checked += 1
    assert checked > 300


def _parity_agreement(payload, model, reset_per_strip):
    """Share of fired triangles whose winding agrees with the game's normals
    (stored normal = -geometric normal) for a given parity model."""
    agree = total = 0
    for part in model.parts:
        if part.vertex_count == 0:
            continue
        _, fired, normals = _address_decoder(payload, part)
        verts = part.vertices
        raw = part.strip_indices
        seg = 0
        starts = {}
        for i in range(len(raw)):
            if i and raw[i] < 0 and raw[i - 1] < 0:
                seg = i - 1
            starts[i] = seg
        for i, (a, b, c) in fired:
            parity = (i - starts[i]) % 2 if reset_per_strip else i % 2
            if parity:
                b, c = c, b
            e1 = [verts[b][k] - verts[a][k] for k in range(3)]
            e2 = [verts[c][k] - verts[a][k] for k in range(3)]
            g = (e1[1] * e2[2] - e1[2] * e2[1], e1[2] * e2[0] - e1[0] * e2[2],
                 e1[0] * e2[1] - e1[1] * e2[0])
            n = [sum(normals[v][k] for v in (a, b, c)) for k in range(3)]
            agree += sum(x * y for x, y in zip(g, n)) < 0
            total += 1
    return agree / total


@pytest.mark.parametrize("which", ["trophy", "kit"])
def test_game_strips_use_an_absolute_parity(which, trophy_bin, kit_bin):
    """The game's own normals decide the winding model (finding A-06): the
    absolute parity fits; 'reset at every restart' (the encoders) does not."""
    if which == "trophy":
        payload, _, _ = decompress_bin(trophy_bin)
        model = parse_model(payload, trophy_section_offsets(payload)[0])
    else:
        payload = load_blocks(kit_bin)[0]
        model = parse_model(payload, model_offsets(payload)[0])
    assert _parity_agreement(payload, model, reset_per_strip=False) > 0.99
    assert _parity_agreement(payload, model, reset_per_strip=True) < 0.75


def _random_meshes(seed=7, count=150):
    rnd = random.Random(seed)
    for _ in range(count):
        n = rnd.randint(2, 8)
        tris = []
        for j in range(n - 1):
            for i in range(n - 1):
                a = j * n + i
                tris += [(a, a + 1, a + n + 1), (a, a + n + 1, a + n)]
        rnd.shuffle(tris)
        kind = rnd.choice(["grid", "flipped", "duplicates", "fan", "soup"])
        if kind == "flipped":
            tris = [t if rnd.random() < 0.5 else (t[0], t[2], t[1]) for t in tris]
        elif kind == "duplicates":
            tris += tris[:3] + [(b, a, c) for a, b, c in tris[3:5]]
        elif kind == "fan":
            tris = [(0, 1, k) for k in range(2, rnd.randint(4, 9))]
        elif kind == "soup":
            tris = [tuple(rnd.sample(range(20), 3)) for _ in range(rnd.randint(1, 30))]
        yield tris


def test_connected_encoder_keeps_every_triangle():
    """No triangle is lost or duplicated, even with duplicates, non-manifold
    fans and random winding (checked with the decode_strip oracle)."""
    for tris in _random_meshes():
        strips = build_connected_strips(orient_coherent(tris))
        indices = connected_strips_to_indices(strips)
        decoded = decode_strip(indices, max(max(t) for t in tris) + 1)
        assert Counter(frozenset(t) for t in decoded) == Counter(frozenset(t) for t in tris)


def test_model_texture_table_is_inside_the_model_header(trophy_bin, kit_bin, stadium_str,
                                                        adboard_bin, face_bin):
    """model+0x3C (with the count at +0x38) points inside the model header,
    so a resize does not have to move it. +0x28/+0x30/+0x34 are always 0."""
    for _, payload, model in _all_seed_models(trophy_bin, kit_bin, stadium_str,
                                              adboard_bin, face_bin):
        mo = model.offset_file_1
        w28, _, w30, w34, _, w3c = struct.unpack_from("<6I", payload, mo + 0x28)
        assert (w28, w30, w34) == (0, 0, 0)
        assert w3c < len(model.pre_parts_bytes) - mo


# ---------------------------------------------------------------------------
# New findings of the second pass
# ---------------------------------------------------------------------------

def _hardware_like_decode(indices):
    """Absolute parity, every non-ADC index fires (what the export reader does)."""
    raw = [c & 0xFFFF for c in indices]
    out = []
    for i in range(2, len(raw)):
        if raw[i] & 0x8000:
            continue
        t = [((raw[k] & 0x7FFF) // 4) - 1 for k in (i - 2, i - 1, i)]
        if len(set(t)) == 3 and min(t) >= 0:
            out.append(tuple(t) if i % 2 == 0 else (t[0], t[2], t[1]))
    return out


def _rot(t):
    a, b, c = t
    return min((a, b, c), (b, c, a), (c, a, b))


@known_bug("A-06", "strips that start at an odd index are drawn with every triangle reversed")
def test_a06_connected_strips_keep_the_winding_under_absolute_parity():
    for tris in _random_meshes(seed=11, count=60):
        oriented = orient_coherent(tris)
        indices = connected_strips_to_indices(build_connected_strips(oriented))
        assert Counter(_rot(t) for t in _hardware_like_decode(indices)) == \
            Counter(_rot(t) for t in oriented if len(set(t)) == 3)


@known_bug("B-02", "decode_strip skips the [pos, neg, pos] window, which the GS fires")
def test_b02_zero_diff_oracle_fires_on_a_single_adc():
    def neg(v):
        return ((v + 1) * 4 | 0x8000) - 0x10000

    def pos(v):
        return (v + 1) * 4
    # n n p | n p : one ADC between two kicks. The GS draws (2, 3, 4) too.
    tris = decode_strip([neg(0), neg(1), pos(2), neg(3), pos(4)], vc=5)
    assert {frozenset(t) for t in tris} == {frozenset((0, 1, 2)), frozenset((2, 3, 4))}


@known_bug("B-01", "the partition ignores the texture of each template part")
def test_b01_multi_texture_template_is_not_filled_blindly(face_bin, tmp_path, write_obj):
    """All real face/hair templates (not face.bin) use 3-4 textures per model
    (tex_id at part+0x34). A single-material .obj spread over those parts is
    drawn with the wrong textures. The import must refuse or route by
    material — here we only ask it to say so."""
    payload, header, _ = decompress_bin(face_bin)
    data = bytearray(payload)
    for part, tex in zip(parse_model(payload).parts, (1, 3, 2, 0, 0, 0, 0, 0)):
        struct.pack_into("<I", data, part.offset_in_payload + 0x34, tex)
    blob = zlib.compress(bytes(data), 9)
    hdr = bytearray(header)
    struct.pack_into("<II", hdr, 4, len(blob), len(data))
    template = tmp_path / "multi_texture.bin"
    template.write_bytes(bytes(hdr) + blob)

    verts, uvs, faces = [], [], []
    for j in range(12):
        for i in range(12):
            verts.append((float(i), float(j), 0.0))
            uvs.append((i / 11, j / 11))
    for j in range(11):
        for i in range(11):
            a = j * 12 + i
            faces += [(a, a + 1, a + 13), (a, a + 13, a + 12)]
    obj = write_obj(verts, uvs, faces, name="one_material.obj")
    try:
        import_face(str(template), obj, str(tmp_path / "out.bin"), allow_recount=True)
        refused = False
    except (SystemExit, ValueError):
        refused = True
    assert refused
