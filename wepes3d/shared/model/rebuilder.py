"""
Reconstrucao de uma part com geometria nova.

Atualiza TODOS os campos derivados que mudam quando `vc` ou `strip_num`
muda. Lista completa (ver `docs/02-anatomia-payload.md` para detalhes):

Header da part (rel 0x00..0xB0):
  - 0x00 (uint32) = part_size                                  (recomputado)
  - 0x0C (uint32) = QWC = (part_size - part_info_start) / 16   (DMA chain)
  - 0x10 (uint32) = strip_indices_total = strip_num × 4
  - 0x2C (uint32) = vbe = 4 × vc + 4   ⚠ copia de header[0xC2]
  - 0x30 (uint32) = ss  = 4 × vc + 8   ⚠ copia de header[0xC8]

VIF prologue (rel 0xB0..0x110):
  - 0xC2 (uint16) = vbe (vertex_block_end)
  - 0xC8 (uint16) = ss  (strip_start)
  - 0xCA (uint16) = se  (strip_end = ss + strip_num)
  - 0xF6 (uint16) = vbe (2a copia)
  - 0xF8 (uint16) = vbe (3a copia)
  - 0x108 (uint8) = vc  (vertex_count, primeiro byte do qword)

Tags VIF UNPACK:
  - tag vertices (rel 0x110), byte[2] = vc
  - tag normais  (apos vertices + pad), byte[2] = vc
  - tag UVs      (apos normais + pad), byte[2] = vc
  - tag strip    (apos VIF_STRIP_MARKER), IMMED = 0xC000 | ss, byte[2] = strip_num
"""

import struct
from typing import List, Optional, Tuple

from ..constants import (
    DMA_ALIGN, MAX_VERTEX_COUNT_PER_PART, MAX_STRIP_NUM,
    VERTEX_IN_PART_OFFSET,
)
from .parser import Part
from .strip import (
    align_strip_to_v4, pack_strip_indices, pad_to_length,
    triangles_to_pes_strip, STRIP_PADDING_VALUE,
)


# ============================================================================
# Atualizacao do header para nova contagem de vertices
# ============================================================================

def update_vertex_count_in_header(
    header_bytes: bytes,
    part_info_start_raw: int,
    pre_normals_tag: bytes,
    pre_uvs_tag: bytes,
    new_count: int,
) -> Tuple[bytes, bytes, bytes]:
    """
    Atualiza os campos `vc` no header e nas tags VIF UNPACK.

    Por que IMMED de normais e UVs NAO muda com vc:

    O STCYCL CL=4 WL=1 no fim do VIF prologue (rel 0x10C) faz com que cada
    elemento V3-16/V2-16 ocupe 1 qword "ativo" + 3 qwords skip. Vertices,
    normais e UVs sao INTERLEAVED no mesmo bloco de 4-qwords:

        qw[4 + 4n + 0] = vertice n    (IMMED ADDR = 4)
        qw[4 + 4n + 1] = normal n     (IMMED ADDR = 5)
        qw[4 + 4n + 2] = (skip/vazio)
        qw[4 + 4n + 3] = uv n         (IMMED ADDR = 7)

    Portanto IMMED ADDR de normais (5) e UVs (7) sao CONSTANTES — soh o
    NUM do tag muda com vc.

    Bug historico: versoes antigas re-mapeavam os IMMEDs como se o layout
    fosse SEQUENCIAL (normais comecando apos os vertices na VU mem). Isso
    causava crashes "unknown vifcmd" no PCSX2 quando vc != 87.
    """
    if new_count > MAX_VERTEX_COUNT_PER_PART:
        raise ValueError(
            f"Vertex count ({new_count}) excede max ({MAX_VERTEX_COUNT_PER_PART}). "
            f"O campo NUM do VIF UNPACK eh uint8."
        )

    vc_offset = part_info_start_raw + VERTEX_IN_PART_OFFSET

    new_header = bytearray(header_bytes)
    struct.pack_into("<H", new_header, vc_offset, new_count)
    if vc_offset + 10 < len(new_header):
        new_header[vc_offset + 10] = new_count & 0xFF

    new_pre_normals = bytearray(pre_normals_tag)
    new_pre_normals[2] = new_count & 0xFF

    new_pre_uvs = bytearray(pre_uvs_tag)
    new_pre_uvs[2] = new_count & 0xFF

    return bytes(new_header), bytes(new_pre_normals), bytes(new_pre_uvs)


