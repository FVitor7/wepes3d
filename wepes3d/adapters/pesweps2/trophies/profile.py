"""
Adapter de TROFEU: o que difere das faces.

- Coordenadas: stored (sx, sz, -sy), factor = +0.001553 (nega Y).
- Container ANINHADO: payload[8] = container 00 06 00 00 -> base = +32 ->
  diretorio de secoes (sub-modelos .mdl). sec0 = trofeu; sec1+ = bancada/palco.
- Resize: desliza as entradas do diretorio (apos a target) + ponteiros ABS do
  header externo (ex.: container de texturas em payload[0x0C]).
- max_parts: None (trofeus tem 14-31 parts por sub-modelo; sem limite de 8).

Ver docs/08-trofeus.md.
"""

import struct
from typing import List, Tuple

from ....shared.constants import MAGIC_MODEL, CONTAINER_MAGIC, NORMAL_SCALE
from ....shared.geometry import CoordSpace, obj_to_int16_uv, int16_to_obj_uv, clamp16
from ....shared.pipeline import AssetProfile

TROPHY_VERTEX_FACTOR = 0.001553
"""Fator de vertice do trofeu (positivo). Mesma magnitude do |VERTEX_FACTOR| da
face, mas SEM o sinal negativo — a inversao de eixo vem da negacao de Y."""


# ============================================================================
# Coordenadas do trofeu
# ============================================================================

def obj_to_int16_vertex(x: float, y: float, z: float) -> Tuple[int, int, int]:
    """OBJ (x,y,z) -> stored (sx, sz, -sy). Inverte Y."""
    f = TROPHY_VERTEX_FACTOR
    return (clamp16(round(x / f)), clamp16(round(z / f)), clamp16(round(-y / f)))


def int16_to_obj_vertex(s0: int, s1: int, s2: int) -> Tuple[float, float, float]:
    """stored (s0,s1,s2) -> OBJ (s0*f, -s2*f, s1*f)."""
    f = TROPHY_VERTEX_FACTOR
    return (s0 * f, -s2 * f, s1 * f)


def obj_to_int16_normal(nx: float, ny: float, nz: float) -> Tuple[int, int, int]:
    """Normal unitaria -> int16, mesma permutacao de eixos dos vertices do trofeu
    (nx, nz, -ny). Validar in-game ao usar recount com normais."""
    return (clamp16(round(nx * NORMAL_SCALE)),
            clamp16(round(nz * NORMAL_SCALE)),
            clamp16(round(-ny * NORMAL_SCALE)))


COORD = CoordSpace(
    name="trophy",
    obj_to_int16_vertex=obj_to_int16_vertex,
    int16_to_obj_vertex=int16_to_obj_vertex,
    obj_to_int16_uv=obj_to_int16_uv,
    int16_to_obj_uv=int16_to_obj_uv,
    obj_to_int16_normal=obj_to_int16_normal,
)


# ============================================================================
# Container aninhado: diretorio de secoes (.mdl)
# ============================================================================

def section_offsets(payload: bytes) -> List[int]:
    """Offsets ABSOLUTOS de cada sub-modelo (.mdl) do diretorio de secoes.
    sec0 = trofeu principal; sec1+ = bancada/palco/etc."""
    offset_file_1 = struct.unpack_from("<I", payload, 8)[0]
    if payload[offset_file_1:offset_file_1 + 4] != CONTAINER_MAGIC:
        raise ValueError("Asset nao eh um trofeu (sem container 00060000).")
    base = offset_file_1 + 32
    count = struct.unpack_from("<I", payload, base)[0]
    offsets: List[int] = []
    for i in range(count):
        rel = struct.unpack_from("<I", payload, base + 8 + 4 * i)[0]
        ab = base + rel
        if payload[ab:ab + 4] == MAGIC_MODEL:
            offsets.append(ab)
    return offsets


def locate(payload: bytes, section: int = 0) -> int:
    """Offset do sub-modelo `section` (0 = trofeu principal)."""
    secs = section_offsets(payload)
    if not (0 <= section < len(secs)):
        raise ValueError(f"secao {section} inexistente ({len(secs)} sub-modelos).")
    return secs[section]


# ============================================================================
# Resize: diretorio de secoes (+delta) + header externo (ponteiros ABS)
# ============================================================================

def patch_resize(payload: bytes, model_offset: int, pre_parts_size: int,
                 orig_parts_end: int, new_parts_end: int) -> Tuple[bytes, int]:
    """
    Ao mudar o tamanho da target por delta, desliza +delta:
      - entradas do diretorio (rel a base) cujo alvo abs >= orig_parts_end;
      - uint32 do header externo (0x00..base, ABS) >= orig_parts_end (ex.: o
        container de texturas em payload[0x0C]).
    `pre_parts_size` nao eh usado (mantido por compatibilidade de assinatura).
    """
    delta = new_parts_end - orig_parts_end
    if delta == 0:
        return payload, 0
    arr = bytearray(payload)
    offset_file_1 = struct.unpack_from("<I", arr, 8)[0]
    base = offset_file_1 + 32
    count = struct.unpack_from("<I", arr, base)[0]
    patched = 0

    for i in range(count):
        off = base + 8 + 4 * i
        if off + 4 > len(arr):
            break
        rel = struct.unpack_from("<I", arr, off)[0]
        if base + rel >= orig_parts_end:      # secao apos a target -> desliza
            struct.pack_into("<I", arr, off, rel + delta)
            patched += 1

    for off in range(0, base - 3, 4):
        val = struct.unpack_from("<I", arr, off)[0]
        if orig_parts_end <= val < len(payload):
            struct.pack_into("<I", arr, off, val + delta)
            patched += 1

    return bytes(arr), patched


TROPHY_PROFILE = AssetProfile(
    name="trophy", coord=COORD, max_parts=None,
    locate=locate, patch_resize=patch_resize, list_sections=section_offsets,
)
