"""
Parser do payload descompactado: extrai parts, vertices, UVs, normais, strip.

Layout do payload (face.bin simples, 8 parts):

    [pre_parts: 272 bytes]   - header global + ponteiros (incl. parts_end)
    [parts:    16560 bytes]  - 8 parts variando ~2048..2080 bytes cada
    [post_parts: 21632 bytes] - cabecalho + textura

Cada part eh:

    [part_header: 176 bytes]  (offset rel 0x00 .. 0xB0)
    [VIF prologue: 96 bytes]  (offset rel 0xB0 .. 0x110)
    [VIF unpack tag vertices: 4 bytes]
    [vertices: vc × 6 bytes]
    [padding (2 bytes se vc impar)]
    [VIF unpack tag normais: 4 bytes]
    [normais: vc × 6 bytes]
    [padding (2 bytes se vc impar)]
    [VIF unpack tag UVs: 4 bytes]
    [UVs: vc × 4 bytes]
    [padding ate VIF_STRIP_MARKER]
    [VIF_STRIP_MARKER: 8 bytes]
    [VIF unpack tag strip: 4 bytes]
    [strip data: strip_num × 8 bytes]
    [post_strip + DMA pad]

Ver `docs/02-anatomia-payload.md` para detalhamento completo dos campos.
"""

import struct
from dataclasses import dataclass
from typing import List, Optional, Tuple

from ..constants import (
    MAGIC_MODEL, CONTAINER_MAGIC, VIF_STRIP_MARKER, PARTS_INFO_OFFSET,
    TEXTURE_INDEX_IN_PART, VERTEX_IN_PART_OFFSET,
)


@dataclass
class Part:
    """Uma part do modelo: bloco com geometria + VIF microcode parameters."""

    offset_in_payload: int
    size: int
    header_bytes: bytes
    """Bytes 0x00 .. vertices_start (header da part + VIF prologue + tag
    vertices). Preservado quase intacto entre rebuilds — so atualizamos
    campos derivados (part_size, QWC, strip_indices_total, vbe, ss, se, vc).
    """

    tex_id: int
    vertex_count: int
    part_info_start_raw: int
    """Offset relativo do VIF prologue (igual a `header[0x08]`). Geralmente
    0xB0 para o template simples."""

    vertices: List[Tuple[int, int, int]]
    """(y, z, x) int16 — ordem do .bin (X eh o ULTIMO no triplet armazenado)."""

    normals: List[Tuple[int, int, int]]
    """(nx, ny, nz) int16 — ordem normal, DIFERENTE dos vertices."""

    uvs: List[Tuple[int, int]]
    """(u, v) int16."""

    strip_indices: List[int]
    """int16 raw com bit 15 = ADC flag (restart no decoder)."""

    pad_after_vertices: bytes
    pre_normals_tag: bytes
    pad_after_normals: bytes
    pre_uvs_tag: bytes
    pad_after_uvs: bytes
    pre_strip_bytes: bytes
    """Bytes entre UVs e o strip_data: VIF_STRIP_MARKER + tag VIF UNPACK strip
    (12 bytes total)."""

    post_strip_bytes: bytes
    """Bytes apos o strip_data ate o fim da part. Geralmente eh um STMOD
    mode=0 (`00 00 00 05`) seguido de padding zeros para alinhar DMA."""


@dataclass
class Model:
    """Modelo completo: parts + bytes circundantes preservados intactos."""

    payload: bytes
    """Payload descompactado original — opcional, usado para debug."""

    offset_file_1: int
    """Offset onde comeca o MAGIC_MODEL no payload. Geralmente 0x10."""

    pre_parts_bytes: bytes
    """Bytes 0x00 .. parts_start. Inclui o outer header + model header +
    metadata (e, em arquivos "ricos", a area de bones de 12KB)."""

    parts: List[Part]

    post_parts_bytes: bytes
    """Bytes apos a ultima part: textura + metadata. Preservado intacto."""


def detect_asset_type(payload: bytes) -> str:
    """Retorna 'face' (modelo direto) ou 'trophy' (container aninhado) olhando
    o magic em `payload[8]` (offset_file_1)."""
    offset_file_1 = struct.unpack_from("<I", payload, 8)[0]
    magic = payload[offset_file_1:offset_file_1 + 4]
    if magic == MAGIC_MODEL:
        return "face"
    if magic == CONTAINER_MAGIC:
        return "trophy"
    raise ValueError(f"Magic desconhecido em offset_file_1=0x{offset_file_1:X}: "
                     f"{magic.hex()} (nem face {MAGIC_MODEL.hex()} nem "
                     f"trofeu {CONTAINER_MAGIC.hex()})")


