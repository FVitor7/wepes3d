"""FACE/HAIR API: import_face / export_face (shared engine + FACE_PROFILE)."""

from ....shared.pipeline import _import, _export
from .profile import FACE_PROFILE


def import_face(template_bin_path: str, obj_path: str, output_bin_path: str,
                **kwargs) -> None:
    """Puts the geometry of an `.obj` inside a PES PS2 FACE/HAIR `.bin`.

    Uses `template_bin_path` (an original `.bin`) as a "shell": header, bones
    and texture are kept; only the geometry is replaced by the one in
    `obj_path`. The result is written to `output_bin_path`.

    Example:
        import_face("face.bin", "new_face.obj", "out.bin",
                    allow_recount=True, recalculate_normals=True, auto_fit=True)

    Options (kwargs), all optional:
      - allow_recount: accepts an `.obj` whose vertex count is different from the template.
      - recalculate_normals: computes the normals of the new geometry (recommended).
      - auto_fit: scales/centers the `.obj` into the template bounding box.
      - match_template: partitions by the nearest template vertex (use with auto_fit).
      - use_groups: uses the `g`/`o` groups of the `.obj` as parts.
      - part_sizes_override / max_verts_per_part: manual control of the partition.
      - strip_mode: "connected" (default) or "list".
      - preserve_strips: keeps the original strip in identical parts (default True).

    See docs/00 (user guide) and docs/03 (pipeline) for the details.
    """
    kwargs.pop("section", None)  # a face has no sections
    _import(FACE_PROFILE, template_bin_path, obj_path, output_bin_path, **kwargs)


def export_face(bin_path: str, obj_path: str, write_mtl: bool = True) -> None:
    """Reads a face `.bin` and writes its geometry as `.obj` (+ `.mtl`).

    The `.obj` opens in Blender. `write_mtl=False` skips the material file.

    Example:
        export_face("face.bin", "face.obj")   # writes face.obj + face.mtl
    """
    _export(FACE_PROFILE, bin_path, obj_path, section=0, write_mtl=write_mtl)


__all__ = ["import_face", "export_face", "FACE_PROFILE"]
