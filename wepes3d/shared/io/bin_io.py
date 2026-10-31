"""
Compressao e descompressao de arquivos .bin do PES PS2.

O formato .bin do PES PS2 tem:
  [outer_header: 16 bytes] [ps2_extra: 16 bytes] [zlib_payload]

O payload descompactado eh o conteudo "real" — o que o parser interpreta.
O outer_header guarda:
  - bytes [4..8]: tamanho do payload comprimido
  - bytes [8..12]: tamanho do payload descompactado

Os outros bytes do header sao preservados intactos durante roundtrip
(sao headers do sistema de arquivos do PES, nao interessam ao modelo 3D).
"""

import struct
import zlib
from typing import Tuple


def decompress_bin(filepath: str) -> Tuple[bytes, bytes, bytes]:
    """
    Le e descompacta um .bin do PES PS2.

    Returns:
        payload: bytes descompactados (o conteudo "real" do modelo).
        outer_full_header: 32 bytes iniciais (outer_header + ps2_extra).
        trailing: dados apos o blob zlib (geralmente vazio, preservado para
            roundtrip).
    """
    with open(filepath, 'rb') as f:
        outer_header = f.read(16)
        ps2_extra = f.read(16)
        zlib_blob = f.read()

    decompressor = zlib.decompressobj()
    payload = decompressor.decompress(zlib_blob)
    trailing = decompressor.unused_data

    return payload, outer_header + ps2_extra, trailing


def decompress_payload(block: bytes) -> bytes:
    """
    Descompacta um bloco .bin a partir de BYTES (em vez de caminho).

    `block` deve comecar pelo header de 32 bytes (magic 00 06 01 00 +
    tamanhos) seguido do blob zlib. Bytes apos o stream zlib (ex.: o proximo
    bloco de um container) sao ignorados. Util para blocos comprimidos dentro
    de um container 00 06 00 00 (estadios).
    """
    decompressor = zlib.decompressobj()
    return decompressor.decompress(block[32:])


def compress_bin(payload: bytes, outer_full_header: bytes, trailing: bytes,
                 output_path: str) -> None:
    """
    Compacta um payload e escreve no formato .bin do PES PS2.

    Atualiza os campos de tamanho no outer header:
      - byte[4..8]:  uint32 LE = tamanho do payload comprimido
      - byte[8..12]: uint32 LE = tamanho do payload descompactado

    Os demais bytes do header sao preservados como veio.
    """
    compressed = zlib.compress(payload, 9)

    new_header = bytearray(outer_full_header)
    struct.pack_into("<I", new_header, 4, len(compressed))
    struct.pack_into("<I", new_header, 8, len(payload))

    with open(output_path, 'wb') as f:
        f.write(new_header)
        f.write(compressed)
        f.write(trailing)
