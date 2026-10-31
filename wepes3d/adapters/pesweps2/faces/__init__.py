"""API de FACE/CABELO: import_face / export_face (motor compartilhado + FACE_PROFILE)."""

from ....shared.pipeline import _import, _export
from .profile import FACE_PROFILE


def import_face(template_bin_path: str, obj_path: str, output_bin_path: str,
                **kwargs) -> None:
    """Coloca a geometria de um `.obj` dentro de um `.bin` de FACE/CABELO do PES PS2.

    Usa `template_bin_path` (um `.bin` original) como "casca": header, bones e
    textura sao preservados; so a geometria e' trocada pela do `obj_path`. O
    resultado e' gravado em `output_bin_path`.

    Exemplo:
        import_face("face.bin", "rosto.obj", "saida.bin",
                    allow_recount=True, recalculate_normals=True, auto_fit=True)

    Opcoes (kwargs), todas opcionais:
      - allow_recount: aceita um `.obj` com numero de vertices diferente do template.
      - recalculate_normals: calcula as normais da geometria nova (recomendado).
      - auto_fit: escala/centra o `.obj` no bounding box do template.
      - match_template: particiona por vizinho mais proximo do template (com auto_fit).
      - use_groups: usa os grupos `g`/`o` do `.obj` como parts.
      - part_sizes_override / max_verts_per_part: controle manual da particao.
      - strip_mode: "connected" (default) ou "list".
      - preserve_strips: mantem o strip original em parts identicas (default True).

    Ver docs/00 (guia de uso) e docs/03 (pipeline) para os detalhes.
    """
    kwargs.pop("section", None)  # face nao tem secoes
    _import(FACE_PROFILE, template_bin_path, obj_path, output_bin_path, **kwargs)


def export_face(bin_path: str, obj_path: str, write_mtl: bool = True) -> None:
    """Le um `.bin` de face e grava a geometria como `.obj` (+ `.mtl`).

    O `.obj` abre no Blender. `write_mtl=False` pula o arquivo de material.

    Exemplo:
        export_face("face.bin", "face.obj")   # gera face.obj + face.mtl
    """
    _export(FACE_PROFILE, bin_path, obj_path, section=0, write_mtl=write_mtl)


__all__ = ["import_face", "export_face", "FACE_PROFILE"]
