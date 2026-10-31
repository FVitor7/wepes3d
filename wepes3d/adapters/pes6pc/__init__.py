"""
pes6pc — export de FACE e TROFEU do PES6/WE PC para .obj.

PC e' "pasta de modelos" (como estadio/kit): um .bin/.str = 1+ modelos
(magic 20050420). FACE = 1 modelo; TROFEU = N modelos (partes: taca, base...).
Por isso a API espelha a de estadio/kit (list/export/complete/parts) e usa as
MESMAS flags na CLI (--list/--model/--complete/--parts/--groups).

SO export — PC nao tem import (.obj -> .bin) por enquanto.

    from wepes3d import (
        list_pc, export_pc, export_pc_complete, export_pc_parts,
    )
    list_pc("pl.str")                                  # estrutura (partes)
    export_pc_complete("pl.str", "trofeu.obj")         # todas as partes
    export_pc("pl.str", "taca.obj", model=0)           # so a parte 0
    export_pc("Kroos.bin", "rosto.obj")                # face (1 modelo)
"""

from typing import List, Optional, Tuple

from ...shared.io import decompress_bin, write_obj
from .reader import find_parts, parse_model

Part = Tuple[List[Tuple[float, float, float]],
             List[Tuple[float, float]],
             List[Tuple[int, int, int]]]


# ============================================================================
# Leitura
# ============================================================================

def _load_parts(bin_path: str) -> List[Part]:
    """Descomprime o .bin/.str e parseia todas as partes (modelos PES6 PC)."""
    payload, _, _ = decompress_bin(bin_path)
    offs = find_parts(payload)
    if not offs:
        raise ValueError(
            f"{bin_path}: nenhum modelo PES6 PC (magic 20050420) encontrado. "
            "Nao parece um .bin/.str de face/trofeu do PES6 PC.")
    return [parse_model(payload, o) for o in offs]


def _dedup(parts: List[Part]) -> List[Part]:
    """Remove partes com geometria identica a uma anterior."""
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
    """Junta partes num so mesh, deslocando indices. Devolve (verts, uvs,
    faces, groups) onde groups = [(nome, face_inicio, qtd_faces)]."""
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
# Estrutura / listagem
# ============================================================================

def pc_index(bin_path: str) -> List[dict]:
    """Lista as partes: [{index, verts, faces}, ...]."""
    parts = _load_parts(bin_path)
    return [{"index": i, "verts": len(v), "faces": len(f)}
            for i, (v, _u, f) in enumerate(parts)]


def list_pc(bin_path: str) -> None:
    """Imprime a estrutura (partes) do .bin/.str PC."""
    idx = pc_index(bin_path)
    kind = "face (1 modelo)" if len(idx) == 1 else f"trofeu ({len(idx)} partes)"
    print(f"{bin_path}: PES6 PC — {kind}")
    for e in idx:
        print(f"  parte {e['index']:>2}: verts {e['verts']:>5}  faces {e['faces']:>5}")


# ============================================================================
# Export
# ============================================================================

def export_pc(bin_path: str, obj_path: str, model: int = 0,
              block: Optional[int] = None, groups: bool = False,
              dedup: bool = False, write_mtl: bool = True) -> None:
    """Exporta UMA parte (modelo `model`). `block` e' ignorado (PC = 1
    container). `groups` aqui nao muda nada (1 parte = 1 objeto)."""
    parts = _load_parts(bin_path)
    if dedup:
        parts = _dedup(parts)
    if not (0 <= model < len(parts)):
        raise IndexError(f"parte {model} invalida (0..{len(parts)-1}).")
    v, u, f = parts[model]
    write_obj(obj_path, v, u, f, write_mtl=write_mtl,
              comment=f"PES6 PC parte {model} de {bin_path}")
    print(f"[export] pes6pc parte {model}: {len(v)} v, {len(f)} faces -> {obj_path}")


def export_pc_complete(bin_path: str, obj_path: str, dedup: bool = False,
                       write_mtl: bool = True) -> None:
    """Exporta TODAS as partes num so .obj (1 objeto `o part_NN` por parte)."""
    parts = _load_parts(bin_path)
    if dedup:
        parts = _dedup(parts)
    verts, uvs, faces, groups = _merge(parts)
    write_obj(obj_path, verts, uvs, faces, write_mtl=write_mtl,
              comment=f"PES6 PC completo ({len(parts)} partes) de {bin_path}",
              groups=groups)
    print(f"[export] pes6pc completo: {len(parts)} partes, {len(verts)} v, "
          f"{len(faces)} faces -> {obj_path}")


def export_pc_parts(bin_path: str, prefix: str, groups: bool = False,
                    dedup: bool = False, write_mtl: bool = True) -> None:
    """Exporta um .obj por parte: `<prefix>_partNN.obj`."""
    parts = _load_parts(bin_path)
    if dedup:
        parts = _dedup(parts)
    for i, (v, u, f) in enumerate(parts):
        out = f"{prefix}_part{i:02d}.obj"
        write_obj(out, v, u, f, write_mtl=write_mtl,
                  comment=f"PES6 PC parte {i} de {bin_path}")
        print(f"[export] pes6pc parte {i}: {len(v)} v, {len(f)} faces -> {out}")


__all__ = [
    "pc_index", "list_pc",
    "export_pc", "export_pc_complete", "export_pc_parts",
]
