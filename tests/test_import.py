"""Import .obj -> .bin: roundtrip, partition strategies and errors."""

import pathlib
import re
import struct
from types import SimpleNamespace

import pytest

from wepes3d import (
    compress_bin, decompress_bin, parse_model, import_face, import_trophy,
    export_trophy, trophy_section_offsets,
)
from wepes3d.shared.io.obj_io import parse_obj
from wepes3d.shared.pipeline.importer import _partition


def _vcount(bin_path):
    """Total vertices of the model (finds face or trophy automatically)."""
    payload, _, _ = decompress_bin(bin_path)
    m = parse_model(payload)
    return sum(p.vertex_count for p in m.parts)


# ---------------------------------------------------------------------------
# Roundtrip and light edits (the count matches the template)
# ---------------------------------------------------------------------------

def test_import_roundtrip_face(face_bin, face_obj, tmp_path):
    out = tmp_path / "rt.bin"
    import_face(face_bin, face_obj, str(out))
    assert out.exists()
    # the geometry is kept (696 vertices, 8 parts)
    assert _vcount(str(out)) == 696
    # without edits, all 8 parts pass through (passthrough): byte-identical payload
    assert decompress_bin(str(out))[0] == decompress_bin(face_bin)[0]


def test_import_edited_vertex_recodes_one_part(face_bin, face_obj, tmp_path):
    # edits 1 vertex: its part is no longer "faithful" to the template (same
    # count, different vertex) and is re-encoded; the others stay identical.
    lines = pathlib.Path(face_obj).read_text().splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("v "):
            lines[i] = "v 0.100000 -0.455029 1.723830"   # moves the 1st vertex
            break
    edited = tmp_path / "edited.obj"
    edited.write_text("\n".join(lines) + "\n")
    out = tmp_path / "edited.bin"
    import_face(face_bin, str(edited), str(out))
    assert _vcount(str(out)) == 696


def test_import_strip_mode_list(face_bin, face_obj, tmp_path):
    out = tmp_path / "list.bin"
    # preserve_strips=False: without edits, the passthrough would keep the
    # game strips and no part would be encoded in list mode.
    import_face(face_bin, face_obj, str(out), strip_mode="list", preserve_strips=False)
    assert _vcount(str(out)) == 696


def test_import_no_preserve_strips(face_bin, face_obj, tmp_path):
    out = tmp_path / "np.bin"
    import_face(face_bin, face_obj, str(out), preserve_strips=False)
    assert _vcount(str(out)) == 696


# ---------------------------------------------------------------------------
# Recount: partition strategies
# ---------------------------------------------------------------------------

def test_import_recount_bfs(face_bin, grid_obj, tmp_path):
    out = tmp_path / "bfs.bin"
    import_face(face_bin, grid_obj(8), str(out),
                allow_recount=True, recalculate_normals=True, auto_fit=True)
    assert out.exists()


def test_import_use_groups(face_bin, islands_obj, tmp_path):
    out = tmp_path / "groups.bin"
    import_face(face_bin, islands_obj(8, with_groups=True), str(out),
                allow_recount=True, use_groups=True, recalculate_normals=True)
    assert _vcount(str(out)) == 32                     # 8 islands × 4 vertices


def test_import_part_sizes(face_bin, islands_obj, tmp_path):
    out = tmp_path / "psizes.bin"
    import_face(face_bin, islands_obj(8), str(out),
                allow_recount=True, part_sizes_override=[4] * 8)
    assert _vcount(str(out)) == 32


def test_import_match_template(face_bin, islands_obj, tmp_path):
    out = tmp_path / "match.bin"
    import_face(face_bin, islands_obj(8), str(out),
                allow_recount=True, match_template=True, auto_fit=True,
                recalculate_normals=True)
    assert out.exists()


def test_import_use_groups_without_groups_warns(face_bin, grid_obj, tmp_path):
    # --use-groups was asked but the .obj has no groups -> falls back to BFS (with a warning)
    out = tmp_path / "nogroups.bin"
    import_face(face_bin, grid_obj(8), str(out),
                allow_recount=True, use_groups=True, recalculate_normals=True)
    assert out.exists()


def test_import_counts_match_but_order_crosses_fallback(face_bin, ribbon_obj, tmp_path):
    # 696 vertices (= template) BUT the triangles cross the 87-vertex borders ->
    # assign_triangles fails and the pipeline falls back to automatic BFS.
    out = tmp_path / "fallback.bin"
    import_face(face_bin, ribbon_obj(696), str(out), recalculate_normals=True)
    assert out.exists()


