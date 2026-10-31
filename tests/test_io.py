"""I/O tests: compression/decompression, reading and conversion of .obj files."""

import pathlib
import struct

import pytest

from wepes3d import convert_obj_to_vertex_uv
from wepes3d.shared.io.bin_io import (
    compress_bin, decompress_bin, decompress_payload,
)
from wepes3d.shared.io.obj_io import parse_obj


def test_decompress_face(face_bin):
    payload, outer, trailing = decompress_bin(face_bin)
    assert len(payload) == 38464
    assert len(outer) == 32
    assert outer[:4] == b"\x00\x06\x01\x00"          # PES magic
    assert struct.unpack_from("<I", outer, 8)[0] == len(payload)  # deco_size
    assert trailing == b""


def test_compress_roundtrip_preserves_payload(face_bin, tmp_path):
    payload, outer, trailing = decompress_bin(face_bin)
    out = tmp_path / "rt.bin"
    compress_bin(payload, outer, trailing, str(out))
    payload2, outer2, trailing2 = decompress_bin(str(out))
    # zlib may produce different compressed bytes, but the PAYLOAD comes back identical.
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
    assert comp_size == len(raw) - 32                # matches the written blob


def test_decompress_payload_from_bytes(face_bin):
    raw = pathlib.Path(face_bin).read_bytes()
    # decompress_payload takes BYTES that start with the 32 B header.
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
    # a face with 4 vertices (quad) -> must become 2 triangles (fan).
    path = write_obj(verts, uvs, [(0, 1, 2)], name="q.obj")
    # rewrites it by hand with a quad + group:
    text = "o grupoA\nv 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n" \
           "vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nf 1 2 3 4\n"
    pathlib.Path(path).write_text(text)
    mesh = parse_obj(path)
    assert len(mesh.vertices) == 4
    assert len(mesh.faces) == 2                      # quad -> 2 triangles
    assert "grupoA" in mesh.group_names
    out = capsys.readouterr().out
    assert "triangulated" in out or "fan" in out


def test_parse_obj_ignores_degenerate_face(write_obj):
    verts = [(0, 0, 0), (1, 0, 0)]
    uvs = [(0, 0), (1, 0)]
    path = write_obj(verts, uvs, [], name="deg.obj")
    with open(path, "a") as fh:
        fh.write("f 1 2\n")                          # face with 2 vertices = degenerate
    mesh = parse_obj(path)
    assert mesh.faces == []


def test_parse_obj_follows_vt_index(tmp_path):
    # Same count of v and vt, but in different orders (Blender export):
    # each vertex gets the UV that the face points to, not the one at the same
    # position.
    src = tmp_path / "perm.obj"
    src.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\n"
                   "vt 0 1\nvt 1 0\nvt 0 0\n"
                   "f 1/3 2/2 3/1\n")
    mesh = parse_obj(str(src))
    assert mesh.vertices == [(0.0, 0.0, 0.0), (1.0, 0.0, 0.0), (0.0, 1.0, 0.0)]
    assert mesh.uvs == [(0.0, 0.0), (1.0, 0.0), (0.0, 1.0)]
    assert mesh.faces == [(0, 1, 2)]


def test_parse_obj_splits_vertex_at_uv_seam(tmp_path, capsys):
    # Vertex 1 shows up with 2 UVs (seam) -> it becomes 2 vertices, and the
    # import no longer stops with "X vertices but Y UVs".
    src = tmp_path / "seam.obj"
    src.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"
                   "vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nvt 0.5 0.5\n"
                   "f 1/1 2/2 3/3\nf 1/5 3/3 4/4\n")
    mesh = parse_obj(str(src))
    assert len(mesh.vertices) == len(mesh.uvs) == 5
    assert mesh.faces == [(0, 1, 2), (3, 2, 4)]
    assert mesh.vertices[3] == mesh.vertices[0]
    assert mesh.uvs[3] == (0.5, 0.5)
    assert "4 vertices -> 5" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# convert_obj_to_vertex_uv (1 UV per vertex)
# ---------------------------------------------------------------------------

def _face_lines(path):
    return [ln for ln in pathlib.Path(path).read_text().splitlines() if ln.startswith("f ")]


def test_convert_obj_to_vertex_uv_splits_by_v_vt_pair(tmp_path, capsys):
    # Like a Blender export: different v and vt indices, and vertex 1 with 2
    # UVs (seam) -> it becomes 2 vertices.
    src = tmp_path / "blender.obj"
    src.write_text("o malha\n"
                   "v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"
                   "vt 0.5 0.5\nvt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\n"
                   "f 1/2 2/3 3/4\nf 1/5 3/4 4/1\n")
    out = tmp_path / "pronto.obj"
    convert_obj_to_vertex_uv(str(src), str(out))
    assert "4 vertices -> 5" in capsys.readouterr().out

    for line in _face_lines(out):                     # every face in the i/i format
        assert all(t.split("/")[0] == t.split("/")[1] for t in line.split()[1:])
    mesh = parse_obj(str(out))
    assert len(mesh.vertices) == len(mesh.uvs) == 5
    assert mesh.faces == [(0, 1, 2), (3, 2, 4)]
    assert mesh.vertices[0] == mesh.vertices[3] == (0.0, 0.0, 0.0)   # duplicated
    assert mesh.uvs[0] == (0.0, 0.0) and mesh.uvs[3] == (0.0, 1.0)  # UV of each side
    assert "malha" in mesh.group_names                # group kept


def test_convert_obj_to_vertex_uv_keeps_aligned_obj(face_obj, tmp_path):
    # .obj already aligned (written by the export): same vertices, same order.
    out = tmp_path / "face_conv.obj"
    convert_obj_to_vertex_uv(face_obj, str(out))
    orig, conv = parse_obj(face_obj), parse_obj(str(out))
    assert conv.vertices == orig.vertices
    assert conv.uvs == orig.uvs
    assert conv.faces == orig.faces


def test_convert_obj_to_vertex_uv_keeps_polygons(tmp_path):
    src = tmp_path / "quad.obj"
    src.write_text("v 0 0 0\nv 1 0 0\nv 1 1 0\nv 0 1 0\n"
                   "vt 0 0\nvt 1 0\nvt 1 1\nvt 0 1\nf 1/4 2/3 3/2 4/1\n")
    out = tmp_path / "quad_conv.obj"
    convert_obj_to_vertex_uv(str(src), str(out))
    assert _face_lines(out) == ["f 1/1 2/2 3/3 4/4"]  # a quad stays a quad
    assert parse_obj(str(out)).uvs[0] == (0.0, 1.0)   # UV of corner 1 (vt 4)


def test_convert_obj_to_vertex_uv_requires_uvs(tmp_path):
    src = tmp_path / "semuv.obj"
    src.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n")
    with pytest.raises(ValueError):
        convert_obj_to_vertex_uv(str(src), str(tmp_path / "x.obj"))
