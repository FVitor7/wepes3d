# examples/ — sample files

This folder has a **real game file**, so you can try the tool without
extracting anything. Everything here is used by the step-by-step tour
[docs/13 — A face, byte by byte](../docs/13-face-byte-by-byte.md).

| File | What it is | Size |
|---|---|---|
| `face.bin` | a **PES PS2 face/hair** ("simple" template, 8 parts, 696 vertices) | 25,761 B |
| `face.obj` | the **export** of `face.bin` (made by the tool itself) | ~60 KB |
| `face.mtl` | the material of the `.obj` (points to `face.png`, the texture) | — |

> `face.obj`/`face.mtl` are **generated** from `face.bin`. You can create them
> again at any time with the `export` command below.

---

## Try it (run from the repository root)

```bash
# 1) LIST — tells you the file type
python -m wepes3d list examples/face.bin --type face

# 2) EXPORT — .bin → .obj (open it in Blender)
python -m wepes3d export examples/face.bin my_face.obj --type face

# 3) IMPORT — .obj → .bin (uses face.bin as the "shell"/template)
python -m wepes3d import examples/face.bin my_face.obj out.bin --type face
```

With the Python API:

```python
from wepes3d import export_face, import_face
export_face("examples/face.bin", "my_face.obj")
import_face("examples/face.bin", "my_face.obj", "out.bin")
```

---

## What to expect

- `face.bin` is a template **without bones** (a static face) — the easiest
  path to import new geometry. See
  [docs/01 §4](../docs/01-bin-format.md#4-simple-vs-rich-templates).
- The `export` reports `696 v, 984 faces`.
- To learn what "identical roundtrip" means (and what is **not**
  byte-identical), read
  [section 4 of docs/13](../docs/13-face-byte-by-byte.md#4-roundtrip-what-identical-means-in-each-layer).

> **Texture:** the `.mtl` points to `face.png`, which is **not** included. The
> texture lives inside the `post_parts` of the `.bin`, and this tool does not
> extract it. The `.obj` opens fine in Blender without the `.png` — it just
> has no image.
