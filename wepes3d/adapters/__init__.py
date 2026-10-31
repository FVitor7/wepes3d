"""
adapters — um subpacote por PLATAFORMA, e dentro dela por TIPO de asset.

  * pesweps2 — PES/WE PlayStation 2 (int16, modelo 0300ffff, VIF unpacks).
               faces, trophies, stadiums, kits. Import + export.
  * pes6pc   — PES6/WE PC (float32, modelo 20050420, strips por vertex group).
               faces, trophies. SO export (.bin/.str -> .obj).

PC e PS2 sao formatos binarios DIFERENTES: PC nao reaproveita o motor PS2
(`shared/pipeline`/`shared/model`), so a I/O comum (`shared/io`: descompressao
zlib + escrita de .obj). Cada plataforma e' isolada na sua pasta.

Adapter PS2 e' fino: `profile.py` (CoordSpace + navegacao + AssetProfile) +
`__init__.py` (wrappers import_/export_ que delegam ao motor `shared/`).
Ver docs/11-arquitetura.md.
"""
