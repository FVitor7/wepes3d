"""
Leitura do "sistema de arquivos" do PES PS2 (compartilhado por estadio e kit).

Dois invólucros:
  * bloco comprimido — magic 00 06 01 00 (igual face/trofeu/.str): 32 bytes de
    header + zlib. Descompacta para UM payload.
  * container        — magic 00 06 00 00: "pasta" do PES, possivelmente ANINHADA
    (container dentro de container) ate chegar nos blocos comprimidos. Cada bloco
    descompacta para um payload com 0..N modelos.

`load_blocks(path)` devolve a lista de payloads descompactados:
  - 00 06 01 00: descompacta direto (1 payload);
  - 00 06 00 00: VARRE o arquivo por TODOS os blocos 00 06 01 00 validos (em
    qualquer profundidade) e descompacta cada um — robusto a aninhamento, sem
    navegar as TOCs; valida cada candidato pela propria descompactacao (tamanho
    == campo decomp_size do header).

Um payload descompactado e' uma "pasta de modelos": [0]=total, [4]=offset da
TOC, TOC[i] (uint32) = offset ABSOLUTO do modelo i (`MAGIC_MODEL` 03 00 FF FF).
`model_offsets(payload)` resolve isso (pula entradas que nao sao modelo).
"""

import struct
import zlib
from typing import List

from .bin_io import decompress_bin, decompress_payload
from ..constants import MAGIC_MODEL

PES_ZLIB_MAGIC = bytes([0x00, 0x06, 0x01, 0x00])     # bloco comprimido
PES_FOLDER_MAGIC = bytes([0x00, 0x06, 0x00, 0x00])   # container
HEADER_SIZE = 32


def is_container(data: bytes) -> bool:
    return data[:4] == PES_FOLDER_MAGIC


def _scan_zlib_blocks(data: bytes) -> List[bytes]:
    """Acha e descompacta todos os blocos 00 06 01 00 validos em `data`.

    Aceita um candidato se o stream zlib (em +32) descompacta sem erro e o
    tamanho bate com decomp_size (header +8). Avanca pelo comp_size (header +4)
    para nao re-varrer dentro do bloco."""
    out: List[bytes] = []
    pos = 0
    n = len(data)
    while True:
        i = data.find(PES_ZLIB_MAGIC, pos)
        if i < 0 or i + 32 > n:
            break
        comp_size = struct.unpack_from("<I", data, i + 4)[0]
        decomp_size = struct.unpack_from("<I", data, i + 8)[0]
        advanced = False
        if 0 < decomp_size and 0 < comp_size <= n - (i + 32):
            try:
                raw = zlib.decompressobj().decompress(data[i + 32:])
                if len(raw) == decomp_size:
                    out.append(raw)
                    pos = i + 32 + comp_size
                    advanced = True
            except zlib.error:
                pass
        if not advanced:
            pos = i + 4
    return out


def load_blocks(path: str) -> List[bytes]:
    """Lista de payloads descompactados (1 para bloco comprimido, N para um
    container, em qualquer profundidade)."""
    with open(path, "rb") as f:
        data = f.read()
    magic = data[:4]

    if magic == PES_ZLIB_MAGIC:
        payload, _, _ = decompress_bin(path)
        return [payload]

    if magic == PES_FOLDER_MAGIC:
        return _scan_zlib_blocks(data)

    raise ValueError(
        f"magic desconhecido: {magic.hex()} "
        f"(esperado {PES_ZLIB_MAGIC.hex()} comprimido ou {PES_FOLDER_MAGIC.hex()} container)")


def model_offsets(payload: bytes) -> List[int]:
    """Offsets ABSOLUTOS de cada modelo (`MAGIC_MODEL`) no payload descompactado.
    Layout: [0]=total, [4]=offset da TOC, TOC[i] (uint32) = offset do modelo i.
    Entradas que nao apontam para `MAGIC_MODEL` (texturas/dados) sao ignoradas."""
    if len(payload) < 8:
        return []
    total = struct.unpack_from("<I", payload, 0)[0]
    toc = struct.unpack_from("<I", payload, 4)[0]
    offsets: List[int] = []
    for i in range(total):
        pos = toc + 4 * i
        if pos + 4 > len(payload):
            break
        o = struct.unpack_from("<I", payload, pos)[0]
        if 0 <= o + 4 <= len(payload) and payload[o:o + 4] == MAGIC_MODEL:
            offsets.append(o)
    return offsets
