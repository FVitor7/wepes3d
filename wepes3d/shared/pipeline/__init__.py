"""
shared.pipeline — import/export orchestration.

  * assets    — AssetProfile (the interface between the engine and each asset type).
  * importer  — _import: .obj -> .bin engine (face/trophy), driven by a profile.
  * exporter  — _export: .bin -> .obj engine (face/trophy).
  * folder    — export of a "model folder" (stadium/kit): model/complete/parts/scene.
  * partition — strategies to split the mesh into parts (used by the importer).
"""

from .assets import AssetProfile
from .importer import _import
from .exporter import _export
from . import folder

__all__ = ["AssetProfile", "_import", "_export", "folder"]
