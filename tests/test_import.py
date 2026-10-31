"""Import .obj -> .bin: roundtrip, estratégias de partição e erros."""

import pathlib
import struct

import pytest

from wepes3d import (
    compress_bin, decompress_bin, parse_model, import_face, import_trophy,
    export_trophy, trophy_section_offsets,
)


def _vcount(bin_path):
    """Total de vértices do modelo (auto-localiza face ou troféu)."""
    payload, _, _ = decompress_bin(bin_path)
    m = parse_model(payload)
    return sum(p.vertex_count for p in m.parts)


# ---------------------------------------------------------------------------
# Roundtrip e edição leve (contagem bate com o template)
# ---------------------------------------------------------------------------

def test_import_roundtrip_face(face_bin, face_obj, tmp_path):
    out = tmp_path / "rt.bin"
    import_face(face_bin, face_obj, str(out))
    assert out.exists()
    # a geometria é preservada (696 vértices, 8 parts)
    assert _vcount(str(out)) == 696
    # sem edição, as 8 parts passam direto (passthrough): payload byte-idêntico
    assert decompress_bin(str(out))[0] == decompress_bin(face_bin)[0]


def test_import_edited_vertex_recodes_one_part(face_bin, face_obj, tmp_path):
    # edita 1 vértice: a part dele deixa de ser "fiel" ao template (mesma
    # contagem, vértice diferente) e é recodificada; as outras seguem idênticas.
    lines = pathlib.Path(face_obj).read_text().splitlines()
    for i, ln in enumerate(lines):
        if ln.startswith("v "):
            lines[i] = "v 0.100000 -0.455029 1.723830"   # mexe no 1º vértice
            break
    edited = tmp_path / "edited.obj"
    edited.write_text("\n".join(lines) + "\n")
    out = tmp_path / "edited.bin"
    import_face(face_bin, str(edited), str(out))
    assert _vcount(str(out)) == 696


def test_import_strip_mode_list(face_bin, face_obj, tmp_path):
    out = tmp_path / "list.bin"
    # preserve_strips=False: sem edição, o passthrough manteria os strips do
    # jogo e nenhuma part seria codificada em modo list.
    import_face(face_bin, face_obj, str(out), strip_mode="list", preserve_strips=False)
    assert _vcount(str(out)) == 696


def test_import_no_preserve_strips(face_bin, face_obj, tmp_path):
    out = tmp_path / "np.bin"
    import_face(face_bin, face_obj, str(out), preserve_strips=False)
    assert _vcount(str(out)) == 696


# ---------------------------------------------------------------------------
# Recount: estratégias de partição
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
    assert _vcount(str(out)) == 32                     # 8 ilhas × 4 vértices


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
    # --use-groups pedido mas o .obj não tem grupos -> cai no BFS (com aviso)
    out = tmp_path / "nogroups.bin"
    import_face(face_bin, grid_obj(8), str(out),
                allow_recount=True, use_groups=True, recalculate_normals=True)
    assert out.exists()


def test_import_counts_match_but_order_crosses_fallback(face_bin, ribbon_obj, tmp_path):
    # 696 vértices (= template) MAS os triângulos cruzam as fronteiras de 87 ->
    # assign_triangles falha e o pipeline cai no BFS automático (fallback).
    out = tmp_path / "fallback.bin"
    import_face(face_bin, ribbon_obj(696), str(out), recalculate_normals=True)
    assert out.exists()


def test_import_match_template_without_autofit(face_bin, islands_obj, tmp_path):
    # match-template SEM auto-fit: deve avisar e ainda assim rodar
    out = tmp_path / "match2.bin"
    import_face(face_bin, islands_obj(8), str(out),
                allow_recount=True, match_template=True, recalculate_normals=True)
    assert out.exists()


# ---------------------------------------------------------------------------
# Troféu
# ---------------------------------------------------------------------------

def test_import_trophy_roundtrip(trophy_bin, tmp_path):
    obj = tmp_path / "t.obj"
    export_trophy(trophy_bin, str(obj), section=0)
    out = tmp_path / "t_rt.bin"
    import_trophy(trophy_bin, str(obj), str(out), section=0)
    # sem edição, as 14 parts passam direto: payload byte-idêntico
    assert decompress_bin(str(out))[0] == decompress_bin(trophy_bin)[0]


# ---------------------------------------------------------------------------
# Fim das parts no model header (model+0x2C, relativo ao modelo)
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
    assert secs[1] != trophy_section_offsets(template)[1]     # sec0 mudou de tamanho
    assert all(_parts_end_rel_ok(payload, off) for off in secs)


def test_import_face_model_at_0x20_updates_parts_end(face_bin, grid_obj, tmp_path):
    # face.bin com o modelo movido de 0x10 para 0x20 (layout de h2/face_1): o
    # fim das parts em model+0x2C deixa de coincidir com `parts_end - 16`.
    payload, outer, trailing = decompress_bin(face_bin)
    moved = bytearray(payload[:0x10] + bytes(16) + payload[0x10:])
    struct.pack_into("<I", moved, 0x08, 0x20)                      # offset_file_1
    parts_end = struct.unpack_from("<I", moved, 0x0C)[0]
    struct.pack_into("<I", moved, 0x0C, parts_end + 16)            # parts_end absoluto
    assert _parts_end_rel_ok(bytes(moved), 0x20)
    template = tmp_path / "face_0x20.bin"
    compress_bin(bytes(moved), outer, trailing, str(template))

    out = tmp_path / "f_recount.bin"
    import_face(str(template), grid_obj(8), str(out),
                allow_recount=True, recalculate_normals=True, auto_fit=True)
    assert _parts_end_rel_ok(decompress_bin(str(out))[0], 0x20)


# ---------------------------------------------------------------------------
# Caminhos de erro (saída limpa via sys.exit -> SystemExit)
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
                    allow_recount=True, part_sizes_override=[1] * 8)  # soma 8 != 32


def test_error_part_sizes_wrong_count(face_bin, islands_obj, tmp_path):
    with pytest.raises(SystemExit):
        import_face(face_bin, islands_obj(8), str(tmp_path / "x.bin"),
                    allow_recount=True, part_sizes_override=[8, 8, 8, 8])  # 4 != 8 parts


def test_error_max_verts_needs_too_many_parts(face_bin, grid_obj, tmp_path):
    with pytest.raises(SystemExit):
        import_face(face_bin, grid_obj(8), str(tmp_path / "x.bin"),
                    allow_recount=True, max_verts_per_part=4)   # 64/4=16 > 8 parts


def test_error_part_exceeds_255(face_bin, grid_obj, tmp_path):
    # grid 18×18 = 324 vértices; força a part 0 com 300 (> 255)
    with pytest.raises(SystemExit):
        import_face(face_bin, grid_obj(18), str(tmp_path / "x.bin"),
                    allow_recount=True,
                    part_sizes_override=[300, 6, 6, 6, 2, 2, 1, 1])  # soma = 324
