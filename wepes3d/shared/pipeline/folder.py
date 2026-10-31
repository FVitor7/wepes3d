"""
GENERIC export of a PES "model folder" (stadium, kit) to .obj.

Stadiums and kits have the SAME structure (a container/model folder of
`03 00 FF FF` models, read by the universal reader
`model.reader.read_model_geometry`); they ONLY differ in the `CoordSpace`.
This module holds the export logic, driven by `coord` + `label`; the
`stadiums/` and `kits/` adapters are thin wrappers.
"""

import os
from typing import List, Optional, Tuple

from ..io.obj_write import write_obj
from ..model.reader import read_model_geometry, read_model_parts
from ..io.pes_archive import load_blocks, model_offsets, is_container
from ..geometry.coords import CoordSpace


def _merge_parts(parts):
    """[(verts,uvs,faces_local),...] -> (verts, uvs, faces, groups) with 1
    'part_NN' group per part (for `write_obj(groups=...)`)."""
    verts, uvs, faces, groups = [], [], [], []
    vcount = 0
    for pi, (pv, pu, pf) in enumerate(parts):
        fstart = len(faces)
        verts.extend(pv)
        uvs.extend(pu)
        faces.extend((a + vcount, b + vcount, c + vcount) for (a, b, c) in pf)
        vcount += len(pv)
        groups.append((f"part_{pi:02d}", fstart, len(faces) - fstart))
    return verts, uvs, faces, groups


def flat_models(path: str):
    """[(block, model_in_block, payload, model_offset), ...] of ALL the 3D
    models in the file (blocks without a model — textures/data — are
    ignored)."""
    out = []
    for bi, payload in enumerate(load_blocks(path)):
        for mi, mo in enumerate(model_offsets(payload)):
            out.append((bi, mi, payload, mo))
    return out


def index(path: str) -> List[Tuple[int, int, int]]:
    """[(block, model, total_parts), ...] (total_parts from the model header, +0x20)."""
    import struct
    out = []
    for bi, payload in enumerate(load_blocks(path)):
        for mi, mo in enumerate(model_offsets(payload)):
            nparts = struct.unpack_from("<I", payload, mo + 0x20)[0]
            out.append((bi, mi, nparts))
    return out


def list_models(path: str, coord: CoordSpace, label: str) -> None:
    """Prints the file structure (blocks / models / parts / v / faces)."""
    blocks = load_blocks(path)
    with open(path, "rb") as f:
        kind = "container" if is_container(f.read(4)) else "compressed block"
    print(f"{path}: {kind} ({label}), {len(blocks)} block(s)")
    for bi, payload in enumerate(blocks):
        offs = model_offsets(payload)
        print(f"  block {bi}: {len(offs)} model(s) ({len(payload)} bytes)")
        for mi, mo in enumerate(offs):
            v, u, f, sk, np = read_model_geometry(coord, payload, mo)
            warn = f"  [{sk}/{np} parts skipped]" if sk else ""
            print(f"     model {mi}: {np} parts -> {len(v)} v, {len(f)} faces{warn}")


def export_model(path: str, obj_path: str, coord: CoordSpace, label: str,
                 model: int = 0, block: Optional[int] = None, write_mtl: bool = True,
                 groups: bool = False, dedup: bool = False) -> None:
    """Exports ONE model. `model` is a GLOBAL index (flattened over the blocks
    that have models); if `block` is given, it is the index inside that block.
    `groups=True` writes 1 object (`o part_NN`) per part. `dedup=True` removes
    duplicated double-sided panels."""
    flat = flat_models(path)
    if not flat:
        raise ValueError(f"{path}: no 3D model found (texture/data?).")
    if block is not None:
        cands = [t for t in flat if t[0] == block]
        if not (0 <= model < len(cands)):
            raise ValueError(f"block {block}: model {model} does not exist "
                             f"({len(cands)} models in the block).")
        bi, mi, payload, mo = cands[model]
    else:
        if not (0 <= model < len(flat)):
            raise ValueError(f"model {model} does not exist ({len(flat)} models "
                             f"in the file). Use the list command to see them.")
        bi, mi, payload, mo = flat[model]

    comment = f"{label} block {bi} model {mi} of {path}"
    parts, skipped, nparts = read_model_parts(coord, payload, mo, dedup=dedup)
    verts, uvs, faces, grp = _merge_parts(parts)
    write_obj(obj_path, verts, uvs, faces, write_mtl=write_mtl, comment=comment,
              groups=grp if groups else None)
    extra = (f", {len(parts)} objects" if groups else "") + (" (dedup)" if dedup else "")
    print(f"[export] {label} b{bi}m{mi}: {len(verts)} v, {len(faces)} faces"
          f"{extra} -> {obj_path}")
    if skipped:
        print(f"  [WARNING] {skipped}/{nparts} part(s) skipped.")
    if block is None and len(flat) > 1:
        print(f"  (the file has {len(flat)} models; --all joins them all, "
              f"--parts writes one .obj per model, the list command shows the structure)")