def locate_model(payload: bytes) -> int:
    """
    Devolve o offset ABSOLUTO no payload onde comeca o MAGIC_MODEL (0300ffff)
    do modelo 3D — o ponto a partir do qual a estrutura de parts eh identica
    entre face e trofeu.

      FACE   : modelo direto em offset_file_1 (payload[8]).
      TROFEU : container em offset_file_1 -> base = offset_file_1 + 32 ->
               offset_mdl = base + uint32(base+8).
    """
    offset_file_1 = struct.unpack_from("<I", payload, 8)[0]
    magic = payload[offset_file_1:offset_file_1 + 4]
    if magic == MAGIC_MODEL:
        return offset_file_1
    if magic == CONTAINER_MAGIC:
        base = offset_file_1 + 32
        off_mdl = struct.unpack_from("<I", payload, base + 8)[0] + base
        mdl_magic = payload[off_mdl:off_mdl + 4]
        if mdl_magic != MAGIC_MODEL:
            raise ValueError(
                f"Container sem MDL valido: magic@0x{off_mdl:X}={mdl_magic.hex()}")
        return off_mdl
    raise ValueError(f"Magic desconhecido: {magic.hex()}")


def parse_model(payload: bytes, model_offset: Optional[int] = None) -> Model:
    """
    Le o payload descompactado e devolve a estrutura `Model` populada.

    `model_offset`: offset do MAGIC_MODEL. Se None, eh localizado automaticamente
    (`locate_model`) — funciona para face (modelo direto) e trofeu (container).
    O campo `Model.offset_file_1` guarda esse offset do MODELO (nao o payload[8]).
    """
    if model_offset is None:
        model_offset = locate_model(payload)
    offset_file_1 = model_offset
    magic = payload[offset_file_1:offset_file_1 + 4]
    if magic != MAGIC_MODEL:
        raise ValueError(f"Magic incorreto: {magic.hex()}")

    total_parts, parts_start_rel = struct.unpack_from(
        "<II", payload, offset_file_1 + PARTS_INFO_OFFSET
    )
    parts_start_abs = parts_start_rel + offset_file_1
    pre_parts_bytes = payload[:parts_start_abs]

    parts: List[Part] = []
    cursor = parts_start_abs
    for _ in range(total_parts):
        part = _parse_part(payload, cursor)
        parts.append(part)
        cursor += part.size

    post_parts_bytes = payload[cursor:]
    return Model(
        payload=payload,
        offset_file_1=offset_file_1,
        pre_parts_bytes=pre_parts_bytes,
        parts=parts,
        post_parts_bytes=post_parts_bytes,
    )


