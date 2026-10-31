"""Export .bin/.str -> .obj for the 5 asset types + variations."""

import os

import pytest

from wepes3d import (
    decompress_bin,
    export_face, export_trophy, export_auto, trophy_section_offsets,
    export_stadium, export_stadium_complete, export_stadium_parts,
    export_stadium_scene, list_stadium, stadium_index,
    export_kit, export_kit_complete, export_kit_parts, export_kit_scene,
    list_kit, kit_index,
    export_pc, export_pc_complete, export_pc_parts, list_pc, pc_index,
)


def count_obj(path):
    v = f = vt = 0
    with open(path) as fh:
        for line in fh:
            if line.startswith("v "):
                v += 1
            elif line.startswith("vt "):
                vt += 1
            elif line.startswith("f "):
                f += 1
    return v, vt, f


# ---------------------------------------------------------------------------
# FACE
# ---------------------------------------------------------------------------

def test_export_face(face_bin, tmp_path):
    out = tmp_path / "face.obj"
    export_face(face_bin, str(out))
    v, vt, f = count_obj(out)
    assert (v, f) == (696, 984)
    assert (tmp_path / "face.mtl").exists()           # writes the .mtl


def test_export_face_no_mtl(face_bin, tmp_path):
    out = tmp_path / "f.obj"
    export_face(face_bin, str(out), write_mtl=False)
    assert out.exists()
    assert not (tmp_path / "f.mtl").exists()


def test_export_auto_face(face_bin, tmp_path):
    out = tmp_path / "a.obj"
    export_auto(face_bin, str(out))
    assert count_obj(out)[0] == 696


# ---------------------------------------------------------------------------
# TROPHY
# ---------------------------------------------------------------------------

def test_trophy_sections(trophy_bin):
    payload, _, _ = decompress_bin(trophy_bin)
    assert len(trophy_section_offsets(payload)) == 9


def test_export_trophy_section0(trophy_bin, tmp_path):
    out = tmp_path / "t.obj"
    export_trophy(trophy_bin, str(out), section=0)
    v, vt, f = count_obj(out)
    assert (v, f) == (1416, 1382)


def test_export_trophy_other_section(trophy_bin, tmp_path):
    out = tmp_path / "t1.obj"
    export_trophy(trophy_bin, str(out), section=1)
    assert count_obj(out)[0] > 0


def test_export_all_trophy_sections(trophy_bin, tmp_path):
    # exports ALL 9 sections (sub-models). Some use different vertex formats
    # (V3-32 / extra UV block) — this exercises those branches of the reader.
    payload, _, _ = decompress_bin(trophy_bin)
    n = len(trophy_section_offsets(payload))
    assert n == 9
    for s in range(n):
        out = tmp_path / f"sec{s}.obj"
        export_trophy(trophy_bin, str(out), section=s)
        assert out.exists() and count_obj(out)[0] > 0


def test_export_auto_trophy(trophy_bin, tmp_path):
    out = tmp_path / "ta.obj"
    export_auto(trophy_bin, str(out))
    assert count_obj(out)[0] == 1416                  # detects the trophy and exports sec0


# ---------------------------------------------------------------------------
# STADIUM (.str = single block; .bin = container)
# ---------------------------------------------------------------------------

def test_stadium_str_complete(stadium_str, tmp_path):
    out = tmp_path / "s.obj"
    export_stadium_complete(stadium_str, str(out))
    v, vt, f = count_obj(out)
    assert (v, f) == (4096, 2104)


def test_stadium_index_and_list(stadium_str, capsys):
    idx = stadium_index(stadium_str)
    assert len(idx) >= 1
    list_stadium(stadium_str)
    assert "model" in capsys.readouterr().out


def test_stadium_model_and_parts(stadium_str, tmp_path):
    one = tmp_path / "one.obj"
    export_stadium(stadium_str, str(one), model=0)
    assert count_obj(one)[0] > 0
    export_stadium_parts(stadium_str, str(tmp_path / "sp"))
    assert any(p.name.endswith(".obj") for p in tmp_path.iterdir())


