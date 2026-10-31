"""Edge cases and defensive error paths (covers the remaining branches)."""

import struct
import types

import pytest

from wepes3d import (
    decompress_bin, parse_model, import_trophy, export_stadium,
)
from wepes3d.shared.io.pes_archive import (
    load_blocks, model_offsets,
)
from wepes3d.shared.model.reader import read_part_geometry
from wepes3d.shared.model.parser import (
    locate_model, write_part, clone_part_structure,
)
from wepes3d.shared.model.rebuilder import (
    update_vertex_count_in_header, rebuild_part, patch_total_parts,
)
from wepes3d.shared.model.strip import decode_strip
from wepes3d.adapters.pesweps2.faces.profile import locate as face_locate
from wepes3d.adapters.pesweps2.trophies.profile import (
    section_offsets, locate as trophy_locate, patch_resize as trophy_patch,
)
from wepes3d.adapters.pesweps2.stadiums.profile import (
    locate as stad_locate, patch_resize as stad_patch,
)

CONTAINER = bytes([0x00, 0x06, 0x00, 0x00])


# ---------------------------------------------------------------------------
# pes_archive
# ---------------------------------------------------------------------------

def test_load_blocks_bad_magic(tmp_path):
    bad = tmp_path / "bad.bin"
    bad.write_bytes(b"\xDE\xAD\xBE\xEF" + b"\x00" * 40)
    with pytest.raises(ValueError):
        load_blocks(str(bad))


def test_model_offsets_too_short():
    assert model_offsets(b"abc") == []                 # < 8 bytes


def test_model_offsets_toc_overflow():
    # total says 5 models but the payload ends before the TOC -> break, no error
    payload = struct.pack("<II", 5, 999) + b"\x00" * 8
    assert model_offsets(payload) == []


def test_scan_container_with_invalid_zlib_block(tmp_path):
    # a container with a "00 06 01 00" that is NOT valid zlib -> except + move on
    blob = CONTAINER + b"\x00" * 12
    blob += bytes([0x00, 0x06, 0x01, 0x00])
    blob += struct.pack("<II", 4, 4) + b"\xFF\xFF\xFF\xFF"
    f = tmp_path / "c.bin"
    f.write_bytes(blob)
    assert load_blocks(str(f)) == []                   # no valid block


# ---------------------------------------------------------------------------
# reader: guards that return None
# ---------------------------------------------------------------------------

def _fake_part(off, size, pis=0):
    return types.SimpleNamespace(
        offset_in_payload=off, size=size, part_info_start_raw=pis)


def test_read_part_geometry_part_too_small():
    payload = b"\x00" * 64
    assert read_part_geometry(payload, _fake_part(0, 20)) is None   # v_addr+48 > end


def test_read_part_geometry_total_sub_invalid():
    payload = b"\x00" * 128                             # total_sub @44 == 0 -> invalid
    assert read_part_geometry(payload, _fake_part(0, 60)) is None


def test_read_part_geometry_submesh_sep_mismatch():
    buf = bytearray(128)
    struct.pack_into("<I", buf, 44, 1)                  # total_sub = 1 (valid)
    # separator expected at 56+36 = 92; we leave zeros (no match) -> None
    assert read_part_geometry(bytes(buf), _fake_part(0, 100)) is None


# ---------------------------------------------------------------------------
# parser: error branches
# ---------------------------------------------------------------------------

