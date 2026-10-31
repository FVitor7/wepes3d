"""
Motor de IMPORT .obj -> .bin (parametrizado por AssetProfile).

Fluxo:
  [1] Le o template .bin     -> model.parser
  [2] Le o .obj              -> io.obj_io
  [3] Auto-fit (opcional)    -> escala/centra para o bbox do template
  [4] Particionamento        -> decide quantos vertices por part e quais
  [5] Recalcula normais      -> opcional (--recalculate-normals)
  [6] Codifica + reconstroi parts
  [7] Patcha pre_parts e escreve o .bin novo
"""

import math
import sys
from typing import List, Optional, Tuple

from .assets import AssetProfile
from .partition import (
    assign_triangles_to_parts, compute_new_ranges_from_sizes,
    partition_by_obj_groups, partition_by_template, partition_mesh_by_faces,
)
from ..constants import MAX_VERTEX_COUNT_PER_PART, NORMAL_SCALE
from ..geometry.transform import auto_fit_vertices, compute_vertex_normals
from ..io.bin_io import compress_bin, decompress_bin
from ..io.obj_io import ObjMesh, parse_obj
from ..model.parser import Model, clone_part_structure, parse_model, write_model
from ..model.rebuilder import patch_parts_end, patch_total_parts, rebuild_part
from ..model.strip import decode_strip