# ============================================================================
# Reconstrucao principal
# ============================================================================

def rebuild_part(
    part: Part,
    new_vertices: List[Tuple[int, int, int]],
    new_normals: List[Tuple[int, int, int]],
    new_uvs: List[Tuple[int, int]],
    new_triangles: List[Tuple[int, int, int]],
    new_count: Optional[int] = None,
    strip_mode: str = "connected",
) -> Part:
    """
    Reconstroi uma part com nova geometria, recalculando todos os campos
    derivados (size, QWC, vbe, ss, se, vc nas tags).

    Se `new_count` for diferente de `part.vertex_count`, atualiza as tags
    VIF e o header. Caso contrario, preserva o tamanho original (paddeando
    o strip com -32768).

    strip_mode:
      "connected" (default) - tristrips conectados (strip_connected.py), ~35%
                    menores; validado in-game. `new_triangles` deve ja vir
                    orientado-para-frente (orient_for_front). Veja docs/05.
      "list"      - triangle list, 3 indices/triangulo. Robusto (formato legado).
    """
    vc = len(new_vertices)
    assert vc == len(new_normals), "vertices e normais devem ter o mesmo size"
    assert vc == len(new_uvs), "vertices e UVs devem ter o mesmo size"

    if new_count is None:
        new_count = vc

    # 1. Atualiza tags VIF se vc mudou
    if new_count != part.vertex_count:
        new_header, new_pre_normals_tag, new_pre_uvs_tag = update_vertex_count_in_header(
            part.header_bytes,
            part.part_info_start_raw,
            part.pre_normals_tag,
            part.pre_uvs_tag,
            new_count,
        )
    else:
        new_header = part.header_bytes
        new_pre_normals_tag = part.pre_normals_tag
        new_pre_uvs_tag = part.pre_uvs_tag

    # 2. Padding apos vertices/normais (2 bytes se vc impar — alinha a 4)
    new_pad_v = b'\x00\x00' if new_count % 2 != 0 else b''
    new_pad_n = b'\x00\x00' if new_count % 2 != 0 else b''

    # 3. Codifica o strip
    if strip_mode == "connected":
        from .strip_connected import (
            build_connected_strips, connected_strips_to_indices,
        )
        new_strip_indices = connected_strips_to_indices(
            build_connected_strips(new_triangles))
        if not new_strip_indices:
            new_strip_indices = triangles_to_pes_strip(new_triangles)
    else:
        new_strip_indices = triangles_to_pes_strip(new_triangles)

    # Se vc nao mudou, mantem tamanho original do strip via padding —
    # evita que part_size mude e portanto ponteiros absolutos no
    # pre_parts (que apontam para parts_end) fiquem desatualizados.
    if new_count == part.vertex_count:
        orig_strip_count = len(part.strip_indices)
        new_strip_indices = pad_to_length(new_strip_indices, orig_strip_count)

    # Alinha a multiplo de 4 (= 1 V4-16 = 8 bytes)
    new_strip_indices = align_strip_to_v4(new_strip_indices)

    # NUM=0 no VIF UNPACK eh invalido (interpretado como 256 elementos).
    # Se o strip ficou vazio, mete um placeholder de 4 paddings.
    if not new_strip_indices:
        new_strip_indices = [STRIP_PADDING_VALUE] * 4

    new_strip_bytes = pack_strip_indices(new_strip_indices)

    new_num_v4 = len(new_strip_bytes) // 8
    if new_num_v4 > MAX_STRIP_NUM:
        raise ValueError(
            f"Strip muito longo (NUM={new_num_v4} > {MAX_STRIP_NUM}). "
            f"Triangle list usa 3 indices/triangulo; o NUM (uint8) limita a "
            f"{MAX_STRIP_NUM} elementos V4-16 = {MAX_STRIP_NUM * 4} indices, "
            f"ou seja ~{MAX_STRIP_NUM * 4 // 3} triangulos por part. "
            f"Divida esta part em mais parts ou decime a malha."
        )

    # 4. Atualiza o tag VIF UNPACK do strip:
    #    bytes [-4..-2] = IMMED = 0xC000 | strip_start (= 4*vc + 8)
    #    bytes [-2..]   = NUM + CMD (0x6D = V4-16)
    new_pre_strip = bytearray(part.pre_strip_bytes)
    new_strip_start = 4 * new_count + 8
    new_strip_immed = 0xC000 | (new_strip_start & 0x03FF)
    struct.pack_into("<H", new_pre_strip, len(new_pre_strip) - 4, new_strip_immed)
    new_tag_value = 0x6D00 + new_num_v4
    struct.pack_into("<H", new_pre_strip, len(new_pre_strip) - 2, new_tag_value)
    new_pre_strip = bytes(new_pre_strip)

    # 5. Calcula o novo size + padding DMA
    new_size = (
        len(new_header)
        + new_count * 6
        + len(new_pad_v)
        + 4
        + new_count * 6
        + len(new_pad_n)
        + 4
        + new_count * 4
        + len(part.pad_after_uvs)
        + len(new_pre_strip)
        + len(new_strip_bytes)
        + len(part.post_strip_bytes)
    )
    align_pad = 0
    if new_size % DMA_ALIGN != 0:
        align_pad = DMA_ALIGN - (new_size % DMA_ALIGN)
        new_size += align_pad
    new_post_strip = part.post_strip_bytes + b'\x00' * align_pad

    # 6. Atualiza campos derivados no header
    hdr = bytearray(new_header)
    struct.pack_into("<I", hdr, 0x00, new_size)
    struct.pack_into("<I", hdr, 0x0C,
                     (new_size - part.part_info_start_raw) // 16)  # QWC
    struct.pack_into("<I", hdr, 0x10, new_num_v4 * 4)              # strip_indices_total

    # Parametros do microcode VU
    vertex_block_end = 4 * new_count + 4
    strip_start = vertex_block_end + 4
    strip_end = strip_start + new_num_v4

    struct.pack_into("<H", hdr, 0xC2, vertex_block_end)
    struct.pack_into("<H", hdr, 0xC8, strip_start)
    struct.pack_into("<H", hdr, 0xCA, strip_end)
    struct.pack_into("<H", hdr, 0xF6, vertex_block_end)
    struct.pack_into("<H", hdr, 0xF8, vertex_block_end)

    # Copias de vbe e ss no header (Bug 10 — em vc=87 do template parece
    # constante porque sempre vale 352/356, mas em h2/h4 e face_X varia.)
    struct.pack_into("<I", hdr, 0x2C, vertex_block_end)
    struct.pack_into("<I", hdr, 0x30, strip_start)

    new_header = bytes(hdr)

    return Part(
        offset_in_payload=part.offset_in_payload,
        size=new_size,
        header_bytes=new_header,
        tex_id=part.tex_id,
        vertex_count=new_count,
        part_info_start_raw=part.part_info_start_raw,
        vertices=new_vertices,
        normals=new_normals,
        uvs=new_uvs,
        strip_indices=new_strip_indices,
        pad_after_vertices=new_pad_v,
        pre_normals_tag=new_pre_normals_tag,
        pad_after_normals=new_pad_n,
        pre_uvs_tag=new_pre_uvs_tag,
        pad_after_uvs=part.pad_after_uvs,
        pre_strip_bytes=new_pre_strip,
        post_strip_bytes=new_post_strip,
    )


# ============================================================================
# Patches no pre_parts (header global)
# ============================================================================

def patch_total_parts(pre_parts_bytes: bytes, offset_file_1: int,
                      new_total: int) -> bytes:
    """Atualiza `total_parts` no model header (offset_file_1 + 0x20)."""
    arr = bytearray(pre_parts_bytes)
    struct.pack_into("<I", arr, offset_file_1 + 0x20, new_total)
    return bytes(arr)

