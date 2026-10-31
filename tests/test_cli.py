"""CLI: the 3 subcommands, all types, options and error handling."""

import runpy
import sys

import pytest

from wepes3d import cli
from wepes3d import compress_bin


def run(monkeypatch, *args):
    """Runs cli.main() with the given argv."""
    monkeypatch.setattr(sys, "argv", ["wepes3d", *args])
    cli.main()


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------

def test_cli_list_face(monkeypatch, face_bin, capsys):
    run(monkeypatch, "list", face_bin, "--type", "face")
    assert "face" in capsys.readouterr().out


def test_cli_list_trophy(monkeypatch, trophy_bin, capsys):
    run(monkeypatch, "list", trophy_bin, "--type", "trophy")
    assert "section" in capsys.readouterr().out


def test_cli_list_auto_detects(monkeypatch, trophy_bin, capsys):
    run(monkeypatch, "list", trophy_bin)               # --type auto (default)
    assert "trophy" in capsys.readouterr().out


@pytest.mark.parametrize("kind,fixture", [
    ("stadium", "stadium_str"), ("kit", "kit_bin"), ("pc", "pc_face_bin"),
])
def test_cli_list_folder_types(monkeypatch, request, kind, fixture, capsys):
    path = request.getfixturevalue(fixture)
    run(monkeypatch, "list", path, "--type", kind)
    assert capsys.readouterr().out.strip() != ""


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------

def test_cli_export_face(monkeypatch, face_bin, tmp_path):
    out = tmp_path / "f.obj"
    run(monkeypatch, "export", face_bin, str(out), "--type", "face")
    assert out.exists()


def test_cli_export_trophy_section(monkeypatch, trophy_bin, tmp_path):
    out = tmp_path / "t.obj"
    run(monkeypatch, "export", trophy_bin, str(out), "--type", "trophy", "--section", "1")
    assert out.exists()


def test_cli_export_stadium_all_model_parts(monkeypatch, stadium_str, tmp_path):
    run(monkeypatch, "export", stadium_str, str(tmp_path / "s.obj"), "--type", "stadium", "--all")
    run(monkeypatch, "export", stadium_str, str(tmp_path / "sm.obj"), "--type", "stadium", "--model", "0")
    run(monkeypatch, "export", stadium_str, str(tmp_path / "sp.obj"), "--type", "stadium", "--parts")
    assert (tmp_path / "s.obj").exists()


def test_cli_export_kit_groups_dedup(monkeypatch, kit_bin, tmp_path):
    run(monkeypatch, "export", kit_bin, str(tmp_path / "k.obj"),
        "--type", "kit", "--all", "--dedup")
    assert (tmp_path / "k.obj").exists()


def test_cli_export_pc(monkeypatch, pc_face_bin, tmp_path):
    run(monkeypatch, "export", pc_face_bin, str(tmp_path / "p.obj"), "--type", "pc")
    assert (tmp_path / "p.obj").exists()


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------

def test_cli_export_auto(monkeypatch, face_bin, tmp_path):
    out = tmp_path / "auto.obj"
    run(monkeypatch, "export", face_bin, str(out))     # no --type -> auto
    assert out.exists()


def test_cli_import_trophy(monkeypatch, trophy_bin, tmp_path):
    obj = tmp_path / "t.obj"
    run(monkeypatch, "export", trophy_bin, str(obj), "--type", "trophy", "--section", "0")
    out = tmp_path / "t.bin"
    run(monkeypatch, "import", trophy_bin, str(obj), str(out), "--type", "trophy", "--section", "0")
    assert out.exists()


def test_cli_import_face(monkeypatch, face_bin, face_obj, tmp_path):
    out = tmp_path / "out.bin"
    run(monkeypatch, "import", face_bin, face_obj, str(out),
        "--type", "face", "--recalculate-normals")
    assert out.exists()


def test_cli_import_recount(monkeypatch, face_bin, grid_obj, tmp_path):
    out = tmp_path / "out.bin"
    run(monkeypatch, "import", face_bin, grid_obj(8), str(out),
        "--type", "auto", "--allow-recount", "--recalculate-normals", "--auto-fit")
    assert out.exists()


# ---------------------------------------------------------------------------
# Usage errors (argparse -> SystemExit 2) and runtime errors (SystemExit 1)
# ---------------------------------------------------------------------------

def test_cli_no_command(monkeypatch):
    with pytest.raises(SystemExit):
        run(monkeypatch)                               # a subcommand is required


def test_cli_help(monkeypatch):
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "--help")
    assert e.value.code == 0


def test_cli_export_all_on_face_errors(monkeypatch, face_bin, tmp_path):
    with pytest.raises(SystemExit):
        run(monkeypatch, "export", face_bin, str(tmp_path / "x.obj"),
            "--type", "face", "--all")


def test_cli_import_groups_without_recount(monkeypatch, face_bin, face_obj, tmp_path):
    with pytest.raises(SystemExit):
        run(monkeypatch, "import", face_bin, face_obj, str(tmp_path / "x.bin"),
            "--use-groups")                             # needs --allow-recount


def test_cli_import_bad_part_sizes(monkeypatch, face_bin, face_obj, tmp_path):
    with pytest.raises(SystemExit):
        run(monkeypatch, "import", face_bin, face_obj, str(tmp_path / "x.bin"),
            "--allow-recount", "--part-sizes", "a,b,c")  # not integers


def test_cli_file_not_found(monkeypatch, tmp_path):
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "export", str(tmp_path / "nope.bin"),
            str(tmp_path / "o.obj"), "--type", "face")
    assert e.value.code == 1


def test_cli_corrupt_file_struct_error(monkeypatch, tmp_path):
    bad = tmp_path / "bad.bin"
    compress_bin(b"\x00\x00\x00\x00", b"\x00" * 32, b"", str(bad))  # payload too short
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "export", str(bad), str(tmp_path / "o.obj"), "--type", "face")
    assert e.value.code == 1


def test_cli_keyboard_interrupt(monkeypatch, face_bin, tmp_path):
    def boom(*a, **k):
        raise KeyboardInterrupt
    monkeypatch.setattr(cli, "export_face", boom)
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "export", face_bin, str(tmp_path / "o.obj"), "--type", "face")
    assert e.value.code == 130


def test_cli_value_error_clean_exit(monkeypatch, face_bin, tmp_path):
    def boom(*a, **k):
        raise ValueError("test error")
    monkeypatch.setattr(cli, "export_face", boom)
    with pytest.raises(SystemExit) as e:
        run(monkeypatch, "export", face_bin, str(tmp_path / "o.obj"), "--type", "face")
    assert e.value.code == 1


def test_main_module_importable():
    # imports __main__ as a normal module (the __name__ != "__main__" guard)
    import wepes3d.__main__ as m
    assert hasattr(m, "main")


def test_main_module_entrypoint(monkeypatch, face_bin):
    # runs `python -m wepes3d list ...` with runpy
    sys.modules.pop("wepes3d.__main__", None)
    monkeypatch.setattr(sys, "argv",
                        ["wepes3d", "list", face_bin, "--type", "face"])
    runpy.run_module("wepes3d", run_name="__main__")