def export_complete(path: str, obj_path: str, coord: CoordSpace, label: str,
                    write_mtl: bool = True, dedup: bool = False) -> None:
    """Exports ALL models (all blocks) into a single .obj."""
    verts: list = []
    uvs: list = []
    faces: list = []
    vcount = 0
    skipped_total = 0
    nmodels = 0
    for payload in load_blocks(path):
        for mo in model_offsets(payload):
            v, u, f, sk, np = read_model_geometry(coord, payload, mo, dedup=dedup)
            verts.extend(v)
            uvs.extend(u)
            faces.extend((a + vcount, b + vcount, c + vcount) for (a, b, c) in f)
            vcount += len(v)
            skipped_total += sk
            nmodels += 1
    write_obj(obj_path, verts, uvs, faces, write_mtl=write_mtl,
              comment=f"{label} COMPLETE ({nmodels} models) of {path}")
    print(f"[export] {label} complete: {nmodels} models, {len(verts)} v, "
          f"{len(faces)} faces{' (dedup)' if dedup else ''} -> {obj_path}")
    if skipped_total:
        print(f"  [WARNING] {skipped_total} part(s) skipped in total.")


def export_parts(path: str, out_prefix: str, coord: CoordSpace, label: str,
                 write_mtl: bool = True, groups: bool = False,
                 dedup: bool = False) -> List[str]:
    """One .obj per model: `{out_prefix}_b{B}m{M}.obj`. `groups`/`dedup` are
    passed on. Returns the paths."""
    parent = os.path.dirname(out_prefix)
    if parent:
        os.makedirs(parent, exist_ok=True)
    written: List[str] = []
    for bi, payload in enumerate(load_blocks(path)):
        for mi, mo in enumerate(model_offsets(payload)):
            outp = f"{out_prefix}_b{bi}m{mi}.obj"
            parts, sk, np = read_model_parts(coord, payload, mo, dedup=dedup)
            v, u, f, grp = _merge_parts(parts)
            write_obj(outp, v, u, f, write_mtl=write_mtl,
                      comment=f"{label} block {bi} model {mi} of {path}",
                      groups=grp if groups else None)
            written.append(outp)
            ex = (f", {len(parts)} objects" if groups else "") + (" (dedup)" if dedup else "")
            print(f"[export] {label} b{bi}m{mi}: {len(v)} v, {len(f)} faces{ex} -> {outp}")
    return written


def export_scene(paths: List[str], obj_path: str, coord: CoordSpace, label: str,
                 write_mtl: bool = True) -> None:
    """Joins SEVERAL files (all blocks x models) into ONE .obj."""
    verts: list = []
    uvs: list = []
    faces: list = []
    vcount = 0
    total_models = 0
    print(f"[scene] building {len(paths)} file(s) into {obj_path} ...")
    for path in paths:
        f0 = len(faces)
        v0 = vcount
        nmod = 0
        for payload in load_blocks(path):
            for mo in model_offsets(payload):
                v, u, f, sk, np = read_model_geometry(coord, payload, mo)
                verts.extend(v)
                uvs.extend(u)
                faces.extend((a + vcount, b + vcount, c + vcount) for (a, b, c) in f)
                vcount += len(v)
                nmod += 1
                total_models += 1
        tag = (f"{nmod} model(s), +{vcount - v0} v / +{len(faces) - f0} faces"
               if nmod else "no 3D model (texture/data)")
        print(f"  {path}: {tag}")
    write_obj(obj_path, verts, uvs, faces, write_mtl=write_mtl,
              comment=f"{label} SCENE: {len(paths)} files, {total_models} models")
    print(f"[scene] total: {total_models} models, {len(verts)} v, "
          f"{len(faces)} faces -> {obj_path}")
