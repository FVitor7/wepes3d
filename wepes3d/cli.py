"""
CLI: tres subcomandos, cada um com seus positionais e flags.

    python -m wepes3d <comando> ...

  export   .bin/.str -> .obj   (PS2 face/trofeu/estadio/kit + PES6 PC)
  import   .obj -> .bin        (so PS2 face/trofeu)
  list     mostra a estrutura do arquivo

Exemplos:
    python -m wepes3d export face.bin rosto.obj
    python -m wepes3d export trofeu.bin t.obj --section 2
    python -m wepes3d export pl.str trofeu.obj --type pc --all
    python -m wepes3d export pl.str taca.obj  --type pc --model 0
    python -m wepes3d import face.bin novo.obj saida.bin \\
        --allow-recount --recalculate-normals --auto-fit
    python -m wepes3d list pl.str --type pc
"""

import argparse
import struct
import sys

from . import (
    import_face, import_trophy, import_auto,
    export_face, export_trophy, export_auto,
    export_stadium, export_stadium_complete, export_stadium_parts, list_stadium,
    export_kit, export_kit_complete, export_kit_parts, list_kit,
    export_pc, export_pc_complete, export_pc_parts, list_pc,
    decompress_bin, detect_asset_type, trophy_section_offsets,
)

# Tipos "pasta de modelos" (1 .bin = N modelos): export por modelo/completo/partes.
FOLDER_FN = {
    "stadium": (list_stadium, export_stadium, export_stadium_complete, export_stadium_parts),
    "kit":     (list_kit, export_kit, export_kit_complete, export_kit_parts),
    "pc":      (list_pc, export_pc, export_pc_complete, export_pc_parts),
}
ALL_TYPES = ["auto", "face", "trophy", "stadium", "kit", "pc"]


# ============================================================================
# Parser
# ============================================================================

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="wepes3d",
        description="PES: exporta/importa modelos 3D entre .bin/.str e .obj "
                    "(PS2: face/trofeu/estadio/kit; PES6 PC: face/trofeu).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="comando")

    _add_export(sub)
    _add_import(sub)
    _add_list(sub)
    return parser


