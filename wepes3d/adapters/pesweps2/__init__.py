"""
pesweps2 — adapters do PES/WE PlayStation 2 (int16, modelo 0300ffff, VIF).

Reexporta a API import_/export_ de cada tipo de asset PS2. FACE/TROFEU usam o
motor importer/exporter de `shared/pipeline`; ESTADIO/KIT (so export) usam
`shared/pipeline/folder` (pasta de modelos).
"""

from .faces import import_face, export_face, FACE_PROFILE
from .trophies import (
    import_trophy, export_trophy, trophy_section_offsets, TROPHY_PROFILE,
)
from .stadiums import (
    export_stadium, export_stadium_complete, export_stadium_parts,
    export_stadium_scene, list_stadium, stadium_index,
)
from .kits import (
    export_kit, export_kit_complete, export_kit_parts, export_kit_scene,
    list_kit, kit_index,
)

__all__ = [
    "import_face", "export_face", "FACE_PROFILE",
    "import_trophy", "export_trophy", "trophy_section_offsets", "TROPHY_PROFILE",
    "export_stadium", "export_stadium_complete", "export_stadium_parts",
    "export_stadium_scene", "list_stadium", "stadium_index",
    "export_kit", "export_kit_complete", "export_kit_parts", "export_kit_scene",
    "list_kit", "kit_index",
]
