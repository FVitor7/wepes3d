"""
Codificacao do strip data do PES PS2.

O strip data eh uma lista de int16 que a VU1 do PS2 decodifica como
triangulos. Cada indice tem:

  - bit 15 = ADC flag (Address Don't Connect): 1 = nao dispara triangulo,
    apenas entra na fila.
  - bits 0..14 = (vertex_local_idx + 1) × 4.

A VU1 mantem uma janela deslizante de 3 indices [a, b, c] e dispara um
triangulo (decode(a), decode(b), decode(c)) quando `c` tem ADC=0. Tres casos:

  Caso 1: [neg, neg, pos]  - 2 restarts + 1 dispara (triangulo isolado).
  Caso 2: [neg, pos, pos]  - 1 restart no inicio + 2 disparos (continuacao
                              do segmento anterior).
  Caso 3: [pos, pos, pos]  - extensao normal: cada `c` dispara um novo
                              triangulo formado com os 2 anteriores.

Esta implementacao usa apenas Caso 1: cada triangulo eh um segmento
isolado [neg, neg, pos], custando 3 indices/triangulo + 1 de padding por
elemento V4-16 (4 indices = 8 bytes). Vide doc/05-strip-encoding.md para
o motivo: strips conectados nao garantem winding consistente sem flip
automatico (que o PS2 nao faz), causando ~60% de triangulos back-facing
e BURACOS visiveis no jogo.
"""

import struct
from typing import List, Tuple


# ============================================================================
# Encoding de um triangulo individual (caso 1: [neg, neg, pos])
# ============================================================================

def _encode_vertex_with_adc(v: int) -> int:
    """Codifica um vertice local com bit ADC=1 (no-kick). int16 negativo."""
    raw = (v + 1) * 4
    # bit 15 setado -> visto como int16 negativo
    return (raw | 0x8000) - 0x10000


def _encode_vertex_kick(v: int) -> int:
    """Codifica um vertice local com bit ADC=0 (kick = dispara triangulo).
    int16 positivo no range [4, 0x7FFC]."""
    raw = (v + 1) * 4
    if raw > 0x7FFF:
        raise ValueError(
            f"Indice de vertice {v} excede 0x7FFF apos multiplicar por 4. "
            f"Max suportado por part: 8190 vertices."
        )
    return raw


# ============================================================================
# Codificacao do strip inteiro (triangle list mode)
# ============================================================================

def triangles_to_pes_strip(
    triangles: List[Tuple[int, int, int]],
) -> List[int]:
    """
    Converte uma lista de triangulos (a, b, c) em indices int16 para o
    strip data do PS2.

    Aplica:
      1. Flip de winding (a, c, b) em cada triangulo — compensa a inversao
         de X aplicada nos vertices (`float_xyz_to_int16_yzx`). Sem isso,
         todos os triangulos ficariam back-facing apos o PS2 aplicar o
         X-flip implicito.
      2. Encoding triangle list: cada triangulo vira [neg(v0), neg(v1),
         pos(v2)] (caso 1 do decoder). Custa 3 indices/triangulo.

    NAO usa estendido de strip: o PS2 nao faz flip de winding automatico
    entre triangulos consecutivos da janela deslizante. Estender via
    `opposite_vertex` em meshes arbitrarios gera ~60% de triangulos com
    winding invertido -> back-face culled -> buracos no jogo. Triangle
    list garante winding correto por construcao.
    """
    indices: List[int] = []
    for (a, b, c) in triangles:
        # Flip de winding: (a, b, c) -> (a, c, b)
        v0, v1, v2 = a, c, b
        indices.append(_encode_vertex_with_adc(v0))
        indices.append(_encode_vertex_with_adc(v1))
        indices.append(_encode_vertex_kick(v2))
    return indices


def pack_strip_indices(indices: List[int]) -> bytes:
    """Empacota a lista de indices int16 em bytes (little endian)."""
    return struct.pack(f"<{len(indices)}h", *indices)


# ============================================================================
# Padding e alinhamento
# ============================================================================

STRIP_PADDING_VALUE = -32768
"""Valor usado para padding: int16 -32768 = 0x8000. Soh tem o bit ADC setado,
entao o decoder NUNCA dispara triangulo, e como representa vertice 0 com
ADC ativo, eh um no-op seguro."""


def align_strip_to_v4(indices: List[int]) -> List[int]:
    """
    Pad para que o numero total de indices seja multiplo de 4 (cada elemento
    V4-16 = 4 int16 = 8 bytes). Sem isso, o tag VIF UNPACK V4-16 nao bate com
    o tamanho do strip data.
    """
    rem = len(indices) % 4
    if rem == 0:
        return indices
    pad_count = 4 - rem
    return indices + [STRIP_PADDING_VALUE] * pad_count


def pad_to_length(indices: List[int], target_length: int) -> List[int]:
    """
    Pad ate atingir `target_length` (caso em que queremos manter o tamanho
    da part exatamente igual ao template).
    """
    if len(indices) >= target_length:
        return indices
    return indices + [STRIP_PADDING_VALUE] * (target_length - len(indices))


# ============================================================================
# Diagnostico (util para debugging)
# ============================================================================

def decode_strip(indices: List[int], vc: int) -> List[Tuple[int, int, int]]:
    """
    Replica o decoder oficial do PS2 (port do plugin Blender pes_ps2_imp).
    Util para validar que o encoding produziu triangulos corretos.

    Retorna uma lista de triangulos (a, b, c) com indices LOCAIS da part.
    """
    divided = [int(i / 4) for i in indices]
    triangles: List[Tuple[int, int, int]] = []

    def safe(value: int, is_restart: bool) -> int:
        return (8192 + value - 1) if is_restart else (value - 1)

    def valid(tri: Tuple[int, int, int]) -> bool:
        return all(0 <= i < vc for i in tri)

    for f in range(len(divided) - 2):
        a, b, c = divided[f], divided[f + 1], divided[f + 2]
        if a < 0 and b < 0 and c >= 0:
            # Caso 1: [neg, neg, pos]
            if a != b and b != c and c != a:
                tri = (safe(a, True), safe(b, True), safe(c, False))
                if valid(tri):
                    triangles.append(tri)
        elif a <= 0 and b >= 0 and c >= 0:
            # Caso 2: [neg, pos, pos]
            if a != b and b != c and c != a:
                tri = (safe(a, True), safe(b, False), safe(c, False))
                if valid(tri):
                    triangles.append(tri)
        elif a > 0 and b >= 0 and c >= 0:
            # Caso 3: [pos, pos, pos]
            if a != b and b != c and c != a:
                tri = (safe(a, False), safe(b, False), safe(c, False))
                if valid(tri):
                    triangles.append(tri)
    return triangles