def _import(
    profile: AssetProfile,
    template_bin_path: str,
    obj_path: str,
    output_bin_path: str,
    recalculate_normals: bool = False,
    allow_recount: bool = False,
    part_sizes_override: Optional[List[int]] = None,
    max_verts_per_part: Optional[int] = None,
    use_groups: bool = False,
    auto_fit: bool = False,
    match_template: bool = False,
    preserve_strips: bool = True,
    strip_mode: str = "connected",
    section: int = 0,
) -> None:
    """
    Pipeline generico: le template + obj, gera novo .bin, parametrizado por
    `profile` (face ou trofeu). Use os wrappers import_face/import_trophy.

    section: so para TROFEU — qual sub-modelo (.mdl) substituir. 0 = o trofeu
    principal; 1+ = outros objetos 3D (bancada, palco, etc.).

    preserve_strips: quando True (default), cada part cuja geometria reproduz
    EXATAMENTE a do template tem o strip ORIGINAL preservado (roundtrip
    byte-identico). Parts com geometria nova caem no rebuild normal.
    """
    coord = profile.coord
    # [1] Template ===========================================================
    print(f"\n[1/7] Loading {profile.name} .bin template: {template_bin_path}")
    payload, outer_header, trailing = decompress_bin(template_bin_path)
    secs = profile.list_sections(payload) if profile.list_sections else None
    if secs is not None:
        if not (0 <= section < len(secs)):
            print(f"\nERRO: secao {section} inexistente — o {profile.name} tem "
                  f"{len(secs)} sub-modelos (.mdl), indices 0..{len(secs)-1}.")
            sys.exit(1)
        print(f"      {len(secs)} sub-modelos (.mdl); alvo: secao {section} "
              f"@0x{secs[section]:X} (0=principal, 1+=outros objetos da cena)")
    model_offset = profile.locate(payload, section)
    template = parse_model(payload, model_offset)
    n_parts = len(template.parts)
    total_v_template = sum(p.vertex_count for p in template.parts)
    print(f"      Parts: {n_parts}, vertices total: {total_v_template}")
    for i, p in enumerate(template.parts):
        print(f"        Part {i}: vc={p.vertex_count}, tex_id={p.tex_id}")

    # [2] OBJ ================================================================
    print(f"\n[2/7] Loading .obj file: {obj_path}")
    obj = parse_obj(obj_path)
    print(f"      Vertices: {len(obj.vertices)}, "
          f"UVs: {len(obj.uvs)}, "
          f"Faces (triangles): {len(obj.faces)}")

    if auto_fit:
        print(f"      Aplicando --auto-fit...")
        fitted = auto_fit_vertices(obj.vertices, template, coord.int16_to_obj_vertex)
        obj = ObjMesh(
            vertices=fitted,
            uvs=obj.uvs,
            faces=obj.faces,
            face_groups=obj.face_groups,
            group_names=obj.group_names,
        )

    if len(obj.uvs) != len(obj.vertices):
        print(f"\nERRO: O .obj tem {len(obj.vertices)} vertices mas "
              f"{len(obj.uvs)} UVs. Cada vertice precisa ter exatamente 1 UV.")
        print("As faces nao referenciam UVs (formato f v/vt): reexporte o .obj com UVs.")
        sys.exit(1)

    counts_match = (len(obj.vertices) == total_v_template)
    if not counts_match and not allow_recount:
        print(f"\nERRO: Mismatch de vertices: obj={len(obj.vertices)}, "
              f"template={total_v_template}")
        print("Use --allow-recount para importar .obj com contagem diferente.")
        sys.exit(1)

    # [3-4] Particionamento ==================================================
    print(f"\n[3/7] Calculating vertex distribution across parts...")
    try:
        (work_vertices, work_uvs, work_faces,
         part_sizes, effective_parts, n_parts) = _partition(
            profile, obj, template, counts_match, allow_recount,
            part_sizes_override, max_verts_per_part,
            use_groups, match_template, auto_fit,
        )
    except ValueError as e:
        # Erros de configuracao do usuario (grupos != parts, soma de
        # --part-sizes incorreta, etc.) — mensagem limpa em vez de traceback.
        print(f"\nERRO: {e}")
        sys.exit(1)
    part_ranges = compute_new_ranges_from_sizes(part_sizes)
    for i, (s, e) in enumerate(part_ranges):
        print(f"        Part {i}: vertices {s}..{e-1} ({e-s} v)")

    for i, sz in enumerate(part_sizes):
        if sz > MAX_VERTEX_COUNT_PER_PART:
            print(f"\nERRO: Part {i} tem {sz} vertices "
                  f"(maximo: {MAX_VERTEX_COUNT_PER_PART}).")
            print("Reduza o numero de faces ou aumente o numero de parts.")
            sys.exit(1)

    print(f"\n[4/7] Assigning triangles to parts...")
    try:
        tris_per_part = assign_triangles_to_parts(work_faces, part_ranges)
    except ValueError as e:
        if counts_match:
            # Fallback: vertices na ordem errada (ex: gerado por simplifier)
            print(f"\nAVISO: Vertices com contagem certa mas ordem nao bate.")
            print(f"       Usando particionamento BFS automatico...")
            work_vertices, work_uvs, work_faces, part_sizes = partition_mesh_by_faces(
                work_vertices, work_uvs, work_faces, n_parts
            )
            for i, sz in enumerate(part_sizes):
                if sz > MAX_VERTEX_COUNT_PER_PART:
                    print(f"\nERRO: Part {i} tem {sz} vertices apos BFS "
                          f"(max: {MAX_VERTEX_COUNT_PER_PART}).")
                    sys.exit(1)
            part_ranges = compute_new_ranges_from_sizes(part_sizes)
            tris_per_part = assign_triangles_to_parts(work_faces, part_ranges)
        else:
            print(f"\nERRO: {e}")
            sys.exit(1)

    for i, tris in enumerate(tris_per_part):
        print(f"      Part {i}: {len(tris)} faces (triangles)")

    # [5] Normais ============================================================
    if recalculate_normals:
        print(f"\n[5/7] Recalculating vertex normals from geometry...")
        float_normals = compute_vertex_normals(work_vertices, work_faces)
        print(f"      {len(float_normals)} normals calculated.")
    else:
        print(f"\n[5/7] Preserving template normals...")
        float_normals = None

    # Normais (float) usadas SO para orientar a malha no modo connected — se o
    # usuario nao pediu recalculo, calculamos aqui mesmo assim (orientacao
    # precisa de uma referencia de "frente").
    orient_normals = None
    if strip_mode == "connected":
        orient_normals = (float_normals if float_normals is not None
                          else compute_vertex_normals(work_vertices, work_faces))
        print(f"      strip_mode=connected (default): tristrips conectados "
              f"(orientacao coerente + winding-aware).")

    # [6] Reconstroi parts ===================================================
    print(f"\n[6/7] Converting and rebuilding parts...")
    new_parts = []
    for i, part in enumerate(effective_parts):
        v_start, v_end = part_ranges[i]
        new_vc = v_end - v_start

        new_verts_int: List[Tuple[int, int, int]] = []
        new_uvs_int: List[Tuple[int, int]] = []
        new_normals_int: List[Tuple[int, int, int]] = []

        for v_local in range(new_vc):
            v_global = v_start + v_local
            fx, fy, fz = work_vertices[v_global]
            new_verts_int.append(coord.obj_to_int16_vertex(fx, fy, fz))

            fu, fv = work_uvs[v_global]
            new_uvs_int.append(coord.obj_to_int16_uv(fu, fv))

            if float_normals is not None:
                nx, ny, nz = float_normals[v_global]
                new_normals_int.append(coord.obj_to_int16_normal(nx, ny, nz))
            else:
                # Preserva normal do template se houver, senao fallback
                if i < len(template.parts) and v_local < len(template.parts[i].normals):
                    new_normals_int.append(template.parts[i].normals[v_local])
                else:
                    new_normals_int.append((0, 0, NORMAL_SCALE))

        if preserve_strips and _part_is_faithful(
                part, new_vc, new_verts_int, new_uvs_int, new_normals_int,
                tris_per_part[i]):
            # Geometria reproduz o template -> reaproveita a part original
            # (preserva o strip conectado do jogo) => bytes identicos.
            new_part = part
            print(f"      Part {i}: {part.vertex_count} v IDENTICA ao template "
                  f"— strip original preservado (zero-diff)")
        else:
            part_triangles = tris_per_part[i]
            if strip_mode == "connected":
                # Orienta os triangulos locais para FRENTE (coerente + normais)
                # antes de stripificar — pre-condicao do encoder conectado.
                from ..model.strip_connected import orient_for_front
                # orient_normals foi calculado acima sempre que strip_mode==connected.
                assert orient_normals is not None
                local_verts = [work_vertices[v_start + k] for k in range(new_vc)]
                local_norms = [orient_normals[v_start + k] for k in range(new_vc)]
                part_triangles = orient_for_front(
                    part_triangles, local_verts, local_norms)
            try:
                new_part = rebuild_part(
                    part, new_verts_int, new_normals_int, new_uvs_int,
                    part_triangles, new_count=new_vc, strip_mode=strip_mode,
                )
            except ValueError as e:
                # Estouro de strip (>~340 tris/part) ou de vc (>255). Mensagem
                # limpa apontando a part culpada em vez de traceback.
                print(f"\nERRO na Part {i}: {e}")
                print("Reduza a densidade da malha (decimate) ou use mais parts "
                      "(--max-verts-per-part).")
                sys.exit(1)
            size_diff = new_part.size - part.size
            diff_str = f"{size_diff:+d}" if size_diff != 0 else "(equal)"
            print(f"      Part {i}: {part.vertex_count} -> {new_vc} v, "
                  f"size {part.size} -> {new_part.size} {diff_str}, "
                  f"{len(tris_per_part[i])} tris")
        new_parts.append(new_part)

    # [7] Patches e escrita ==================================================
    print(f"\n[7/7] Writing .bin...")
    new_pre_parts = template.pre_parts_bytes
    if len(effective_parts) != len(template.parts):
        new_pre_parts = patch_total_parts(
            template.pre_parts_bytes, template.offset_file_1, len(effective_parts)
        )
        print(f"      total_parts atualizado: "
              f"{len(template.parts)} -> {len(effective_parts)}")

    new_post_parts = template.post_parts_bytes
    new_model = Model(
        payload=b'',
        offset_file_1=template.offset_file_1,
        pre_parts_bytes=new_pre_parts,
        parts=new_parts,
        post_parts_bytes=new_post_parts,
    )
    new_payload = write_model(new_model)
    print(f"      Payload: {len(new_payload)} bytes "
          f"(the template had {len(payload)})")

    # Corrige ponteiros absolutos no container se parts_end mudou
    # (face: parts_end/parts_end-16; trofeu: diretorio de secoes + header externo)
    pre_parts_size = len(template.pre_parts_bytes)
    orig_parts_end = pre_parts_size + sum(p.size for p in template.parts)
    new_parts_end = pre_parts_size + sum(p.size for p in new_parts)
    if orig_parts_end != new_parts_end:
        print(f"      Part sizes have changed: "
              f"0x{orig_parts_end:X} -> 0x{new_parts_end:X}")
        new_payload, patched = profile.patch_resize(
            new_payload, template.offset_file_1, pre_parts_size,
            orig_parts_end, new_parts_end,
        )
        print(f"      Container pointers fixed: {patched}")
        # Fim das parts no model header (+0x2C, relativo ao modelo) — face e
        # trofeu. Gravado DEPOIS do patch_resize: a varredura dele compara com
        # os valores do template e poderia re-patchar este se coincidisse.
        new_payload = patch_parts_end(new_payload, template.offset_file_1, new_parts_end)
        print(f"      Model header parts_end (rel.): "
              f"0x{new_parts_end - template.offset_file_1:X}")
    else:
        print(f"      Parts with identical size — no pointers to fix")

    compress_bin(new_payload, outer_header, trailing, output_bin_path)
    print(f"\n=== COMPLETED SUCCESSFULLY ===")
    print(f"Generated file: {output_bin_path}")


