"""
Adapter de ESTADIO: o que difere de face/trofeu.

- Coordenadas: factor = 1/256 = 0.00390625 (escala grande). stored (s0,s1,s2)
  -> obj (s0, s2, -s1)  (deduzido do `stadium_modifier.py`:
  `x,z,y = unpack(3h); v = (x*F, y*F, -z*F)`).
- Navegacao: o payload descompactado e' uma "pasta" de sub-modelos: total em
  [0], offset da tabela (TOC) em [4], e os offsets ABSOLUTOS de cada modelo
  (`MAGIC_MODEL` 03 00 FF FF) a partir do TOC. (Um estadio tem 1..N modelos =
  arquibancadas/quadrantes.) Ver `loader.py` para .str (bloco unico) vs .bin
  (container 00 06 00 00 de varios blocos comprimidos).
- max_parts: None (estadios tem ~120-150 parts por modelo).

Ver docs/09-estadios.md.
"""

from typing import Tuple

from ....shared.constants import NORMAL_SCALE
from ....shared.geometry import CoordSpace, obj_to_int16_uv, int16_to_obj_uv, clamp16
from ....shared.pipeline import AssetProfile
from ....shared.io import model_offsets

STADIUM_VERTEX_FACTOR = 0.00390625
"""1/256. Escala de estadio (muito maior que face/trofeu)."""


# ============================================================================
# Coordenadas do estadio
# ============================================================================

def int16_to_obj_vertex(s0: int, s1: int, s2: int) -> Tuple[float, float, float]:
    """stored (s0,s1,s2) -> OBJ (s0*f, s2*f, -s1*f)."""
    f = STADIUM_VERTEX_FACTOR
    return (s0 * f, s2 * f, -s1 * f)


def obj_to_int16_vertex(x: float, y: float, z: float) -> Tuple[int, int, int]:
    """OBJ (x,y,z) -> stored (x/f, -z/f, y/f) (inverso de int16_to_obj_vertex)."""
    f = STADIUM_VERTEX_FACTOR
    return (clamp16(round(x / f)), clamp16(round(-z / f)), clamp16(round(y / f)))


def obj_to_int16_normal(nx: float, ny: float, nz: float) -> Tuple[int, int, int]:
    """Normal unitaria -> int16, mesma permutacao de eixos dos vertices
    (nx, -nz, ny)."""
    return (clamp16(round(nx * NORMAL_SCALE)),
            clamp16(round(-nz * NORMAL_SCALE)),
            clamp16(round(ny * NORMAL_SCALE)))


COORD = CoordSpace(
    name="stadium",
    obj_to_int16_vertex=obj_to_int16_vertex,
    int16_to_obj_vertex=int16_to_obj_vertex,
    obj_to_int16_uv=obj_to_int16_uv,
    int16_to_obj_uv=int16_to_obj_uv,
    obj_to_int16_normal=obj_to_int16_normal,
)


# ============================================================================
# Navegacao: "pasta" de sub-modelos (generica em shared.pes_archive)
# ============================================================================

def locate(payload: bytes, section: int = 0) -> int:
    """Offset do modelo `section` dentro do payload (bloco) descompactado."""
    offs = model_offsets(payload)
    if not (0 <= section < len(offs)):
        raise ValueError(f"modelo {section} inexistente ({len(offs)} modelos no bloco).")
    return offs[section]


def patch_resize(payload: bytes, model_offset: int, pre_parts_size: int,
                 orig_parts_end: int, new_parts_end: int) -> Tuple[bytes, int]:
    """Resize do estadio (import por partes) ainda nao implementado.

    Para roundtrip de MESMO tamanho (delta == 0) e' no-op. Mudancas de tamanho
    exigiriam deslizar a TOC + offsets dos modelos seguintes + (no .bin) a TOC do
    container externo — sera adicionado quando o import por partes for feito."""
    if new_parts_end == orig_parts_end:
        return payload, 0
    raise NotImplementedError(
        "resize de estadio (import com mudanca de contagem) ainda nao suportado; "
        "use roundtrip de mesmo tamanho ou somente export por enquanto.")


STADIUM_PROFILE = AssetProfile(
    name="stadium", coord=COORD, max_parts=None,
    locate=locate, patch_resize=patch_resize, list_sections=model_offsets,
)
