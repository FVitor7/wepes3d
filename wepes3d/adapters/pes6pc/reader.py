"""
Leitor do formato de modelo PES6/WE PC (magic 20050420).

PC e PS2 sao formatos binarios DIFERENTES — este leitor NAO usa o motor PS2
(`shared/model`, `shared/pipeline`); so a descompressao comum (`shared/io`).

Estrutura (eng. reversa, ver pes6_bin_to_obj.py / pes6_trophy_to_obj.py):

  * FACE/CABELO: o payload tem o modelo DIRETO — payload[8] aponta o magic
    20050420.
  * TROFEU: o payload e um container aninhado (00060100 externo ja
    descomprimido -> 00060000) com VARIOS modelos 20050420, um por PARTE
    (taca, base, alcas...).

Em ambos os casos cada modelo e lido igual: localizamos os modelos por scan do
magic e parseamos cada um com `parse_model` (ponteiros internos relativos ao
inicio do modelo).

Vertex groups: marcador `07 <m>` + 4xuint16 (total_tlist, vert_start,
total_verts, total_f). O 2o byte varia (face 0x05, trofeu 0x26); achamos qual
faz as somas fecharem (sum total_verts == vc, sum total_tlist == tri_total).
Indices do strip sao GLOBAIS (nao somar vert_start).
"""

import struct
from typing import List, Tuple

from .coords import raw_to_obj_vertex, raw_to_obj_uv

MODEL_MAGIC = bytes([0x20, 0x05, 0x04, 0x20])   # modelo PES6 PC

Vert = Tuple[float, float, float]
UV = Tuple[float, float]
Face = Tuple[int, int, int]


def find_parts(payload: bytes) -> List[int]:
    """Offsets de cada modelo PES6 PC (magic 20050420) no payload.

    Face -> 1 offset; trofeu -> N (um por parte). Scan robusto (nao depende de
    navegar o diretorio do container)."""
    parts = []
    pos = 0
    while True:
        f = payload.find(MODEL_MAGIC, pos)
        if f == -1:
            break
        parts.append(f)
        pos = f + 4
    return parts


def find_vertex_groups(hdr_block: bytes, vc: int, tri_total: int):
    """
    Tabela de vertex groups dentro do bloco header de um modelo.

    Cada grupo: `07 <m>` + 4xuint16 (total_tlist, vert_start, total_verts,
    total_f). Descobrimos o marcador <m> validando as somas. Devolve lista de
    (total_tlist, vert_start, total_verts, total_f) ou None.
    """
    candidates = {hdr_block[j + 1]
                  for j in range(len(hdr_block) - 9)
                  if hdr_block[j] == 0x07 and hdr_block[j + 1] != 0x00}
    for m in sorted(candidates):
        marker = bytes([0x07, m])
        entries = []
        pos = 0
        while True:
            f = hdr_block.find(marker, pos)
            if f == -1 or f + 10 > len(hdr_block):
                break
            tl, vsr, tv, tf = struct.unpack_from("<4H", hdr_block, f + 2)
            if 0 < tv <= vc and 0 < tl <= tri_total and vsr + tv <= vc:
                entries.append((tl, vsr, tv, tf))
            pos = f + 2
        if entries and sum(e[2] for e in entries) == vc \
                   and sum(e[0] for e in entries) == tri_total:
            return entries
    return None


def parse_model(payload: bytes, off1: int) -> Tuple[List[Vert], List[UV], List[Face]]:
    """
    Le UM modelo PES6 PC que comeca em `off1` (magic 20050420).
    Devolve (verts, uvs, faces) ja no espaco OBJ.
    """
    magic = payload[off1:off1 + 4]
    if magic != MODEL_MAGIC:
        raise ValueError(f"offset {off1:#x} nao tem magic de modelo PES6 PC "
                         f"(achei {magic.hex()}).")

    end_of_header, _, _mat_info, vertex_off, idx_off, header_start = \
        struct.unpack_from("<6I", payload, off1 + 4)
    end_of_header += off1
    vertex_off    += off1
    idx_off       += off1
    header_start  += off1

    vc = struct.unpack_from("<H", payload, vertex_off + 8)[0]
    tri_total = struct.unpack_from("<H", payload, idx_off)[0]

    # --- vertex groups (quebram o strip nos limites de grupo) ---
    hdr_block = payload[header_start:end_of_header]
    groups = find_vertex_groups(hdr_block, vc, tri_total)
    if groups is None:
        groups = [(tri_total, 0, vc, 0)]   # fallback: 1 grupo unico

    vg_ranges = []
    tri_counter = 0
    for total_tlist, _vs, _tv, _tf in groups:
        vg_ranges.append((tri_counter, tri_counter + total_tlist))
        tri_counter += total_tlist

    # --- vertices + UVs ---
    cursor = vertex_off + 8
    vc2, vs, _pad, _anim = struct.unpack_from("<H2BI", payload, cursor)
    cursor += 8

    verts: List[Vert] = []
    uvs: List[UV] = []
    for _ in range(vc2):
        raw_x, raw_y, raw_z = struct.unpack_from("<3f", payload, cursor)
        cursor += 12
        verts.append(raw_to_obj_vertex(raw_x, raw_y, raw_z))
        cursor += vs - 20            # padding / normais / pesos
        u, v = struct.unpack_from("<2f", payload, cursor)
        cursor += 8
        uvs.append(raw_to_obj_uv(u, v))

    # --- indices (triangle strip por grupo) ---
    tlist = struct.unpack_from(f"<{tri_total}H", payload, idx_off + 2)
    faces: List[Face] = []
    for ts, te in vg_ranges:
        strip = tlist[ts:te]
        for i in range(len(strip) - 2):
            a, b, c = strip[i], strip[i + 1], strip[i + 2]
            if a != b and b != c and a != c:    # pula degenerados (restart)
                faces.append((c, b, a))          # winding invertido (= plugin)

    return verts, uvs, faces
