"""High-level public API: auto-detection and compatibility wrappers."""

from wepes3d import (
    import_auto, export_auto, import_new_face, import_face,
    decompress_bin, parse_model,
)


def _vcount(bin_path):
    payload, _, _ = decompress_bin(bin_path)
    return sum(p.vertex_count for p in parse_model(payload).parts)


def test_export_auto_face_and_trophy(face_bin, trophy_bin, tmp_path):
    fa = tmp_path / "fa.obj"
    ta = tmp_path / "ta.obj"
    export_auto(face_bin, str(fa))
    export_auto(trophy_bin, str(ta))
    assert fa.exists() and ta.exists()


def test_import_auto_face(face_bin, face_obj, tmp_path):
    out = tmp_path / "auto.bin"
    import_auto(face_bin, face_obj, str(out))           # detecta face
    assert _vcount(str(out)) == 696


def test_import_auto_trophy(trophy_bin, tmp_path):
    from wepes3d import export_trophy
    obj = tmp_path / "t.obj"
    export_trophy(trophy_bin, str(obj), section=0)
    out = tmp_path / "ta.bin"
    import_auto(trophy_bin, str(obj), str(out), section=0)  # detects the trophy
    assert out.exists()


def test_import_new_face_compat_alias(face_bin, face_obj, tmp_path):
    out = tmp_path / "compat.bin"
    import_new_face(face_bin, face_obj, str(out), section=99)  # section is ignored
    assert _vcount(str(out)) == 696
