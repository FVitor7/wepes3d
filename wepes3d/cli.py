"""
CLI: three subcommands, each with its own positional arguments and options.

    python -m wepes3d <command> ...

  export   .bin/.str -> .obj   (PS2 face/trophy/stadium/kit + PES6 PC)
  import   .obj -> .bin        (PS2 face/trophy only)
  list     shows the structure of the file

Examples:
    python -m wepes3d export face.bin face.obj
    python -m wepes3d export trophy.bin t.obj --section 2
    python -m wepes3d export pl.str trophy.obj --type pc --all
    python -m wepes3d export pl.str cup.obj    --type pc --model 0
    python -m wepes3d import face.bin new.obj out.bin \\
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

# "Model folder" types (1 .bin = N models): export by model/complete/parts.
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
        description="PES: exports/imports 3D models between .bin/.str and .obj "
                    "(PS2: face/trophy/stadium/kit; PES6 PC: face/trophy).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True, metavar="command")

    _add_export(sub)
    _add_import(sub)
    _add_list(sub)
    return parser


def _add_export(sub) -> None:
    p = sub.add_parser(
        "export", help=".bin/.str -> .obj",
        description="Exports the geometry of a .bin/.str to .obj (+ .mtl).",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
By type:
  auto/face/trophy (PS2) : exports 1 model. Trophy: pick the sub-model with
                           --section N (0 = main).
  stadium/kit/pc         : "model folder" — pick:
                             (nothing) / --all : all models in one .obj
                             --model M         : only model M (--block B narrows it)
                             --parts           : one .obj per model (OUT = prefix)
                           --groups (1 'o' per part) and --dedup also work here.
""")
    p.add_argument("input", help="Input .bin/.str.")
    p.add_argument("out", help="Output .obj (or a prefix, with --parts).")
    p.add_argument("--type", choices=ALL_TYPES, default="auto",
        help="File type (default: auto = detects PS2 face/trophy).")
    p.add_argument("--section", type=int, default=0, metavar="N",
        help="PS2 TROPHY: which sub-model (.mdl). 0 = main (default).")

    sel = p.add_mutually_exclusive_group()
    sel.add_argument("--all", "--complete", dest="all", action="store_true",
        help="model folder: ALL models in one .obj (default).")
    sel.add_argument("--parts", action="store_true",
        help="model folder: one .obj per model (OUT becomes a prefix).")
    sel.add_argument("--model", type=int, default=None, metavar="M",
        help="model folder: exports ONLY model M.")
    p.add_argument("--block", type=int, default=None, metavar="B",
        help="model folder: limits --model to one block of the container.")
    p.add_argument("--groups", action="store_true",
        help="model folder: 1 'o part_NN' object per part in the .obj.")
    p.add_argument("--dedup", action="store_true",
        help="model folder: removes duplicated parts/models.")
    p.set_defaults(func=cmd_export)


