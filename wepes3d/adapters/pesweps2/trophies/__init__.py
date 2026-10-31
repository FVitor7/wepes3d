"""TROPHY API: import_trophy / export_trophy (shared engine + TROPHY_PROFILE)."""

from ....shared.pipeline import _import, _export
from .profile import TROPHY_PROFILE, section_offsets as trophy_section_offsets


def import_trophy(template_bin_path: str, obj_path: str, output_bin_path: str,
                  section: int = 0, **kwargs) -> None:
    """Imports an .obj into a sub-model (.mdl) of a TROPHY .bin.

    section: 0 = main trophy (default); 1+ = stand/stage/etc.
    Same kwargs as import_face (recalculate_normals, allow_recount, auto_fit...)."""
    _import(TROPHY_PROFILE, template_bin_path, obj_path, output_bin_path,
            section=section, **kwargs)


def export_trophy(bin_path: str, obj_path: str, section: int = 0,
                  write_mtl: bool = True) -> None:
    """Exports a sub-model (.mdl) of a trophy to .obj (+ .mtl).
    section: 0 = main trophy; 1+ = stand/stage/etc."""
    _export(TROPHY_PROFILE, bin_path, obj_path, section=section, write_mtl=write_mtl)


__all__ = ["import_trophy", "export_trophy", "trophy_section_offsets", "TROPHY_PROFILE"]
