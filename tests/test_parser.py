"""Parser do payload: detecção, navegação, parse e serialização (lossless)."""

import struct

import pytest

from wepes3d import decompress_bin, parse_model
from wepes3d.shared.model.parser import (
    detect_asset_type, locate_model, write_model, write_part,
    clone_part_structure,
)


def _fake_payload(magic_at_8: bytes) -> bytes:
    """payload mínimo: offset_file_1 = 0x20 e um magic arbitrário lá."""
    buf = bytearray(64)
    struct.pack_into("<I", buf, 8, 0x20)
    buf[0x20:0x24] = magic_at_8
    return bytes(buf)


def test_detect_face(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    assert detect_asset_type(payload) == "face"


def test_detect_trophy(trophy_bin):
    payload, _, _ = decompress_bin(trophy_bin)
    assert detect_asset_type(payload) == "trophy"


def test_detect_unknown_raises():
    with pytest.raises(ValueError):
        detect_asset_type(_fake_payload(b"\xAA\xBB\xCC\xDD"))


def test_locate_model_face(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    assert locate_model(payload) == 0x10            # face: modelo direto em payload[8]


def test_locate_model_trophy(trophy_bin):
    payload, _, _ = decompress_bin(trophy_bin)
    off = locate_model(payload)
    assert payload[off:off+4] == b"\x03\x00\xFF\xFF"


def test_locate_model_unknown_raises():
    with pytest.raises(ValueError):
        locate_model(_fake_payload(b"\xAA\xBB\xCC\xDD"))


def test_parse_face_structure(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    m = parse_model(payload)
    assert len(m.parts) == 8
    assert all(p.vertex_count == 87 for p in m.parts)
    assert m.offset_file_1 == 0x10
    p0 = m.parts[0]
    assert p0.size == 2048
    assert len(p0.vertices) == 87
    assert len(p0.uvs) == 87
    assert p0.vertices[0] == (293, -1110, 0)        # ordem armazenada (y, z, x)


def test_write_model_roundtrip_identical(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    m = parse_model(payload)
    assert write_model(m) == payload                # serializer é lossless


def test_write_part_length(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    m = parse_model(payload)
    data = write_part(m.parts[0])
    assert len(data) == m.parts[0].size


def test_clone_part_structure(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    m = parse_model(payload)
    clone = clone_part_structure(m.parts[0])
    assert clone.vertices == []                     # shell sem geometria
    assert clone.header_bytes == m.parts[0].header_bytes
    assert clone.size == m.parts[0].size


def test_parse_trophy_section_explicit_offset(trophy_bin):
    payload, _, _ = decompress_bin(trophy_bin)
    off = locate_model(payload)
    m = parse_model(payload, off)
    assert len(m.parts) >= 1
    assert write_model(m) == payload                # roundtrip do payload inteiro
