"""
adapters — one sub-package per PLATFORM, and inside it one per asset TYPE.

  * pesweps2 — PES/WE PlayStation 2 (int16, 0300ffff model, VIF unpacks).
               faces, trophies, stadiums, kits. Import + export.
  * pes6pc   — PES6/WE PC (float32, 20050420 model, strips per vertex group).
               faces, trophies. Export ONLY (.bin/.str -> .obj).

PC and PS2 are DIFFERENT binary formats: PC does not reuse the PS2 engine
(`shared/pipeline`/`shared/model`), only the common I/O (`shared/io`: zlib
decompression + .obj writing). Each platform lives in its own folder.

A PS2 adapter is thin: `profile.py` (CoordSpace + navigation + AssetProfile)
+ `__init__.py` (import_/export_ wrappers that call the `shared/` engine).
See docs/10-architecture.md.
"""