def test_import_match_template_without_autofit(face_bin, islands_obj, tmp_path):
    # match-template WITHOUT auto-fit: must warn and still run
    out = tmp_path / "match2.bin"
    import_face(face_bin, islands_obj(8), str(out),
                allow_recount=True, match_template=True, recalculate_normals=True)
    assert out.exists()


# ---------------------------------------------------------------------------
# Trophy
# ---------------------------------------------------------------------------

def test_import_trophy_roundtrip(trophy_bin, tmp_path):
    obj = tmp_path / "t.obj"
    export_trophy(trophy_bin, str(obj), section=0)
    out = tmp_path / "t_rt.bin"
    import_trophy(trophy_bin, str(obj), str(out), section=0)
    # without edits, all 14 parts pass through: byte-identical payload
    assert decompress_bin(str(out))[0] == decompress_bin(trophy_bin)[0]


# ---------------------------------------------------------------------------
# End of the parts in the model header (model+0x2C, relative to the model)
# ---------------------------------------------------------------------------

def _parts_end_rel_ok(payload, model_offset):
    m = parse_model(payload, model_offset)
    parts_end = len(m.pre_parts_bytes) + sum(p.size for p in m.parts)
    return struct.unpack_from("<I", payload, model_offset + 0x2C)[0] == parts_end - model_offset


def test_import_trophy_recount_updates_parts_end(trophy_bin, grid_obj, tmp_path):
    out = tmp_path / "t_recount.bin"
    import_trophy(trophy_bin, grid_obj(8), str(out), section=0,
                  allow_recount=True, recalculate_normals=True, auto_fit=True)
    template, _, _ = decompress_bin(trophy_bin)
    payload, _, _ = decompress_bin(str(out))
    secs = trophy_section_offsets(payload)
    assert secs[1] != trophy_section_offsets(template)[1]     # sec0 changed size
    assert all(_parts_end_rel_ok(payload, off) for off in secs)


def test_max_verts_per_part_is_a_hard_limit(trophy_bin, grid_obj, tmp_path):
    # Bug 16: the option used to be only an average (this case gave 66 v)
    out = tmp_path / "t_cap.bin"
    import_trophy(trophy_bin, grid_obj(30), str(out), section=0, allow_recount=True,
                  recalculate_normals=True, auto_fit=True, max_verts_per_part=40)
    payload, _, _ = decompress_bin(str(out))
    secs = trophy_section_offsets(payload)
    parts = parse_model(payload, secs[0]).parts
    assert max(p.vertex_count for p in parts) <= 40
    assert len(parts) > 14                      # parts added to the template's 14
    assert all(_parts_end_rel_ok(payload, off) for off in secs)


def test_max_verts_per_part_above_255_uses_255(trophy_bin, grid_obj, tmp_path, capsys):
    out = tmp_path / "t_400.bin"
    import_trophy(trophy_bin, grid_obj(10), str(out), section=0,
                  allow_recount=True, auto_fit=True, max_verts_per_part=400)
    assert "using 255" in capsys.readouterr().out
    assert out.exists()


def test_import_face_model_at_0x20_updates_parts_end(face_bin, grid_obj, tmp_path):
    # face.bin with the model moved from 0x10 to 0x20 (the h2/face_1 layout):
    # the end of the parts at model+0x2C is no longer equal to `parts_end - 16`.
    payload, outer, trailing = decompress_bin(face_bin)
    moved = bytearray(payload[:0x10] + bytes(16) + payload[0x10:])
    struct.pack_into("<I", moved, 0x08, 0x20)                      # offset_file_1
    parts_end = struct.unpack_from("<I", moved, 0x0C)[0]
    struct.pack_into("<I", moved, 0x0C, parts_end + 16)            # absolute parts_end
    assert _parts_end_rel_ok(bytes(moved), 0x20)
    template = tmp_path / "face_0x20.bin"
    compress_bin(bytes(moved), outer, trailing, str(template))

    out = tmp_path / "f_recount.bin"
    import_face(str(template), grid_obj(8), str(out),
                allow_recount=True, recalculate_normals=True, auto_fit=True)
    assert _parts_end_rel_ok(decompress_bin(str(out))[0], 0x20)


