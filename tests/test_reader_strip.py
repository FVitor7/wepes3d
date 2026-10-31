"""Leitor universal de geometria + codificação/decodificação do strip."""

import pytest

from wepes3d import decompress_bin, parse_model
from wepes3d.shared.model.reader import (
    read_part_geometry, read_model_parts, read_model_geometry,
)
from wepes3d.shared.model.strip import (
    triangles_to_pes_strip, decode_strip, align_strip_to_v4, pad_to_length,
    pack_strip_indices, _encode_vertex_kick, STRIP_PADDING_VALUE,
)
from wepes3d.shared.model.strip_connected import (
    build_connected_strips, connected_strips_to_indices, orient_for_front,
)
from wepes3d.adapters.pesweps2.faces.profile import COORD as FACE


# ---------------------------------------------------------------------------
# read_part_geometry / read_model_*
# ---------------------------------------------------------------------------

def test_read_part_geometry_face(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    m = parse_model(payload)
    verts, uvs, faces = read_part_geometry(payload, m.parts[0])
    assert len(verts) == 87
    assert len(uvs) == 87
    assert len(faces) > 0
    # índices das faces ficam dentro do range de vértices da part
    for tri in faces:
        assert all(0 <= i < 87 for i in tri)


def test_read_model_parts_and_merge(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    off = parse_model(payload).offset_file_1
    parts, skipped, total = read_model_parts(FACE, payload, off)
    assert total == 8 and skipped == 0 and len(parts) == 8
    verts, uvs, faces, skipped2, nparts = read_model_geometry(FACE, payload, off)
    assert len(verts) == 696
    assert len(faces) == 984


def test_read_model_parts_dedup_is_subset(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    off = parse_model(payload).offset_file_1
    full, _, _ = read_model_parts(FACE, payload, off)
    dedup, _, _ = read_model_parts(FACE, payload, off, dedup=True)
    assert len(dedup) <= len(full)


# ---------------------------------------------------------------------------
# strip (triangle list)
# ---------------------------------------------------------------------------

def test_triangle_list_roundtrip():
    tris = [(0, 1, 2), (2, 3, 4), (1, 4, 5)]
    indices = triangles_to_pes_strip(tris)
    decoded = decode_strip(indices, vc=6)
    assert {frozenset(t) for t in decoded} == {frozenset(t) for t in tris}


def test_decode_strip_case2_neg_pos_pos():
    # [neg(0), kick(1), kick(2)] -> case 2 -> triângulo (0,1,2)
    indices = [-32764, 8, 12]
    assert decode_strip(indices, vc=10) == [(0, 1, 2)]


def test_decode_strip_case3_pos_pos_pos():
    # [kick(0), kick(1), kick(2)] -> case 3 -> triângulo (0,1,2)
    indices = [4, 8, 12]
    assert decode_strip(indices, vc=10) == [(0, 1, 2)]


def test_decode_strip_skips_degenerate_triangle():
    # [kick(0), kick(0), kick(1)] -> a==b -> triângulo degenerado é descartado
    assert decode_strip([4, 4, 8], vc=10) == []


def test_decode_strip_skips_out_of_range():
    # índice aponta para vértice >= vc -> inválido -> descartado
    assert decode_strip([4, 8, 4000], vc=3) == []


def test_decode_strip_case1_degenerate():
    # [neg(0), neg(0), kick(1)] -> caso 1 com a==b -> descartado
    assert decode_strip([-32764, -32764, 8], vc=10) == []


def test_decode_strip_case2_degenerate():
    # [neg(0), kick(2), kick(2)] -> caso 2 com b==c -> descartado
    assert decode_strip([-32764, 12, 12], vc=10) == []


def test_decode_strip_degenerate_mixed_signs():
    # [neg(0), kick(0), kick(1)] -> a != b só pelo sinal, mas decodifica em
    # (0, 0, 1): degenerado -> descartado, como no leitor do export. Antes,
    # esse triângulo fantasma fazia o passthrough recodificar parts intactas.
    assert decode_strip([-32764, 4, 8], vc=10) == []


def test_align_strip_to_v4():
    assert len(align_strip_to_v4([1, 2, 3])) == 4          # padding até múltiplo de 4
    assert align_strip_to_v4([1, 2, 3, 4]) == [1, 2, 3, 4]  # já alinhado
    assert align_strip_to_v4([1, 2, 3])[-1] == STRIP_PADDING_VALUE


def test_pad_to_length():
    assert pad_to_length([1, 2], 5) == [1, 2, STRIP_PADDING_VALUE, STRIP_PADDING_VALUE,
                                        STRIP_PADDING_VALUE]
    assert pad_to_length([1, 2, 3], 2) == [1, 2, 3]        # já maior: não corta


def test_pack_strip_indices_length():
    assert len(pack_strip_indices([1, 2, 3, 4])) == 8      # 4 int16 = 8 bytes


def test_encode_vertex_kick_overflow():
    with pytest.raises(ValueError):
        _encode_vertex_kick(99999)                          # excede 0x7FFF


# ---------------------------------------------------------------------------
# strip conectado
# ---------------------------------------------------------------------------

def test_connected_strip_preserves_triangle_set():
    tris = [(0, 1, 2), (1, 2, 3), (2, 3, 4), (3, 4, 5)]
    indices = connected_strips_to_indices(build_connected_strips(tris))
    decoded = decode_strip(indices, vc=6)
    # o strip conectado deve recuperar exatamente o mesmo CONJUNTO de triângulos
    assert {frozenset(t) for t in decoded} == {frozenset(t) for t in tris}


def test_orient_for_front_keeps_count():
    tris = [(0, 1, 2), (0, 2, 3)]
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    normals = [(0, 0, 1)] * 4
    oriented = orient_for_front(tris, verts, normals)
    assert len(oriented) == len(tris)
