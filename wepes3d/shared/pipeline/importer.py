"""
IMPORT engine .obj -> .bin (driven by an AssetProfile).

Flow:
  [1] Reads the template .bin  -> model.parser
  [2] Reads the .obj           -> io.obj_io
  [3] Auto-fit (optional)      -> scales/centers into the template bbox
  [4] Partitioning             -> decides how many vertices go to each part
  [5] Recalculates normals     -> optional (--recalculate-normals)
  [6] Encodes + rebuilds the parts
  [7] Patches pre_parts and writes the new .bin
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
    Generic pipeline: reads the template + obj and writes a new .bin, driven
    by `profile` (face or trophy). Use the import_face/import_trophy wrappers.

    section: TROPHY only — which sub-model (.mdl) to replace. 0 = the main
    trophy; 1+ = other 3D objects (stand, stage, etc.).

    preserve_strips: when True (default), each part whose geometry matches
    the template EXACTLY keeps its ORIGINAL strip (byte-identical roundtrip).
    Parts with new geometry go through the normal rebuild.
    """
    coord = profile.coord
    # [1] Template ===========================================================
    print(f"\n[1/7] Loading {profile.name} .bin template: {template_bin_path}")
    payload, outer_header, trailing = decompress_bin(template_bin_path)
    secs = profile.list_sections(payload) if profile.list_sections else None
    if secs is not None:
        if not (0 <= section < len(secs)):
            print(f"\nERROR: section {section} does not exist — this {profile.name} has "
                  f"{len(secs)} sub-models (.mdl), indices 0..{len(secs)-1}.")
            sys.exit(1)
        print(f"      {len(secs)} sub-models (.mdl); target: section {section} "
              f"@0x{secs[section]:X} (0=main, 1+=other objects of the scene)")
    model_offset = profile.locate(payload, section)
    template = parse_model(payload, model_offset)
    n_parts = len(template.parts)
    total_v_template = sum(p.vertex_count for p in template.parts)
    print(f"      Parts: {n_parts}, total vertices: {total_v_template}")
    for i, p in enumerate(template.parts):
        print(f"        Part {i}: vc={p.vertex_count}, tex_id={p.tex_id}")

    # [2] OBJ ================================================================
    print(f"\n[2/7] Loading .obj file: {obj_path}")
    obj = parse_obj(obj_path)
    print(f"      Vertices: {len(obj.vertices)}, "
          f"UVs: {len(obj.uvs)}, "
          f"Faces (triangles): {len(obj.faces)}")

    if auto_fit:
        print(f"      Applying --auto-fit...")
        fitted = auto_fit_vertices(obj.vertices, template, coord.int16_to_obj_vertex)
        obj = ObjMesh(
            vertices=fitted,
            uvs=obj.uvs,
            faces=obj.faces,
            face_groups=obj.face_groups,
            group_names=obj.group_names,
        )

    if len(obj.uvs) != len(obj.vertices):
        print(f"\nERROR: the .obj has {len(obj.vertices)} vertices but "
              f"{len(obj.uvs)} UVs. Each vertex needs exactly 1 UV.")
        print("The faces do not reference UVs (format f v/vt): export the .obj again with UVs.")
        sys.exit(1)

    counts_match = (len(obj.vertices) == total_v_template)
    if not counts_match and not allow_recount:
        print(f"\nERROR: vertex count mismatch: obj={len(obj.vertices)}, "
              f"template={total_v_template}")
        print("Use --allow-recount to import an .obj with a different count.")
        sys.exit(1)

    # [3-4] Partitioning =====================================================
    print(f"\n[3/7] Calculating vertex distribution across parts...")
    try:
        (work_vertices, work_uvs, work_faces,
         part_sizes, effective_parts, n_parts) = _partition(
            profile, obj, template, counts_match, allow_recount,
            part_sizes_override, max_verts_per_part,
            use_groups, match_template, auto_fit,
        )
    except ValueError as e:
        # User setup errors (groups != parts, wrong --part-sizes sum, etc.)
        # — a clean message instead of a traceback.
        print(f"\nERROR: {e}")
        sys.exit(1)
    part_ranges = compute_new_ranges_from_sizes(part_sizes)
    for i, (s, e) in enumerate(part_ranges):
        print(f"        Part {i}: vertices {s}..{e-1} ({e-s} v)")

    for i, sz in enumerate(part_sizes):
        if sz > MAX_VERTEX_COUNT_PER_PART:
            print(f"\nERROR: Part {i} has {sz} vertices "
                  f"(maximum: {MAX_VERTEX_COUNT_PER_PART}).")
            print("Reduce the number of faces or increase the number of parts.")
            sys.exit(1)

    print(f"\n[4/7] Assigning triangles to parts...")
    try:
        tris_per_part = assign_triangles_to_parts(work_faces, part_ranges)
    except ValueError as e:
        if counts_match:
            # Fallback: vertices in the wrong order (e.g. made by a simplifier)
            print(f"\nWARNING: the vertex count is right but the order does not match.")
            print(f"       Using automatic BFS partitioning...")
            work_vertices, work_uvs, work_faces, part_sizes = partition_mesh_by_faces(
                work_vertices, work_uvs, work_faces, n_parts
            )
            for i, sz in enumerate(part_sizes):
                if sz > MAX_VERTEX_COUNT_PER_PART:
                    print(f"\nERROR: Part {i} has {sz} vertices after BFS "
                          f"(max: {MAX_VERTEX_COUNT_PER_PART}).")
                    sys.exit(1)
            part_ranges = compute_new_ranges_from_sizes(part_sizes)
            tris_per_part = assign_triangles_to_parts(work_faces, part_ranges)
        else:
            print(f"\nERROR: {e}")
            sys.exit(1)

    for i, tris in enumerate(tris_per_part):
        print(f"      Part {i}: {len(tris)} faces (triangles)")

    # [5] Normals ============================================================
    if recalculate_normals:
        print(f"\n[5/7] Recalculating vertex normals from geometry...")
        float_normals = compute_vertex_normals(work_vertices, work_faces)
        print(f"      {len(float_normals)} normals calculated.")
    else:
        print(f"\n[5/7] Preserving template normals...")
        float_normals = None

    # Float normals used ONLY to orient the mesh in connected mode — if the
    # user did not ask to recalculate them, we compute them here anyway (the
    # orientation needs a reference for "front").
    orient_normals = None
    if strip_mode == "connected":
        orient_normals = (float_normals if float_normals is not None
                          else compute_vertex_normals(work_vertices, work_faces))
        print(f"      strip_mode=connected (default): connected tristrips "
              f"(coherent orientation + winding-aware).")

    # [6] Rebuilds the parts =================================================
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
                # Keeps the template normal if there is one, otherwise a fallback
                if i < len(template.parts) and v_local < len(template.parts[i].normals):
                    new_normals_int.append(template.parts[i].normals[v_local])
                else:
                    new_normals_int.append((0, 0, NORMAL_SCALE))

        if preserve_strips and _part_is_faithful(
                part, new_vc, new_verts_int, new_uvs_int, new_normals_int,
                tris_per_part[i]):
            # The geometry matches the template -> reuse the original part
            # (keeps the game's connected strip) => identical bytes.
            new_part = part
            print(f"      Part {i}: {part.vertex_count} v IDENTICAL to the template "
                  f"— original strip kept (zero-diff)")
        else:
            part_triangles = tris_per_part[i]
            if strip_mode == "connected":
                # Turns the local triangles to face FORWARD (coherent +
                # normals) before making strips — a precondition of the
                # connected encoder.
                from ..model.strip_connected import orient_for_front
                # orient_normals was computed above whenever strip_mode==connected.
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
                # Strip overflow (>~340 tris/part) or vc overflow (>255). A
                # clean message that names the part, instead of a traceback.
                print(f"\nERROR in Part {i}: {e}")
                print("Reduce the mesh density (decimate) or use more parts "
                      "(--max-verts-per-part).")
                sys.exit(1)
            size_diff = new_part.size - part.size
            diff_str = f"{size_diff:+d}" if size_diff != 0 else "(equal)"
            print(f"      Part {i}: {part.vertex_count} -> {new_vc} v, "
                  f"size {part.size} -> {new_part.size} {diff_str}, "
                  f"{len(tris_per_part[i])} tris")
        new_parts.append(new_part)

    # [7] Patches and writing ================================================
    print(f"\n[7/7] Writing .bin...")
    new_pre_parts = template.pre_parts_bytes
    if len(effective_parts) != len(template.parts):
        new_pre_parts = patch_total_parts(
            template.pre_parts_bytes, template.offset_file_1, len(effective_parts)
        )
        print(f"      total_parts updated: "
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

    # Fixes the absolute pointers in the container if parts_end changed
    # (face: parts_end/parts_end-16; trophy: section directory + outer header)
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
        # End of the parts in the model header (+0x2C, relative to the model)
        # — face and trophy. Written AFTER patch_resize: its scan compares
        # against the template values and could patch this one again if they
        # happened to match.
        new_payload = patch_parts_end(new_payload, template.offset_file_1, new_parts_end)
        print(f"      Model header parts_end (rel.): "
              f"0x{new_parts_end - template.offset_file_1:X}")
    else:
        print(f"      Parts with identical size — no pointers to fix")

    compress_bin(new_payload, outer_header, trailing, output_bin_path)
    print(f"\n=== COMPLETED SUCCESSFULLY ===")
    print(f"Generated file: {output_bin_path}")


# ============================================================================
# Helper: detects a faithful roundtrip (strip passthrough)
# ============================================================================

def _part_is_faithful(part, new_vc, new_verts_int, new_uvs_int,
                      new_normals_int, new_triangles) -> bool:
    """
    True if the new geometry matches the template part EXACTLY: same vc, same
    int16 vertices/UVs/normals, and the same SET of triangles that the
    original strip decodes into. In that case the original strip can be kept
    (byte-identical roundtrip).

    Triangles are compared as a set of frozensets (order and winding are
    ignored), because the strip decoder flips and orders them differently from
    the .obj — what matters for keeping the strip is that they are the SAME
    triangles.
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
# Helper: picks the partition strategy
# ============================================================================

def _partition(
    profile: AssetProfile,
    obj: ObjMesh, template: Model, counts_match: bool, allow_recount: bool,
    part_sizes_override: Optional[List[int]], max_verts_per_part: Optional[int],
    use_groups: bool, match_template: bool, auto_fit: bool,
) -> Tuple[list, list, list, List[int], list, int]:
    """Holds the logic that picks the partition strategy. Returns:
        (work_vertices, work_uvs, work_faces, part_sizes,
         effective_parts, n_parts).
    """
    n_parts = len(template.parts)
    effective_parts = list(template.parts)

    if counts_match:
        # Ideal case: the .obj count matches the template
        sizes = [p.vertex_count for p in template.parts]
        print(f"      Count matches the template — using the original distribution.")
        return obj.vertices, obj.uvs, obj.faces, sizes, effective_parts, n_parts

    if part_sizes_override is not None:
        # The user gave the sizes by hand
        if len(part_sizes_override) != n_parts:
            raise ValueError(
                f"--part-sizes: {len(part_sizes_override)} sizes given but "
                f"the template has {n_parts} parts."
            )
        if sum(part_sizes_override) != len(obj.vertices):
            raise ValueError(
                f"--part-sizes: the sum {sum(part_sizes_override)} is different "
                f"from the number of vertices in the .obj ({len(obj.vertices)})."
            )
        return obj.vertices, obj.uvs, obj.faces, part_sizes_override, effective_parts, n_parts

    n_obj_groups = len(obj.group_names)
    if use_groups and n_obj_groups > 1:
        if n_obj_groups != n_parts:
            raise ValueError(
                f"The OBJ has {n_obj_groups} groups but the template has {n_parts} parts."
            )
        print(f"      Partitioning by {n_obj_groups} OBJ groups...")
        work_v, work_u, work_f, sizes = partition_by_obj_groups(
            obj.vertices, obj.uvs, obj.faces, obj.face_groups, n_obj_groups,
        )
        _log_seam_stats(obj.vertices, work_v)
        return work_v, work_u, work_f, sizes, effective_parts, n_parts

    if match_template:
        print(f"      Partitioning by nearest neighbour of the template...")
        if not auto_fit:
            print(f"      [WARNING] --match-template works better with --auto-fit")
        work_v, work_u, work_f, sizes = partition_by_template(
            obj.vertices, obj.uvs, obj.faces, template,
            profile.coord.int16_to_obj_vertex,
        )
        _log_seam_stats(obj.vertices, work_v)
        return work_v, work_u, work_f, sizes, effective_parts, n_parts

    if use_groups and n_obj_groups <= 1:
        print(f"      [WARNING] --use-groups was asked but the .obj has no 'g'/'o' groups. "
              f"Falling back to automatic BFS. In Blender: split the face into "
              f"{n_parts} objects and export a multi-object .obj.")

    # Default: BFS by adjacency. No part may go over `cap` vertices: the VIF
    # limit (255), or the --max-verts-per-part value. Only that option may add
    # parts beyond the template.
    cap = MAX_VERTEX_COUNT_PER_PART
    if max_verts_per_part is not None:
        if max_verts_per_part < 3:
            raise ValueError("--max-verts-per-part must be at least 3 (one triangle).")
        if max_verts_per_part > MAX_VERTEX_COUNT_PER_PART:
            print(f"      [WARNING] --max-verts-per-part {max_verts_per_part} is above "
                  f"the VIF limit: using {MAX_VERTEX_COUNT_PER_PART}.")
            cap = MAX_VERTEX_COUNT_PER_PART
        else:
            cap = max_verts_per_part
        # The fewest parts possible: stop early if even that is too many
        n_parts = max(n_parts, math.ceil(len(obj.vertices) / cap))
        _check_max_parts(profile, n_parts, cap, len(obj.vertices))

    print(f"      Partitioning mesh by faces (BFS) into {n_parts} groups...")
    work_v, work_u, work_f, sizes = partition_mesh_by_faces(
        obj.vertices, obj.uvs, obj.faces, n_parts, max_verts=cap,
    )
    if len(sizes) > n_parts:
        # The planned parts are full (seam copies and scattered leftovers
        # need more vertices than the average).
        if max_verts_per_part is None:
            if profile.max_parts is None:
                hint = "Decimate the mesh, or use --max-verts-per-part 255 to add parts."
            elif n_parts < profile.max_parts:
                hint = (f"Decimate the mesh, or use --max-verts-per-part to add parts "
                        f"(at most {profile.max_parts} for a {profile.name}).")
            else:
                hint = (f"Decimate the mesh (a {profile.name} has at most "
                        f"{profile.max_parts} parts).")
            raise ValueError(
                f"the mesh does not fit in the {n_parts} parts of the template "
                f"with at most {cap} vertices per part (it needs {len(sizes)} "
                f"parts). {hint}")
        print(f"      The {n_parts} parts are full (max {cap} v each): "
              f"{len(sizes)} parts needed")
        n_parts = len(sizes)
        _check_max_parts(profile, n_parts, cap, len(obj.vertices))

    if n_parts > len(template.parts):
        donor = template.parts[-1]
        effective_parts = list(template.parts) + [
            clone_part_structure(donor) for _ in range(n_parts - len(template.parts))
        ]
        print(f"      Parts added: {len(template.parts)} -> {n_parts}")
    _log_seam_stats(obj.vertices, work_v)
    return work_v, work_u, work_f, sizes, effective_parts, n_parts


def _check_max_parts(profile: AssetProfile, n_needed: int, cap: int,
                     n_vertices: int) -> None:
    """Stops if --max-verts-per-part needs more parts than the asset allows
    (faces: 8 — Bug 12)."""
    if profile.max_parts is None or n_needed <= profile.max_parts:
        return
    # A lower bound: the seam copies may need even more
    min_vc = max(math.ceil(n_vertices / profile.max_parts), cap + 1)
    print(f"\nERROR: --max-verts-per-part {cap} needs "
          f"{n_needed} parts, but {profile.name} supports at most "
          f"{profile.max_parts} (byte[0x04]=8 in all face examples).")
    print(f"      With > {profile.max_parts} parts the face becomes INVISIBLE.")
    print(f"      Solutions:")
    print(f"        1. Raise --max-verts-per-part (it needs at least {min_vc})")
    print(f"        2. Remove --max-verts-per-part (automatic distribution)")
    print(f"        3. Reduce the number of vertices in the .obj "
          f"(max ~{MAX_VERTEX_COUNT_PER_PART * profile.max_parts})")
    sys.exit(1)


def _log_seam_stats(orig, new):
    dup = len(new) - len(orig)
    print(f"      Vertices: {len(orig)} -> {len(new)} "
          f"({dup:+d} duplicated at seams)")