# ---------------------------------------------------------------------------
# Error paths (clean exit via sys.exit -> SystemExit)
# ---------------------------------------------------------------------------

def test_error_recount_without_flag(face_bin, grid_obj, tmp_path):
    with pytest.raises(SystemExit):
        import_face(face_bin, grid_obj(8), str(tmp_path / "x.bin"))


def test_error_uv_mismatch(face_bin, tmp_path):
    bad = tmp_path / "baduv.obj"
    bad.write_text("v 0 0 0\nv 1 0 0\nv 0 1 0\nvt 0 0\nvt 1 0\nf 1 2 3\n")
    with pytest.raises(SystemExit):
        import_face(face_bin, str(bad), str(tmp_path / "x.bin"), allow_recount=True)


def test_error_use_groups_wrong_count(face_bin, islands_obj, tmp_path):
    with pytest.raises(SystemExit):
        import_face(face_bin, islands_obj(4, with_groups=True),
                    str(tmp_path / "x.bin"), allow_recount=True, use_groups=True)


def test_error_part_sizes_wrong_sum(face_bin, islands_obj, tmp_path):
    with pytest.raises(SystemExit):
        import_face(face_bin, islands_obj(8), str(tmp_path / "x.bin"),
                    allow_recount=True, part_sizes_override=[1] * 8)  # sum 8 != 32


def test_error_part_sizes_wrong_count(face_bin, islands_obj, tmp_path):
    with pytest.raises(SystemExit):
        import_face(face_bin, islands_obj(8), str(tmp_path / "x.bin"),
                    allow_recount=True, part_sizes_override=[8, 8, 8, 8])  # 4 != 8 parts


def test_error_max_verts_needs_too_many_parts(face_bin, grid_obj, tmp_path):
    with pytest.raises(SystemExit):
        import_face(face_bin, grid_obj(8), str(tmp_path / "x.bin"),
                    allow_recount=True, max_verts_per_part=4)   # 64/4=16 > 8 parts


def test_error_max_verts_hard_limit_needs_more_than_8_parts(face_bin, grid_obj, tmp_path):
    # ceil(400/60) = 7 parts on paper, but the seam copies need a 9th part,
    # and a face stops at 8 (before Bug 16 it made parts with 72 v instead)
    with pytest.raises(SystemExit):
        import_face(face_bin, grid_obj(20), str(tmp_path / "x.bin"),
                    allow_recount=True, max_verts_per_part=60)


def test_error_max_verts_below_3(face_bin, grid_obj, tmp_path):
    with pytest.raises(SystemExit):
        import_face(face_bin, grid_obj(8), str(tmp_path / "x.bin"),
                    allow_recount=True, max_verts_per_part=2)


def test_error_mesh_too_big_for_the_template_parts(trophy_bin, grid_obj, tmp_path, capsys):
    # 3600 v do not fit in the 14 parts × 255 v of sec0: a clear stop + a hint
    with pytest.raises(SystemExit):
        import_trophy(trophy_bin, grid_obj(60), str(tmp_path / "x.bin"), section=0,
                      allow_recount=True, auto_fit=True)
    assert "--max-verts-per-part 255" in capsys.readouterr().out


@pytest.mark.parametrize("max_parts, hint", [
    (None, "use --max-verts-per-part 255 to add parts"),
    (8, "at most 8 for a face"),
    (2, "a face has at most 2 parts"),
])
def test_hint_when_the_mesh_does_not_fit(grid_obj, max_parts, hint):
    # 2 template parts × 255 v cannot hold a 24×24 grid (576 v)
    profile = SimpleNamespace(name="face", max_parts=max_parts)
    template = SimpleNamespace(parts=[object(), object()])
    with pytest.raises(ValueError, match=re.escape(hint)):
        _partition(profile, parse_obj(grid_obj(24)), template,
                   counts_match=False, allow_recount=True,
                   part_sizes_override=None, max_verts_per_part=None,
                   use_groups=False, match_template=False, auto_fit=False)


def test_error_part_exceeds_255(face_bin, grid_obj, tmp_path):
    # grid 18×18 = 324 vertices; forces part 0 to 300 (> 255)
    with pytest.raises(SystemExit):
        import_face(face_bin, grid_obj(18), str(tmp_path / "x.bin"),
                    allow_recount=True,
                    part_sizes_override=[300, 6, 6, 6, 2, 2, 1, 1])  # sum = 324