# ============================================================================
# Helper: deteccao de roundtrip fiel (passthrough do strip)
# ============================================================================

def _part_is_faithful(part, new_vc, new_verts_int, new_uvs_int,
                      new_normals_int, new_triangles) -> bool:
    """
    True se a geometria nova reproduz EXATAMENTE a part do template: mesmo vc,
    mesmos vertices/UVs/normais int16, e o mesmo CONJUNTO de triangulos que o
    strip original decodifica. Nesse caso o strip original pode ser preservado
    (roundtrip byte-identico).

    Compara triangulos como conjunto de frozensets (ignora ordem e winding),
    pois o decode do strip aplica flip e ordena diferente do .obj — o que
    importa para preservar e' que sejam os MESMOS triangulos.
    """
    if new_vc != part.vertex_count:
        return False
    if new_verts_int != list(part.vertices):
        return False
    if new_uvs_int != list(part.uvs):
        return False
    if new_normals_int != list(part.normals):
        return False
    orig_tris = {frozenset(t) for t in decode_strip(part.strip_indices, part.vertex_count)}
    new_tris = {frozenset(t) for t in new_triangles}
    return orig_tris == new_tris


# ============================================================================
# Helper: seleciona estrategia de particionamento
# ============================================================================

def _partition(
    profile: AssetProfile,
    obj: ObjMesh, template: Model, counts_match: bool, allow_recount: bool,
    part_sizes_override: Optional[List[int]], max_verts_per_part: Optional[int],
    use_groups: bool, match_template: bool, auto_fit: bool,
) -> Tuple[list, list, list, List[int], list, int]:
    """Encapsula a logica de escolha de particionamento. Retorna:
        (work_vertices, work_uvs, work_faces, part_sizes,
         effective_parts, n_parts).
    """
    n_parts = len(template.parts)
    effective_parts = list(template.parts)

    if counts_match:
        # Caso ideal: contagem do .obj bate com template
        sizes = [p.vertex_count for p in template.parts]
        print(f"      Contagem bate com template — usando distribuicao original.")
        return obj.vertices, obj.uvs, obj.faces, sizes, effective_parts, n_parts

    if part_sizes_override is not None:
        # Usuario forneceu sizes manualmente
        if len(part_sizes_override) != n_parts:
            raise ValueError(
                f"--part-sizes: forneceu {len(part_sizes_override)} sizes mas "
                f"template tem {n_parts} parts."
            )
        if sum(part_sizes_override) != len(obj.vertices):
            raise ValueError(
                f"--part-sizes: soma {sum(part_sizes_override)} difere do total "
                f"de vertices do .obj ({len(obj.vertices)})."
            )
        return obj.vertices, obj.uvs, obj.faces, part_sizes_override, effective_parts, n_parts

    n_obj_groups = len(obj.group_names)
    if use_groups and n_obj_groups > 1:
        if n_obj_groups != n_parts:
            raise ValueError(
                f"OBJ tem {n_obj_groups} grupos mas template tem {n_parts} parts."
            )
        print(f"      Particionando por {n_obj_groups} grupos OBJ...")
        work_v, work_u, work_f, sizes = partition_by_obj_groups(
            obj.vertices, obj.uvs, obj.faces, obj.face_groups, n_obj_groups,
        )
        _log_seam_stats(obj.vertices, work_v)
        return work_v, work_u, work_f, sizes, effective_parts, n_parts

    if match_template:
        print(f"      Particionando por nearest-neighbor do template...")
        if not auto_fit:
            print(f"      [AVISO] --match-template funciona melhor com --auto-fit")
        work_v, work_u, work_f, sizes = partition_by_template(
            obj.vertices, obj.uvs, obj.faces, template,
            profile.coord.int16_to_obj_vertex,
        )
        _log_seam_stats(obj.vertices, work_v)
        return work_v, work_u, work_f, sizes, effective_parts, n_parts

    if use_groups and n_obj_groups <= 1:
        print(f"      [AVISO] --use-groups pedido mas o .obj nao tem grupos 'g'/'o'. "
              f"Caindo para BFS automatico. No Blender: separe o rosto em "
              f"{n_parts} objetos e exporte como .obj multi-object.")

    # Default: BFS por adjacencia
    # Pode expandir parts alem do template se max_verts_per_part for dado
    if max_verts_per_part is not None:
        n_needed = max(n_parts, math.ceil(len(obj.vertices) / max_verts_per_part))
        if profile.max_parts is not None and n_needed > profile.max_parts:
            min_vc = math.ceil(len(obj.vertices) / profile.max_parts)
            print(f"\nERRO: --max-verts-per-part {max_verts_per_part} requer "
                  f"{n_needed} parts, mas {profile.name} suporta no maximo "
                  f"{profile.max_parts} (byte[0x04]=8 em todos os exemplos de face).")
            print(f"      Com > {profile.max_parts} parts a face fica INVISIVEL.")
            print(f"      Solucoes:")
            print(f"        1. Aumente --max-verts-per-part para >= {min_vc}")
            print(f"        2. Remova --max-verts-per-part (distribui automatico)")
            print(f"        3. Reduza o numero de vertices do .obj "
                  f"(max ~{MAX_VERTEX_COUNT_PER_PART * profile.max_parts})")
            sys.exit(1)
        if n_needed > n_parts:
            donor = template.parts[-1]
            effective_parts = list(template.parts) + [
                clone_part_structure(donor) for _ in range(n_needed - n_parts)
            ]
            n_parts = n_needed
            print(f"      Parts expandidas: {len(template.parts)} -> {n_parts}")

    print(f"      Partitioning mesh by faces (BFS) into {n_parts} groups...")
    work_v, work_u, work_f, sizes = partition_mesh_by_faces(
        obj.vertices, obj.uvs, obj.faces, n_parts,
    )
    _log_seam_stats(obj.vertices, work_v)
    return work_v, work_u, work_f, sizes, effective_parts, n_parts


def _log_seam_stats(orig, new):
    dup = len(new) - len(orig)
    print(f"      Vertices: {len(orig)} -> {len(new)} "
          f"({dup:+d} Duplicate at seams)")