def _parse_part(payload: bytes, offset: int) -> Part:
    """Le uma part a partir de um offset absoluto no payload."""
    part_size = struct.unpack_from("<I", payload, offset)[0]
    tex_id = struct.unpack_from("<I", payload, offset + TEXTURE_INDEX_IN_PART)[0]
    part_info_start_raw = struct.unpack_from("<I", payload, offset + 8)[0]

    vertex_count_pos = offset + part_info_start_raw + VERTEX_IN_PART_OFFSET
    vertex_count = struct.unpack_from("<H", payload, vertex_count_pos)[0]
    vertices_start = vertex_count_pos + 12

    header_bytes = payload[offset:vertices_start]

    # Vertices (y, z, x) int16
    vertices: List[Tuple[int, int, int]] = []
    cursor = vertices_start
    for _ in range(vertex_count):
        y, z, x = struct.unpack_from("<hhh", payload, cursor)
        vertices.append((y, z, x))
        cursor += 6

    # Padding apos vertices (2 bytes se vc impar)
    pad_v_size = 2 if vertex_count % 2 != 0 else 0
    pad_after_vertices = payload[cursor:cursor + pad_v_size]
    cursor += pad_v_size

    # Tag VIF UNPACK das normais (4 bytes)
    pre_normals_tag = payload[cursor:cursor + 4]
    cursor += 4

    # Normais (nx, ny, nz) int16
    normals: List[Tuple[int, int, int]] = []
    for _ in range(vertex_count):
        nx, ny, nz = struct.unpack_from("<hhh", payload, cursor)
        normals.append((nx, ny, nz))
        cursor += 6

    pad_n_size = 2 if vertex_count % 2 != 0 else 0
    pad_after_normals = payload[cursor:cursor + pad_n_size]
    cursor += pad_n_size

    # Tag VIF UNPACK dos UVs
    pre_uvs_tag = payload[cursor:cursor + 4]
    cursor += 4

    # UVs (u, v) int16
    uvs: List[Tuple[int, int]] = []
    for _ in range(vertex_count):
        u, v = struct.unpack_from("<hh", payload, cursor)
        uvs.append((u, v))
        cursor += 4

    # Procura o VIF_STRIP_MARKER no resto da part
    part_end = offset + part_size
    remaining = payload[cursor:part_end]
    marker_pos = remaining.find(VIF_STRIP_MARKER)
    if marker_pos == -1:
        raise ValueError(f"VIF_STRIP_MARKER nao encontrado em part @ 0x{offset:x}")

    pad_after_uvs = remaining[:marker_pos]
    strip_block_start = cursor + marker_pos

    # Apos o marker (8 bytes), o tag VIF UNPACK V4-16 do strip
    tag_pos = strip_block_start + 8 + 2  # +2 para pular IMMED bytes do tag
    tag_value = struct.unpack_from("<H", payload, tag_pos)[0]
    num_v4_elements = tag_value - 0x6D00  # CMD 0x6D = V4-16, subtraindo NUM
    strip_data_bytes = num_v4_elements * 8

    pre_strip_bytes = payload[strip_block_start:tag_pos + 2]
    strip_data_start = tag_pos + 2
    strip_data_end = strip_data_start + strip_data_bytes

    num_indices = strip_data_bytes // 2
    strip_indices = list(struct.unpack_from(
        f"<{num_indices}h", payload, strip_data_start))

    post_strip_bytes = payload[strip_data_end:part_end]

    return Part(
        offset_in_payload=offset,
        size=part_size,
        header_bytes=header_bytes,
        tex_id=tex_id,
        vertex_count=vertex_count,
        part_info_start_raw=part_info_start_raw,
        vertices=vertices,
        normals=normals,
        uvs=uvs,
        strip_indices=strip_indices,
        pad_after_vertices=pad_after_vertices,
        pre_normals_tag=pre_normals_tag,
        pad_after_normals=pad_after_normals,
        pre_uvs_tag=pre_uvs_tag,
        pad_after_uvs=pad_after_uvs,
        pre_strip_bytes=pre_strip_bytes,
        post_strip_bytes=post_strip_bytes,
    )


def clone_part_structure(donor: Part) -> Part:
    """
    Cria um shell de Part copiando toda estrutura VIF de `donor` (tags,
    padding, pre/post strip), mas sem geometria. Geometria eh preenchida
    depois pelo `rebuilder.rebuild_part()`. Usado para criar parts extras
    alem das do template.
    """
    return Part(
        offset_in_payload=0,
        size=donor.size,
        header_bytes=donor.header_bytes,
        tex_id=donor.tex_id,
        vertex_count=donor.vertex_count,
        part_info_start_raw=donor.part_info_start_raw,
        vertices=[],
        normals=[],
        uvs=[],
        strip_indices=[],
        pad_after_vertices=donor.pad_after_vertices,
        pre_normals_tag=donor.pre_normals_tag,
        pad_after_normals=donor.pad_after_normals,
        pre_uvs_tag=donor.pre_uvs_tag,
        pad_after_uvs=donor.pad_after_uvs,
        pre_strip_bytes=donor.pre_strip_bytes,
        post_strip_bytes=donor.post_strip_bytes,
    )


def write_part(part: Part) -> bytes:
    """Serializa uma Part de volta em bytes, na mesma ordem do parser."""
    out = bytearray()
    out += part.header_bytes
    for (y, z, x) in part.vertices:
        out += struct.pack("<hhh", y, z, x)
    out += part.pad_after_vertices
    out += part.pre_normals_tag
    for (nx, ny, nz) in part.normals:
        out += struct.pack("<hhh", nx, ny, nz)
    out += part.pad_after_normals
    out += part.pre_uvs_tag
    for (u, v) in part.uvs:
        out += struct.pack("<hh", u, v)
    out += part.pad_after_uvs
    out += part.pre_strip_bytes
    for idx in part.strip_indices:
        out += struct.pack("<h", idx)

    # Se algo deu errado e o conteudo eh menor que part.size, completa com
    # zeros. Geralmente nao acontece — apenas seguranca para roundtrips
    # imperfeitos.
    written = len(out) + len(part.post_strip_bytes)
    if written < part.size:
        out += b'\x00' * (part.size - written)
    out += part.post_strip_bytes
    return bytes(out)


def write_model(model: Model) -> bytes:
    """Serializa o Model inteiro: pre_parts + parts concatenadas + post_parts."""
    out = bytearray()
    out += model.pre_parts_bytes
    for part in model.parts:
        out += write_part(part)
    out += model.post_parts_bytes
    return bytes(out)
