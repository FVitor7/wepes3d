"""Testes de I/O: compressão/descompressão e leitura de .obj."""

import pathlib
import struct

import pytest

from wepes3d.shared.io.bin_io import (
    compress_bin, decompress_bin, decompress_payload,
)
from wepes3d.shared.io.obj_io import parse_obj


def test_decompress_face(face_bin):
    payload, outer, trailing = decompress_bin(face_bin)
    assert len(payload) == 38464
    assert len(outer) == 32
    assert outer[:4] == b"\x00\x06\x01\x00"          # magic do PES
    assert struct.unpack_from("<I", outer, 8)[0] == len(payload)  # deco_size
    assert trailing == b""


def test_compress_roundtrip_preserves_payload(face_bin, tmp_path):
    payload, outer, trailing = decompress_bin(face_bin)
    out = tmp_path / "rt.bin"
    compress_bin(payload, outer, trailing, str(out))
    payload2, outer2, trailing2 = decompress_bin(str(out))
    # zlib pode gerar bytes comprimidos diferentes, mas o PAYLOAD volta idêntico.
    assert payload2 == payload
    assert struct.unpack_from("<I", outer2, 8)[0] == len(payload)


def test_compress_updates_header_sizes(face_bin, tmp_path):
    payload, outer, trailing = decompress_bin(face_bin)
    out = tmp_path / "rt.bin"
    compress_bin(payload, outer, trailing, str(out))
    raw = out.read_bytes()
    comp_size = struct.unpack_from("<I", raw, 4)[0]
    deco_size = struct.unpack_from("<I", raw, 8)[0]
    assert deco_size == len(payload)
    assert comp_size == len(raw) - 32                # bate com o blob escrito


def test_decompress_payload_from_bytes(face_bin):
    raw = pathlib.Path(face_bin).read_bytes()
    # decompress_payload recebe BYTES começando pelo header de 32 B.
    payload = decompress_payload(raw)
    assert len(payload) == 38464


def test_parse_obj_basic(face_obj):
    mesh = parse_obj(face_obj)
    assert len(mesh.vertices) == 696
    assert len(mesh.uvs) == 696
    assert len(mesh.faces) == 984
    assert mesh.vertices[0] == (0.0, -0.455029, 1.723830)
    assert mesh.faces[0] == (0, 2, 1)                # 1/1 3/3 2/2 -> 0-based


def test_parse_obj_triangulates_quad_and_handles_groups(write_obj, capsys):
    verts = [(0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0)]
    uvs = [(0, 0), (1, 0), (1, 1), (0, 1)]
    # uma face com 4 vértices (quad) -> deve virar 2 triângulos (fan).
    path = write_obj(verts, uvs, [(0, 1, 2)], name="q.obj")
    # reescreve manualmente com um quad + grupo:
    text = "o grupoA\nv 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n" \
           "vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nf 1 2 3 4\n"
    pathlib.Path(path).write_text(text)
    mesh = parse_obj(path)
    assert len(mesh.vertices) == 4
    assert len(mesh.faces) == 2                      # quad -> 2 triângulos
    assert "grupoA" in mesh.group_names
    out = capsys.readouterr().out
    assert "triangulada" in out or "fan" in out


def test_parse_obj_ignores_degenerate_face(write_obj):
    verts = [(0, 0, 0), (1, 0, 0)]
    uvs = [(0, 0), (1, 0)]
    path = write_obj(verts, uvs, [], name="deg.obj")
    with open(path, "a") as fh:
        fh.write("f 1 2\n")                          # face com 2 vértices = degenerada
    mesh = parse_obj(path)
    assert mesh.faces == []