def _add_export(sub) -> None:
    p = sub.add_parser(
        "export", help=".bin/.str -> .obj",
        description="Exporta a geometria de um .bin/.str para .obj (+ .mtl).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Por tipo:
  auto/face/trophy (PS2) : exporta 1 modelo. Trofeu: escolha o sub-modelo com
                           --section N (0 = principal).
  stadium/kit/pc         : "pasta de modelos" — escolha:
                             (nada) / --all : todos os modelos num .obj so
                             --model M      : so o modelo M (--block B restringe)
                             --parts        : um .obj por modelo (OUT = prefixo)
                           --groups (1 'o' por part) e --dedup tambem valem aqui.
""")
    p.add_argument("input", help=".bin/.str de entrada.")
    p.add_argument("out", help=".obj de saida (ou prefixo, com --parts).")
    p.add_argument("--type", choices=ALL_TYPES, default="auto",
        help="Tipo do arquivo (default: auto = detecta face/trofeu PS2).")
    p.add_argument("--section", type=int, default=0, metavar="N",
        help="TROFEU PS2: qual sub-modelo (.mdl). 0 = principal (default).")

    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--all", "--complete", dest="all", action="store_true",
        help="pasta de modelos: TODOS os modelos num .obj so (default).")
    sel.add_argument("--parts", action="store_true",
        help="pasta de modelos: um .obj por modelo (OUT vira prefixo).")
    sel.add_argument("--model", type=int, default=None, metavar="M",
        help="pasta de modelos: exporta SO o modelo M.")
    p.add_argument("--block", type=int, default=None, metavar="B",
        help="pasta de modelos: restringe --model a um bloco do container.")
    p.add_argument("--groups", action="store_true",
        help="pasta de modelos: 1 objeto 'o part_NN' por part no .obj.")
    p.add_argument("--dedup", action="store_true",
        help="pasta de modelos: remove parts/modelos duplicados.")
    p.set_defaults(func=cmd_export)


def _add_import(sub) -> None:
    p = sub.add_parser(
        "import", help=".obj -> .bin (so PS2)",
        description="Importa um .obj para um .bin de FACE ou TROFEU do PES PS2.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Estrategias de particionamento (mutuamente exclusivas — escolha 1; default = BFS
por adjacencia de faces):
  --use-groups         : cada 'g'/'o' do .obj vira uma part (controle manual no
                         Blender). Nº de grupos deve = nº de parts do template.
  --part-sizes L       : voce define quantos vertices por part (lista por virgula;
                         soma = total de vertices do .obj).
  --max-verts-per-part : limita vertices por part (cria parts novas se precisar;
                         max 8, limite do jogo).
--match-template particiona por nearest-neighbor no espaco do template (use com
--auto-fit). Todas estas requerem --allow-recount.

Exemplos:
  ... import face.bin meu.obj saida.bin --recalculate-normals
  ... import face.bin novo.obj saida.bin --allow-recount --recalculate-normals --auto-fit
""")
    p.add_argument("template", help=".bin template (base a ser modificada).")
    p.add_argument("obj", help=".obj com a nova geometria.")
    p.add_argument("out", help=".bin de saida.")
    p.add_argument("--type", choices=["auto", "face", "trophy"], default="auto",
        help="Tipo do template (default: auto). PC nao suporta import.")
    p.add_argument("--section", type=int, default=0, metavar="N",
        help="TROFEU: qual sub-modelo (.mdl) substituir. 0 = principal.")

    p.add_argument("--recalculate-normals", action="store_true",
        help="Recalcula normais da nova geometria (recomendado).")
    p.add_argument("--allow-recount", action="store_true",
        help="Permite .obj com contagem de vertices diferente do template.")
    p.add_argument("--auto-fit", action="store_true",
        help="Escala/centra os vertices do .obj no bbox do template.")

    part = p.add_mutually_exclusive_group()
    part.add_argument("--use-groups", action="store_true",
        help="Usa grupos 'g'/'o' do .obj como parts. Requer --allow-recount.")
    part.add_argument("--part-sizes", type=str, default=None, metavar="L",
        help="Sizes manuais por part (csv). Requer --allow-recount.")
    part.add_argument("--max-verts-per-part", type=int, default=None, metavar="N",
        help="Limita vertices por part. Requer --allow-recount.")
    p.add_argument("--match-template", action="store_true",
        help="Particiona via nearest-neighbor no espaco do template (use com --auto-fit).")

    p.add_argument("--no-preserve-strips", action="store_true",
        help="Re-codifica TODOS os strips (mesmo de parts identicas ao template) "
             "— desliga o passthrough zero-diff.")
    p.add_argument("--strip-mode", choices=["connected", "list"], default="connected",
        help="Codificacao dos strips de parts NOVAS: 'connected' (default — "
             "tristrips conectados, ~35%% menores, validado in-game) ou 'list' "
             "(triangle list, formato legado). Ver docs/05-strip-encoding.md.")
    p.set_defaults(func=cmd_import)


def _add_list(sub) -> None:
    p = sub.add_parser(
        "list", help="mostra a estrutura do arquivo",
        description="Imprime a estrutura (modelos/partes/secoes) do .bin/.str.")
    p.add_argument("input", help=".bin/.str de entrada.")
    p.add_argument("--type", choices=ALL_TYPES, default="auto",
        help="Tipo do arquivo (default: auto).")
    p.set_defaults(func=cmd_list)


# ============================================================================
# Comandos
# ============================================================================

def cmd_export(args) -> None:
    parser_error = _error_fn()
    if args.type in FOLDER_FN:
        _f_list, f_one, f_complete, f_parts = FOLDER_FN[args.type]
        if args.parts:
            prefix = args.out[:-4] if args.out.lower().endswith(".obj") else args.out
            f_parts(args.input, prefix, groups=args.groups, dedup=args.dedup)
        elif args.model is not None or args.block is not None:
            f_one(args.input, args.out, model=args.model or 0, block=args.block,
                  groups=args.groups, dedup=args.dedup)
        else:  # default e --all: tudo num .obj
            f_complete(args.input, args.out, dedup=args.dedup)
        return

    # PS2 face/trofeu: 1 modelo. Flags de "pasta de modelos" nao se aplicam.
    if args.all or args.parts or args.model is not None or args.block is not None \
            or args.groups or args.dedup:
        parser_error("--all/--parts/--model/--block/--groups/--dedup so valem "
                     "para --type stadium|kit|pc.")
    if args.type == "face":
        export_face(args.input, args.out)
    elif args.type == "trophy":
        export_trophy(args.input, args.out, section=args.section)
    else:  # auto
        export_auto(args.input, args.out, section=args.section)


