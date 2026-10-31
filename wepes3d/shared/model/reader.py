"""
Leitor UNIVERSAL de geometria do modelo PES PS2 (verts/UVs/faces).

Tres niveis:
  * read_part_geometry  — uma part -> (verts_raw int16, uvs_raw int16, faces_local).
                          Ciente do formato (porta do `stadium_modifier.read_ps2_mdl_part`),
                          sem fallback; cobre face, trofeu sec0..8, estadio e kit.
  * read_model_parts    — todas as parts de um modelo, ja no espaco OBJ (recebe
                          o CoordSpace), SEM mesclar (1 entrada por part).
  * read_model_geometry — idem, porem MESCLADO num unico (verts, uvs, faces).

Compartilhado por face/trofeu (export), estadio e kit.
"""

import struct

from ..constants import VIF_STRIP_MARKER
from .parser import parse_model

# Separador de submesh = STCYCL CL=4 WL=1 (4 bytes): inicia cada sub-bloco de
# geometria de uma part.
_SUBMESH_SEP = bytes([0x04, 0x01, 0x00, 0x01])
_VSIZE = {0x69: 6, 0x68: 12, 0x65: 4, 0x6D: 8}   # bytes por elemento por CMD UNPACK


def read_part_geometry(payload, part):
    """
    Leitor de geometria UNIVERSAL de uma part (verts/UVs/faces), ciente do
    formato — sem fallback. Algoritmo do `stadium_modifier.py`
    (read_ps2_mdl_part), o decoder mais completo da comunidade. Cobre TODOS os
    casos observados (faces, trofeu sec0..8, estadio, kit) porque o caso simples
    eh apenas `total_submesh == 1`:

      - Estrutura: em `v_address` (= part + part_info_start) ha um sub-header;
        `total_submesh` em v_address+44; tabela de descritores (36 bytes cada);
        marcador STCYCL CL=4 WL=1 (`_SUBMESH_SEP`); depois N submeshes.
      - Cada submesh comeca por um tag VIF `H2B` (IMMED, NUM, CMD); o CMD diz o
        formato dos vertices: 0x69=V3-16 (int16, 6B), 0x68=V3-32 (int32, 12B).
        Normais e UV seguem (UV pode ter um bloco extra: `uv_type - v_type == 2`).
      - O strip indexa a UNIAO dos submeshes por ENDERECO da VU; a correcao
        `diff = max(idx) - total_verts + 1` recupera o indice global sem
        precisar do endereco base (single-block: diff == 0). Decode em janela
        deslizante com winding alternado.

    Escala/eixos NAO sao aplicados aqui (responsabilidade do `profile.coord`):
    retorna ints crus. Retorna (verts_raw[(s0,s1,s2)], uvs_raw[(u,v)],
    faces_local) ou None se a estrutura nao casar.
    """
    off = part.offset_in_payload
    size = part.size
    v_addr = off + part.part_info_start_raw
    tstrip_size = struct.unpack_from("<I", payload, off + 16)[0]
    if v_addr + 48 > off + size:
        return None
    total_sub = struct.unpack_from("<I", payload, v_addr + 44)[0]
    if not (1 <= total_sub < 4096):
        return None
    p = v_addr + 56 + 36 * total_sub
    if payload[p:p + 4] != _SUBMESH_SEP:
        return None
    p += 4

    verts, uvs = [], []
    end = off + size
    uv_end = p
    for sub in range(total_sub):
        if p + 4 > end:
            return None
        v_type, v_num, v_fmt = struct.unpack_from("<H2B", payload, p); p += 4
        vs = _VSIZE.get(v_fmt, 6)
        for _ in range(v_num):
            if v_fmt == 0x68:
                verts.append(struct.unpack_from("<iii", payload, p))
            else:
                verts.append(struct.unpack_from("<hhh", payload, p))
            p += vs
        if v_num % 2 and v_fmt == 0x69:
            p += 2
        _, _, n_fmt = struct.unpack_from("<H2B", payload, p); p += 4
        p += v_num * _VSIZE.get(n_fmt, 6)
        if v_num % 2 and n_fmt == 0x69:
            p += 2
        uv_type, _, uv_fmt = struct.unpack_from("<H2B", payload, p); p += 4
        if uv_type - v_type == 2:                 # bloco extra (cor/2a uv)
            p += v_num * _VSIZE.get(uv_fmt, 4)
            if v_num % 2 and uv_fmt == 0x69:
                p += 2
            uv_type, _, uv_fmt = struct.unpack_from("<H2B", payload, p); p += 4
        for _ in range(v_num):
            uvs.append(struct.unpack_from("<hh", payload, p)); p += 4
        uv_end = p
        while sub < total_sub - 1:                # pula ate o proximo separador
            if payload[p:p + 4] == _SUBMESH_SEP:
                p += 4
                break
            p += 4
            if p > end:
                return None

    vcounter = len(verts)
    ts = payload[uv_end:end].find(VIF_STRIP_MARKER)
    if ts < 0:
        return None
    sp = uv_end + ts + 8 + 4                       # marker(8) + tag(4)
    idx = list(struct.unpack_from(f"<{tstrip_size}H", payload, sp))

    def gv(c):
        return ((c & 0x7FFF) // 4) - 1
    if not idx:
        return None
    # diff calculado sobre TODOS os indices (kicks E restarts), como no stadium.
    # Usar so kicks dava off-by-1 em algumas parts (geometria embaralhada).
    diff = max(gv(c) for c in idx) - vcounter + 1
    faces = []
    rev = True
    for i in range(2, len(idx)):
        c = idx[i]
        if (c & 0x8000) == 0:
            t1, t2, t3 = gv(idx[i]) - diff, gv(idx[i-1]) - diff, gv(idx[i-2]) - diff
            if t1 != t2 and t2 != t3 and t1 != t3 and all(0 <= t < vcounter for t in (t1, t2, t3)):
                faces.append((t3, t2, t1) if rev else (t1, t2, t3))
        rev = not rev
    return verts, uvs, faces


def read_model_parts(coord, payload, model_offset, dedup=False):
    """
    Le as parts de um modelo SEM mesclar: devolve
    (parts, skipped, total) onde parts = [(verts_obj, uvs_obj, faces_local), ...].

    `dedup=True` pula parts cuja GEOMETRIA crua (vertices int16) e' identica a uma
    ja lida — sao os paineis "double-sided" que o PS2 duplica para renderizar os
    dois lados do tecido. Util para um .obj visualmente mais limpo.
    """
    model = parse_model(payload, model_offset)
    parts = []
    seen = set()
    skipped = 0
    for part in model.parts:
        geom = read_part_geometry(payload, part)
        if geom is None:
            skipped += 1
            continue
        pverts, puvs, local_faces = geom
        if dedup:
            key = tuple(pverts)
            if key in seen:
                continue
            seen.add(key)
        verts = [coord.int16_to_obj_vertex(s0, s1, s2) for (s0, s1, s2) in pverts]
        uvs = [coord.int16_to_obj_uv(u, v) for (u, v) in puvs]
        parts.append((verts, uvs, list(local_faces)))
    return parts, skipped, len(model.parts)


def read_model_geometry(coord, payload, model_offset, dedup=False):
    """
    Le TODAS as parts de um modelo (`MAGIC_MODEL` em `model_offset`) e devolve a
    geometria MESCLADA no espaco OBJ: (verts, uvs, faces, skipped, nparts).

    Nucleo compartilhado por face/trofeu (export), estadio e kit. Cada part passa
    pelo leitor universal `read_part_geometry`; `coord` (do AssetProfile) aplica
    escala/eixos. `dedup` remove paineis double-sided (ver read_model_parts).
    """
    parts, skipped, total = read_model_parts(coord, payload, model_offset, dedup=dedup)
    verts, uvs, faces = [], [], []
    vcount = 0
    for pverts, puvs, local_faces in parts:
        verts.extend(pverts)
        uvs.extend(puvs)
        faces.extend((a + vcount, b + vcount, c + vcount) for (a, b, c) in local_faces)
        vcount += len(pverts)
    return verts, uvs, faces, skipped, total
