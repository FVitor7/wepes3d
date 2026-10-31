"""
shared.pipeline — orquestracao import/export.

  * assets    — AssetProfile (a interface entre o motor e cada tipo de asset).
  * importer  — _import: motor .obj -> .bin (face/trofeu), parametrizado por profile.
  * exporter  — _export: motor .bin -> .obj (face/trofeu).
  * folder    — export de "pasta de modelos" (estadio/kit): modelo/completo/partes/cena.
  * partition — estrategias de particionamento do mesh em parts (usado pelo importer).
"""

from .assets import AssetProfile
from .importer import _import
from .exporter import _export
from . import folder

__all__ = ["AssetProfile", "_import", "_export", "folder"]