def cmd_import(args) -> None:
    parser_error = _error_fn()
    needs_recount = ("--use-groups" if args.use_groups else
                     "--part-sizes" if args.part_sizes else
                     "--max-verts-per-part" if args.max_verts_per_part is not None
                     else None)
    if needs_recount and not args.allow_recount:
        parser_error(f"{needs_recount} requer --allow-recount.")

    part_sizes = None
    if args.part_sizes:
        try:
            part_sizes = [int(x.strip()) for x in args.part_sizes.split(",")]
        except ValueError:
            parser_error("--part-sizes deve ser inteiros separados por virgula.")

    # So as OPCOES (fluem pro **kwargs). Os caminhos vao posicionais (str), p/
    # nao desempacotar tipos variados nos params tipados template/obj/output.
    opts = dict(
        recalculate_normals=args.recalculate_normals,
        allow_recount=args.allow_recount,
        part_sizes_override=part_sizes,
        max_verts_per_part=args.max_verts_per_part,
        use_groups=args.use_groups,
        auto_fit=args.auto_fit,
        match_template=args.match_template,
        preserve_strips=not args.no_preserve_strips,
        strip_mode=args.strip_mode,
    )
    if args.type == "face":
        import_face(args.template, args.obj, args.out, **opts)
    elif args.type == "trophy":
        import_trophy(args.template, args.obj, args.out, section=args.section, **opts)
    else:  # auto: import_auto detecta face/trofeu pelo magic (face descarta section)
        import_auto(args.template, args.obj, args.out, section=args.section, **opts)


def cmd_list(args) -> None:
    if args.type in FOLDER_FN:
        FOLDER_FN[args.type][0](args.input)   # list_stadium / list_kit / list_pc
        return
    # PS2 face/trofeu (auto/face/trophy)
    payload, _, _ = decompress_bin(args.input)
    kind = detect_asset_type(payload)
    if kind == "trophy":
        secs = trophy_section_offsets(payload)
        print(f"{args.input}: PS2 trofeu — {len(secs)} secao(oes) (sub-modelos).")
        for i, off in enumerate(secs):
            print(f"  secao {i:>2}: offset 0x{off:X}"
                  + ("  (principal)" if i == 0 else ""))
    else:
        print(f"{args.input}: PS2 face/cabelo — 1 modelo (use export para ver "
              "vertices/faces).")


# ============================================================================
# Util
# ============================================================================

_PARSER = None


def _error_fn():
    """Devolve parser.error (usa o parser global p/ mensagens consistentes)."""
    assert _PARSER is not None, "parser nao inicializado"
    return _PARSER.error


def main() -> None:
    global _PARSER
    _PARSER = build_parser()
    args = _PARSER.parse_args()
    # Erros "esperados" (dado ruim / arquivo errado) viram alerta limpo, sem
    # traceback. Bugs de verdade (qualquer outra excecao) ainda estouram completo.
    try:
        args.func(args)
    except FileNotFoundError as e:
        _fail(f"arquivo nao encontrado: {e.filename or e}")
    except struct.error as e:
        _fail(f"arquivo corrompido ou formato inesperado ({e}).")
    except (ValueError, IndexError, KeyError, NotImplementedError,
            IsADirectoryError, PermissionError) as e:
        _fail(str(e))
    except KeyboardInterrupt:
        _fail("cancelado pelo usuario.", code=130)


def _fail(msg: str, code: int = 1) -> None:
    """Imprime um alerta de erro no padrao do parser e encerra."""
    prog = _PARSER.prog if _PARSER else "wepes3d"
    print(f"{prog}: erro: {msg}", file=sys.stderr)
    sys.exit(code)