def test_parse_model_wrong_offset(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    with pytest.raises(ValueError):
        parse_model(payload, 0)                         # offset 0 has no MAGIC_MODEL


def test_locate_model_container_without_valid_mdl():
    buf = bytearray(0x60)
    struct.pack_into("<I", buf, 8, 0x20)                # offset_file_1 = 0x20
    buf[0x20:0x24] = CONTAINER                          # a container, but...
    struct.pack_into("<I", buf, 0x28, 0)               # base+8 -> rel 0 -> MDL at base
    # base = 0x40; payload[0x40:0x44] = zeros != MAGIC_MODEL
    with pytest.raises(ValueError):
        locate_model(bytes(buf))


def test_write_part_pads_short_content(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    p0 = parse_model(payload).parts[0]
    shell = clone_part_structure(p0)                    # no geometry -> short content
    data = write_part(shell)
    assert len(data) == shell.size                      # it was padded up to the size


# ---------------------------------------------------------------------------
# rebuilder: limits
# ---------------------------------------------------------------------------

def test_update_vertex_count_overflow(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    p0 = parse_model(payload).parts[0]
    with pytest.raises(ValueError):
        update_vertex_count_in_header(
            p0.header_bytes, p0.part_info_start_raw,
            p0.pre_normals_tag, p0.pre_uvs_tag, 256)    # > 255


def test_rebuild_part_default_new_count(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    p0 = parse_model(payload).parts[0]
    tris = decode_strip(p0.strip_indices, p0.vertex_count)
    rebuilt = rebuild_part(p0, p0.vertices, p0.normals, p0.uvs, tris,
                           strip_mode="list")           # new_count=None -> uses vc
    assert rebuilt.vertex_count == p0.vertex_count


def test_rebuild_part_strip_too_long(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    p0 = parse_model(payload).parts[0]
    huge = [(0, 1, 2)] * 800                            # 800 tris -> > 255 V4-16
    with pytest.raises(ValueError):
        rebuild_part(p0, p0.vertices, p0.normals, p0.uvs, huge, strip_mode="list")


def test_patch_total_parts(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    m = parse_model(payload)
    patched = patch_total_parts(m.pre_parts_bytes, m.offset_file_1, 5)
    assert struct.unpack_from("<I", patched, m.offset_file_1 + 0x20)[0] == 5


# ---------------------------------------------------------------------------
# adapters: profiles (invalid locate, patch_resize)
# ---------------------------------------------------------------------------

def test_face_locate_on_trophy_raises(trophy_bin):
    payload, _, _ = decompress_bin(trophy_bin)
    with pytest.raises(ValueError):
        face_locate(payload)                            # a trophy is not a face


def test_trophy_section_offsets_on_face_raises(face_bin):
    payload, _, _ = decompress_bin(face_bin)
    with pytest.raises(ValueError):
        section_offsets(payload)                        # a face is not a container


def test_trophy_locate_invalid_section(trophy_bin):
    payload, _, _ = decompress_bin(trophy_bin)
    with pytest.raises(ValueError):
        trophy_locate(payload, 999)


def test_trophy_patch_resize_noop(trophy_bin):
    payload, _, _ = decompress_bin(trophy_bin)
    out, n = trophy_patch(payload, 0, 0, 100, 100)      # delta 0 -> no-op
    assert n == 0 and out == payload


def test_stadium_patch_resize_noop_and_notimpl():
    out, n = stad_patch(b"data", 0, 0, 100, 100)        # delta 0 -> no-op
    assert n == 0
    with pytest.raises(NotImplementedError):
        stad_patch(b"data", 0, 0, 100, 200)             # size change: not supported


def test_stadium_locate_invalid(stadium_str):
    block = load_blocks(stadium_str)[0]
    with pytest.raises(ValueError):
        stad_locate(block, 999)


# ---------------------------------------------------------------------------
# folder: export_model branches
# ---------------------------------------------------------------------------

def test_export_stadium_no_model_raises(stadium_data_bin, tmp_path):
    with pytest.raises(ValueError):
        export_stadium(stadium_data_bin, str(tmp_path / "x.obj"), model=0)


def test_export_stadium_model_out_of_range(stadium_str, tmp_path):
    with pytest.raises(ValueError):
        export_stadium(stadium_str, str(tmp_path / "x.obj"), model=999)


def test_export_stadium_block_path(adboard_bin, tmp_path):
    export_stadium(adboard_bin, str(tmp_path / "b.obj"), model=0, block=0)
    assert (tmp_path / "b.obj").exists()
    with pytest.raises(ValueError):
        export_stadium(adboard_bin, str(tmp_path / "x.obj"), model=999, block=0)


# ---------------------------------------------------------------------------
# importer: trophy section that does not exist (clean exit)
# ---------------------------------------------------------------------------

def test_import_trophy_invalid_section(trophy_bin, face_obj, tmp_path):
    with pytest.raises(SystemExit):
        import_trophy(trophy_bin, face_obj, str(tmp_path / "x.bin"), section=999)


# ---------------------------------------------------------------------------
# pes6pc/reader: error branches
# ---------------------------------------------------------------------------

def test_pc_parse_model_wrong_magic():
    from wepes3d.adapters.pes6pc.reader import parse_model as pc_parse
    with pytest.raises(ValueError):
        pc_parse(b"\x00" * 64, 0)                       # no 20050420 magic


def test_pc_find_vertex_groups_none():
    from wepes3d.adapters.pes6pc.reader import find_vertex_groups
    # a block with no 07 <m> marker -> no groups -> None (uses the fallback)
    assert find_vertex_groups(b"\x00" * 32, vc=10, tri_total=5) is None
