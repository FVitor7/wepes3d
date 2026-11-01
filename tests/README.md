# tests/ — automated test suite

Tests of the tool with **pytest** + **coverage** (`pytest-cov`). They use
**real game files** (in [`seed/`](seed/)) to cover the 5 asset types.

> The package itself (runtime) has **no** external dependencies — only the
> Python standard library. `pytest`/`pytest-cov` are **test-only**
> dependencies (see [`../requirements-dev.txt`](../requirements-dev.txt)).

---

## How to run

Install the test dependencies and run from the repository root:

```bash
pip install -r requirements-dev.txt

# runs everything + coverage report (already set in pyproject.toml):
python -m pytest
```

The configuration (in [`../pyproject.toml`](../pyproject.toml)) already turns
on `--cov=wepes3d --cov-report=term-missing`. For an HTML report:

```bash
python -m pytest --cov-report=html
# open htmlcov/index.html
```

### On GitHub (CI)

[`../.github/workflows/tests.yml`](../.github/workflows/tests.yml) runs the
same suite on every push to `main` and on every pull request, with the oldest
supported Python (3.9) and the newest one. The job fails if a test fails or if
the coverage goes below **95%**.

---

## What each file tests

| File | Focus |
|---|---|
| `test_io.py` | `.bin` compression/decompression; `.obj` reading (triangulation, groups, `v`/`vt` indices, UV seams); 1-UV-per-vertex conversion. |
| `test_coords.py` | `CoordSpace`: the `int16 ↔ float` conversion is **lossless** (face/trophy/stadium/PC). |
| `test_geometry.py` | bounding box, auto-fit, normal computation. |
| `test_parser.py` | detection (face/trophy), navigation and serialization (`write_model` is lossless). |
| `test_reader_strip.py` | universal geometry reader + strip encoding/decoding (including degenerate triangles). |
| `test_strip_connected.py` | connected tristrips (winding, encode, the `_measure` demo). |
| `test_partition.py` | how vertices are split into parts (BFS, groups, border errors). |
| `test_export.py` | export of the 5 types: face, trophy, stadium, kit, PES6 PC. |
| `test_import.py` | face/trophy import: roundtrip + each partition strategy + header pointers (`parts_end`) + errors. |
| `test_cli.py` | the 3 subcommands (`export`/`import`/`list`), options and error handling. |
| `test_public_api.py` | high-level API (`import_auto`/`export_auto` + compatibility wrappers). |
| `test_edge_cases.py` | error/defensive paths (invalid magics, missing sections…). |

---

## The seed files (`seed/`)

They are small real files, one for each code path:

| Seed | Type | Notes |
|---|---|---|
| `face.bin` | PS2 face | 8 parts, 696 v (the same as in `examples/`). |
| `face.obj` | face export | used in the import/roundtrip tests. |
| `trophy.bin` | PS2 trophy | container with **9 sections** (sub-models). |
| `stadium.str` | stadium (crowd) | a single compressed block, 1 model. |
| `stadium_data.bin` | stadium (container) | container with **0 models** (only data/texture). |
| `adboard.bin` | stadium (boards) | container **with models** (scan path). |
| `kit.bin` | kit (hands) | 4 models (LODs). |
| `pc_face.bin` | PES6 PC face | `20050420` format, 1 model. |
| `pc_trophy.str` | PES6 PC trophy | container with 9 parts. |

Synthetic `.obj` files (grid, islands, ribbon) are **generated in memory** by
the fixtures in [`conftest.py`](conftest.py) — they do not need to be on disk.

---

## Coverage

The goal is to **cover all the code** of the package. What is left without
coverage is a few **defensive** lines (error exits for rare corrupted files,
expansion of trophy parts, and reading of multi-submesh geometry that the seed
files do not use). Run with `--cov-report=term-missing` to see exactly which
ones.