def test_stadium_scene(stadium_str, tmp_path):
    out = tmp_path / "scene.obj"
    export_stadium_scene([stadium_str], str(out))
    assert count_obj(out)[0] > 0


def test_stadium_container_with_models(adboard_bin, tmp_path, capsys):
    list_stadium(adboard_bin)
    assert "model" in capsys.readouterr().out
    out = tmp_path / "ad.obj"
    export_stadium_complete(adboard_bin, str(out))
    assert count_obj(out)[0] > 0


def test_stadium_container_zero_models(stadium_data_bin, capsys):
    idx = stadium_index(stadium_data_bin)
    assert isinstance(idx, list)
    list_stadium(stadium_data_bin)
    assert "0 model" in capsys.readouterr().out


def test_stadium_groups_dedup(adboard_bin, tmp_path):
    out = tmp_path / "g.obj"
    export_stadium_complete(adboard_bin, str(out), dedup=True)
    assert out.exists()
    out2 = tmp_path / "g2.obj"
    export_stadium(adboard_bin, str(out2), model=0, groups=True)
    assert out2.exists()


# ---------------------------------------------------------------------------
# KIT (same engine; face coordinates)
# ---------------------------------------------------------------------------

def test_kit_complete(kit_bin, tmp_path):
    out = tmp_path / "k.obj"
    export_kit_complete(kit_bin, str(out))
    v, vt, f = count_obj(out)
    assert (v, f) == (564, 584)


def test_kit_index_list_model_parts_scene(kit_bin, tmp_path, capsys):
    idx = kit_index(kit_bin)
    assert len(idx) >= 1
    list_kit(kit_bin)
    assert "model" in capsys.readouterr().out
    export_kit(kit_bin, str(tmp_path / "km.obj"), model=0)
    export_kit_parts(kit_bin, str(tmp_path / "kp"))
    export_kit_scene([kit_bin], str(tmp_path / "ks.obj"))
    assert (tmp_path / "km.obj").exists()
    assert (tmp_path / "ks.obj").exists()


def test_kit_groups_and_dedup(kit_bin, tmp_path):
    export_kit_complete(kit_bin, str(tmp_path / "kd.obj"), dedup=True)
    export_kit(kit_bin, str(tmp_path / "kg.obj"), model=0, groups=True)
    assert (tmp_path / "kd.obj").exists()


# ---------------------------------------------------------------------------
# PES6 PC (face = 1 model; trophy = N parts)
# ---------------------------------------------------------------------------

def test_pc_face(pc_face_bin, tmp_path):
    out = tmp_path / "pc.obj"
    export_pc(pc_face_bin, str(out))
    v, vt, f = count_obj(out)
    assert (v, f) == (1094, 2033)


def test_pc_face_list(pc_face_bin, capsys):
    list_pc(pc_face_bin)
    assert "face" in capsys.readouterr().out          # 1 model -> "face"


def test_pc_trophy_complete_and_parts(pc_trophy_str, tmp_path, capsys):
    idx = pc_index(pc_trophy_str)
    assert len(idx) == 9
    list_pc(pc_trophy_str)
    assert "trophy" in capsys.readouterr().out
    export_pc_complete(pc_trophy_str, str(tmp_path / "pcc.obj"))
    export_pc_parts(pc_trophy_str, str(tmp_path / "pcp"))
    assert (tmp_path / "pcc.obj").exists()


def test_pc_model_and_dedup(pc_trophy_str, tmp_path):
    export_pc(pc_trophy_str, str(tmp_path / "pm.obj"), model=0)
    export_pc_complete(pc_trophy_str, str(tmp_path / "pcd.obj"), dedup=True)
    assert (tmp_path / "pm.obj").exists()


def test_pc_invalid_model_raises(pc_face_bin, tmp_path):
    with pytest.raises(IndexError):
        export_pc(pc_face_bin, str(tmp_path / "x.obj"), model=99)


def test_pc_non_pc_file_raises(face_bin, tmp_path):
    # a PS2 face has no PC 20050420 magic -> clear error
    with pytest.raises(ValueError):
        export_pc(face_bin, str(tmp_path / "x.obj"))
