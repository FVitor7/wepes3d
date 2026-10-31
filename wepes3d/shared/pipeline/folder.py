"""
Export GENERICO de uma "pasta de modelos" PES (estadio, kit) para .obj.

Estadio e kit têm a MESMA estrutura (container/pasta de modelos `03 00 FF FF`
lidos pelo leitor universal `pipeline.read_model_geometry`); diferem APENAS no
`CoordSpace`. Este modulo concentra a logica de export parametrizada por `coord`
+ `label`; `stadium/` e `kit/` sao adapters finos.
"""

import os
from typing import List, Optional, Tuple

from ..io.obj_write import write_obj
from ..model.reader import read_model_geometry, read_model_parts
from ..io.pes_archive import load_blocks, model_offsets, is_container
from ..geometry.coords import CoordSpace


def _merge_parts(parts):
    """[(verts,uvs,faces_local),...] -> (verts, uvs, faces, groups) com 1 grupo
    'part_NN' por part (para `write_obj(groups=...)`)."""
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
    """[(bloco, modelo_no_bloco, payload, model_offset), ...] de TODOS os modelos
    3D do arquivo (blocos sem modelo — texturas/dados — sao ignorados)."""
    out = []
    for bi, payload in enumerate(load_blocks(path)):
        for mi, mo in enumerate(model_offsets(payload)):
            out.append((bi, mi, payload, mo))
    return out


def index(path: str) -> List[Tuple[int, int, int]]:
    """[(bloco, modelo, total_parts), ...] (total_parts do header do modelo, +0x20)."""
    import struct
    out = []
    for bi, payload in enumerate(load_blocks(path)):
        for mi, mo in enumerate(model_offsets(payload)):
            nparts = struct.unpack_from("<I", payload, mo + 0x20)[0]
            out.append((bi, mi, nparts))
    return out


def list_models(path: str, coord: CoordSpace, label: str) -> None:
    """Imprime a estrutura do arquivo (blocos / modelos / parts / v / faces)."""
    blocks = load_blocks(path)
    with open(path, "rb") as f:
        kind = "container" if is_container(f.read(4)) else "bloco comprimido"
    print(f"{path}: {kind} ({label}), {len(blocks)} bloco(s)")
    for bi, payload in enumerate(blocks):
        offs = model_offsets(payload)
        print(f"  bloco {bi}: {len(offs)} modelo(s) ({len(payload)} bytes)")
        for mi, mo in enumerate(offs):
            v, u, f, sk, np = read_model_geometry(coord, payload, mo)
            warn = f"  [{sk}/{np} parts puladas]" if sk else ""
            print(f"     modelo {mi}: {np} parts -> {len(v)} v, {len(f)} faces{warn}")


def export_model(path: str, obj_path: str, coord: CoordSpace, label: str,
                 model: int = 0, block: Optional[int] = None, write_mtl: bool = True,
                 groups: bool = False, dedup: bool = False) -> None:
    """Exporta UM modelo. `model` e' indice GLOBAL (achatado sobre os blocos com
    modelo); se `block` for dado, e' o indice dentro do bloco.
    `groups=True` escreve 1 objeto (`o part_NN`) por part. `dedup=True` remove
    paineis double-sided duplicados."""
    flat = flat_models(path)
    if not flat:
        raise ValueError(f"{path}: nenhum modelo 3D encontrado (textura/dados?).")
    if block is not None:
        cands = [t for t in flat if t[0] == block]
        if not (0 <= model < len(cands)):
            raise ValueError(f"bloco {block}: modelo {model} inexistente "
                             f"({len(cands)} modelos no bloco).")
        bi, mi, payload, mo = cands[model]
    else:
        if not (0 <= model < len(flat)):
            raise ValueError(f"modelo {model} inexistente ({len(flat)} modelos "
                             f"no arquivo). Use --list para ver.")
        bi, mi, payload, mo = flat[model]

    comment = f"{label} bloco {bi} modelo {mi} de {path}"
    parts, skipped, nparts = read_model_parts(coord, payload, mo, dedup=dedup)
    verts, uvs, faces, grp = _merge_parts(parts)
    write_obj(obj_path, verts, uvs, faces, write_mtl=write_mtl, comment=comment,
              groups=grp if groups else None)
    extra = (f", {len(parts)} objetos" if groups else "") + (" (dedup)" if dedup else "")
    print(f"[export] {label} b{bi}m{mi}: {len(verts)} v, {len(faces)} faces"
          f"{extra} -> {obj_path}")
    if skipped:
        print(f"  [AVISO] {skipped}/{nparts} part(s) puladas.")
    if block is None and len(flat) > 1:
        print(f"  (o arquivo tem {len(flat)} modelos; --complete junta todos, "
              f"--parts gera um .obj por modelo, --list mostra a estrutura)")


def export_complete(path: str, obj_path: str, coord: CoordSpace, label: str,
                    write_mtl: bool = True, dedup: bool = False) -> None:
    """Exporta TODOS os modelos (todos os blocos) num unico .obj."""
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
              comment=f"{label} COMPLETO ({nmodels} modelos) de {path}")
    print(f"[export] {label} completo: {nmodels} modelos, {len(verts)} v, "
          f"{len(faces)} faces{' (dedup)' if dedup else ''} -> {obj_path}")
    if skipped_total:
        print(f"  [AVISO] {skipped_total} part(s) puladas no total.")


def export_parts(path: str, out_prefix: str, coord: CoordSpace, label: str,
                 write_mtl: bool = True, groups: bool = False,
                 dedup: bool = False) -> List[str]:
    """Um .obj por modelo: `{out_prefix}_b{B}m{M}.obj`. `groups`/`dedup` repassados.
    Devolve os caminhos."""
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
                      comment=f"{label} bloco {bi} modelo {mi} de {path}",
                      groups=grp if groups else None)
            written.append(outp)
            ex = (f", {len(parts)} objetos" if groups else "") + (" (dedup)" if dedup else "")
            print(f"[export] {label} b{bi}m{mi}: {len(v)} v, {len(f)} faces{ex} -> {outp}")
    return written


def export_scene(paths: List[str], obj_path: str, coord: CoordSpace, label: str,
                 write_mtl: bool = True) -> None:
    """Junta VARIOS arquivos (todos os blocos x modelos) num UNICO .obj."""
    verts: list = []
    uvs: list = []
    faces: list = []
    vcount = 0
    total_models = 0
    print(f"[cena] montando {len(paths)} arquivo(s) em {obj_path} ...")
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
        tag = (f"{nmod} modelo(s), +{vcount - v0} v / +{len(faces) - f0} faces"
               if nmod else "sem modelo 3D (textura/dados)")
        print(f"  {path}: {tag}")
    write_obj(obj_path, verts, uvs, faces, write_mtl=write_mtl,
              comment=f"{label} CENA: {len(paths)} arquivos, {total_models} modelos")
    print(f"[cena] total: {total_models} modelos, {len(verts)} v, "
          f"{len(faces)} faces -> {obj_path}")