def _add_import(sub) -> None:
    p = sub.add_parser(
        "import", help=".obj -> .bin (PS2 only)",
        description="Imports an .obj into a PES PS2 FACE or TROPHY .bin.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Partition strategies (pick only 1; default = BFS by face adjacency):
  --use-groups         : each 'g'/'o' of the .obj becomes a part (manual control
                         in Blender). Number of groups must = number of parts
                         in the template.
  --part-sizes L       : you choose how many vertices go in each part (comma
                         separated list; the sum = vertices in the .obj).
  --max-verts-per-part : limits the vertices per part (creates new parts if
                         needed; max 8 for faces, the game limit).
--match-template partitions by nearest neighbour in template space (use it
with --auto-fit). All of these need --allow-recount.

Examples:
  ... import face.bin my.obj out.bin --recalculate-normals
  ... import face.bin new.obj out.bin --allow-recount --recalculate-normals --auto-fit
""")
    p.add_argument("template", help="Template .bin (the base that will be changed).")
    p.add_argument("obj", help=".obj with the new geometry.")
    p.add_argument("out", help="Output .bin.")
    p.add_argument("--type", choices=["auto", "face", "trophy"], default="auto",
        help="Template type (default: auto). PC does not support import.")
    p.add_argument("--section", type=int, default=0, metavar="N",
        help="TROPHY: which sub-model (.mdl) to replace. 0 = main.")

    p.add_argument("--recalculate-normals", action="store_true",
        help="Recalculates the normals of the new geometry (recommended).")
    p.add_argument("--allow-recount", action="store_true",
        help="Allows an .obj whose vertex count is different from the template.")
    p.add_argument("--auto-fit", action="store_true",
        help="Scales/centers the .obj vertices into the template bbox.")

    part = p.add_mutually_exclusive_group()
    part.add_argument("--use-groups", action="store_true",
        help="Uses the 'g'/'o' groups of the .obj as parts. Needs --allow-recount.")
    part.add_argument("--part-sizes", type=str, default=None, metavar="L",
        help="Manual sizes per part (csv). Needs --allow-recount.")
    part.add_argument("--max-verts-per-part", type=int, default=None, metavar="N",
        help="Limits the vertices per part. Needs --allow-recount.")
    p.add_argument("--match-template", action="store_true",
        help="Partitions by nearest neighbour in template space (use it with --auto-fit).")

    p.add_argument("--no-preserve-strips", action="store_true",
        help="Re-encodes ALL strips (even for parts identical to the template) "
             "— turns off the zero-diff passthrough.")
    p.add_argument("--strip-mode", choices=["connected", "list"], default="connected",
        help="Encoding of the strips of NEW parts: 'connected' (default — "
             "connected tristrips, ~35%% smaller, checked in the game) or 'list' "
             "(triangle list, legacy format). See docs/05-strip-encoding.md.")
    p.set_defaults(func=cmd_import)


def _add_list(sub) -> None:
    p = sub.add_parser(
        "list", help="shows the structure of the file",
        description="Prints the structure (models/parts/sections) of the .bin/.str.")
    p.add_argument("input", help="Input .bin/.str.")
    p.add_argument("--type", choices=ALL_TYPES, default="auto",
        help="File type (default: auto).")
    p.set_defaults(func=cmd_list)


# ============================================================================
# Commands
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
        else:  # default and --all: everything in one .obj
            f_complete(args.input, args.out, dedup=args.dedup)
        return

    # PS2 face/trophy: 1 model. The "model folder" options do not apply.
    if args.all or args.parts or args.model is not None or args.block is not None \
            or args.groups or args.dedup:
        parser_error("--all/--parts/--model/--block/--groups/--dedup only work "
                     "with --type stadium|kit|pc.")
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
        parser_error(f"{needs_recount} needs --allow-recount.")

    part_sizes = None
    if args.part_sizes:
        try:
            part_sizes = [int(x.strip()) for x in args.part_sizes.split(",")]
        except ValueError:
            parser_error("--part-sizes must be integers separated by commas.")

    # Only the OPTIONS (they go into **kwargs). The paths are passed as
    # positional strings, so we do not unpack mixed types into the typed
    # template/obj/output parameters.
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
    else:  # auto: import_auto finds face/trophy from the magic (a face ignores section)
        import_auto(args.template, args.obj, args.out, section=args.section, **opts)


def cmd_list(args) -> None:
    if args.type in FOLDER_FN:
        FOLDER_FN[args.type][0](args.input)   # list_stadium / list_kit / list_pc
        return
    # PS2 face/trophy (auto/face/trophy)
    payload, _, _ = decompress_bin(args.input)
    kind = detect_asset_type(payload)
    if kind == "trophy":
        secs = trophy_section_offsets(payload)
        print(f"{args.input}: PS2 trophy — {len(secs)} section(s) (sub-models).")
        for i, off in enumerate(secs):
            print(f"  section {i:>2}: offset 0x{off:X}"
                  + ("  (main)" if i == 0 else ""))
    else:
        print(f"{args.input}: PS2 face/hair — 1 model (use export to see "
              "vertices/faces).")


# ============================================================================
# Utilities
# ============================================================================

_PARSER = None


def _error_fn():
    """Returns parser.error (uses the global parser, for consistent messages)."""
    assert _PARSER is not None, "parser not initialized"
    return _PARSER.error


def main() -> None:
    global _PARSER
    _PARSER = build_parser()
    args = _PARSER.parse_args()
    # "Expected" errors (bad data / wrong file) become a clean message, with
    # no traceback. Real bugs (any other exception) still show the full
    # traceback.
    try:
        args.func(args)
    except FileNotFoundError as e:
        _fail(f"file not found: {e.filename or e}")
    except struct.error as e:
        _fail(f"corrupted file or unexpected format ({e}).")
    except (ValueError, IndexError, KeyError, NotImplementedError,
            IsADirectoryError, PermissionError) as e:
        _fail(str(e))
    except KeyboardInterrupt:
        _fail("cancelled by the user.", code=130)


def _fail(msg: str, code: int = 1) -> None:
    """Prints an error message in the parser style and exits."""
    prog = _PARSER.prog if _PARSER else "wepes3d"
    print(f"{prog}: error: {msg}", file=sys.stderr)
    sys.exit(code)
