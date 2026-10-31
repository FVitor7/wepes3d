"""
pes6pc — export of PES6/WE PC FACES and TROPHIES to .obj.

PC works as a "model folder" (like stadiums/kits): one .bin/.str = 1+ models
(magic 20050420). FACE = 1 model; TROPHY = N models (parts: cup, base...).
That is why the API mirrors the stadium/kit one (list/export/complete/parts)
and uses the SAME CLI options (the `list` command and
--all/--model/--parts/--groups).

Export ONLY — PC has no import (.obj -> .bin) for now.

    from wepes3d import (
        list_pc, export_pc, export_pc_complete, export_pc_parts,
    )
    list_pc("pl.str")                                  # structure (parts)
    export_pc_complete("pl.str", "trophy.obj")         # all the parts
    export_pc("pl.str", "cup.obj", model=0)            # only part 0
    export_pc("Kroos.bin", "face.obj")                 # face (1 model)
"""

from typing import List, Optional, Tuple

from ...shared.io import decompress_bin, write_obj
from .reader import find_parts, parse_model

Part = Tuple[List[Tuple[float, float, float]],
             List[Tuple[float, float]],
             List[Tuple[int, int, int]]]


# ============================================================================
# Reading
# ============================================================================

def _load_parts(bin_path: str) -> List[Part]:
    """Decompresses the .bin/.str and parses all parts (PES6 PC models)."""
    payload, _, _ = decompress_bin(bin_path)
    offs = find_parts(payload)
    if not offs:
        raise ValueError(
            f"{bin_path}: no PES6 PC model (magic 20050420) found. "
            "This does not look like a PES6 PC face/trophy .bin/.str.")
    return [parse_model(payload, o) for o in offs]


def _dedup(parts: List[Part]) -> List[Part]:
    """Removes parts whose geometry is the same as an earlier part."""
    seen = set()
    out = []
    for verts, uvs, faces in parts:
        key = (tuple(verts), tuple(faces))
        if key in seen:
            continue
        seen.add(key)
        out.append((verts, uvs, faces))
    return out


def _merge(parts: List[Part]):
    """Joins the parts into one mesh, shifting the indices. Returns (verts,
    uvs, faces, groups) where groups = [(name, first_face, face_count)]."""
    verts, uvs, faces, groups = [], [], [], []
    v_base = 0
    for i, (pv, puv, pf) in enumerate(parts):
        fstart = len(faces)
        for (a, b, c) in pf:
            faces.append((a + v_base, b + v_base, c + v_base))
        verts.extend(pv)
        uvs.extend(puv)
        groups.append((f"part_{i:02d}", fstart, len(pf)))
        v_base += len(pv)
    return verts, uvs, faces, groups


# ============================================================================
# Structure / listing
# ============================================================================

def pc_index(bin_path: str) -> List[dict]:
    """Lists the parts: [{index, verts, faces}, ...]."""
    parts = _load_parts(bin_path)
    return [{"index": i, "verts": len(v), "faces": len(f)}
            for i, (v, _u, f) in enumerate(parts)]


def list_pc(bin_path: str) -> None:
    """Prints the structure (parts) of the PC .bin/.str."""
    idx = pc_index(bin_path)
    kind = "face (1 model)" if len(idx) == 1 else f"trophy ({len(idx)} parts)"
    print(f"{bin_path}: PES6 PC — {kind}")
    for e in idx:
        print(f"  part {e['index']:>2}: verts {e['verts']:>5}  faces {e['faces']:>5}")


# ============================================================================
# Export
# ============================================================================

def export_pc(bin_path: str, obj_path: str, model: int = 0,
              block: Optional[int] = None, groups: bool = False,
              dedup: bool = False, write_mtl: bool = True) -> None:
    """Exports ONE part (model `model`). `block` is ignored (PC = 1
    container). `groups` changes nothing here (1 part = 1 object)."""
    parts = _load_parts(bin_path)
    if dedup:
        parts = _dedup(parts)
    if not (0 <= model < len(parts)):
        raise IndexError(f"part {model} is not valid (0..{len(parts)-1}).")
    v, u, f = parts[model]
    write_obj(obj_path, v, u, f, write_mtl=write_mtl,
              comment=f"PES6 PC part {model} of {bin_path}")
    print(f"[export] pes6pc part {model}: {len(v)} v, {len(f)} faces -> {obj_path}")


def export_pc_complete(bin_path: str, obj_path: str, dedup: bool = False,
                       write_mtl: bool = True) -> None:
    """Exports ALL parts into one .obj (1 object `o part_NN` per part)."""
    parts = _load_parts(bin_path)
    if dedup:
        parts = _dedup(parts)
    verts, uvs, faces, groups = _merge(parts)
    write_obj(obj_path, verts, uvs, faces, write_mtl=write_mtl,
              comment=f"PES6 PC complete ({len(parts)} parts) of {bin_path}",
              groups=groups)
    print(f"[export] pes6pc complete: {len(parts)} parts, {len(verts)} v, "
          f"{len(faces)} faces -> {obj_path}")


def export_pc_parts(bin_path: str, prefix: str, groups: bool = False,
                    dedup: bool = False, write_mtl: bool = True) -> None:
    """Exports one .obj per part: `<prefix>_partNN.obj`."""
    parts = _load_parts(bin_path)
    if dedup:
        parts = _dedup(parts)
    for i, (v, u, f) in enumerate(parts):
        out = f"{prefix}_part{i:02d}.obj"
        write_obj(out, v, u, f, write_mtl=write_mtl,
                  comment=f"PES6 PC part {i} of {bin_path}")
        print(f"[export] pes6pc part {i}: {len(v)} v, {len(f)} faces -> {out}")


__all__ = [
    "pc_index", "list_pc",
    "export_pc", "export_pc_complete", "export_pc_parts",
]
