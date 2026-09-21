# Passages Level Editor — User's Guide

> Tool located at `_local/tools/passages_tool/` (GitHub: `arctree_tools/passages_tool`).
> File format **version 2**. Vertical FOV + render size are authored; horizontal FOV is derived.

---

## Table of Contents

1. [Overview](#1-overview)
2. [Installation & Launch](#2-installation--launch)
3. [From empty window to baked frames](#3-from-empty-window-to-baked-frames)
4. [Interface Layout](#4-interface-layout)
5. [Viewport Navigation](#5-viewport-navigation)
6. [Tool Modes](#6-tool-modes)
7. [Working with Geometry](#7-working-with-geometry)
8. [Texture Palette](#8-texture-palette) (style packs)
9. [Properties Panel](#9-properties-panel)
10. [Validate](#10-validate)
11. [File Operations](#11-file-operations)
12. [Keyboard & Mouse Reference](#12-keyboard--mouse-reference)
13. [Level File Format](#13-level-file-format)
14. [Convert, bake, and ship](#14-convert-bake-and-ship)
15. [Troubleshooting](#15-troubleshooting)

---

## 1. Overview

The **Passages Level Editor** is a standalone 2D editor for level geometry used by the *Passages* minigame. It lets you:

- Draw **Walls**, **Arches**, **EyePaths**, and **Anchors**
- Assign textures from a browsable palette (including per-wall intervals)
- Pan and zoom a grid-backed orthographic viewport
- Preview a 3D viewpoint from a selected EyePath edge
- Save and load levels as `.passages.json` (version 2)
- Undo and redo edits

The tool is a desktop Panda3D application with a Dear ImGui overlay. Baking still frames for the game is a separate CLI (`bake.bat` / `python -m passages_tool.renderer`); there is no File → Bake command in the editor yet.

---

## 2. Installation & Launch

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10 or higher |
| Panda3D | 1.10.16 (installed automatically) |
| panda3d-imgui | 1.2.0 (installed automatically) |

### First run

Double-click `run.bat` in the `passages_tool/` folder (or run it from any working directory — it `cd`s to its own folder). `run.bat` and `bake.bat` share `_ensure_venv.bat`, which keeps a **local** `.venv` next to the tool. That isolation is intended: do not reuse Miniconda or the ArcTree repo-root env. On first run, or if that venv is broken (typical after uninstalling Miniconda), it will:

1. Remove the broken `.venv` if present
2. Create a new `.venv/` with a standalone Python 3.10+ (`python3.12`, then `py -3`, then `python`; skips interpreters that already live inside another venv)
3. Install dependencies from PyPI
4. Launch the editor (or continue the bake)

Image assets are not in git. Before the palette or baker can find sample textures:

```bat
cd _local\tools\passages_tool
tar -xf sample_assets.tar
```

On first launch the editor auto-scans `assets/sample_textures/` if that folder exists. After you **Browse folder…**, the last path is remembered in `editor_state.json` (gitignored). **View → UI Scale** (100/125/150/200%) is stored there too; with no saved value the first launch snaps to Windows DPI.

### Running from a terminal

```bat
cd _local\tools\passages_tool
run.bat
```

or, with the venv already created:

```bat
.venv\Scripts\python.exe -m passages_tool.main
```

### Running from VS Code

Open `passages_tool/` as the workspace root. Select interpreter `.venv\Scripts\python.exe` (`Ctrl+Shift+P` → **Python: Select Interpreter**).

---

## 3. From empty window to baked frames

1. Launch with `run.bat`. Confirm the Textures panel lists sample PNGs (extract `sample_assets.tar` if it is empty).
2. **File → Open…** a sample such as `json/verify.passages.json`, or draw your own (Wall `W`, EyePath `E`, Arch `A`, Anchor `R`).
3. Toggle **Snap** (`G`) if you want vertices on the visible grid. Grid spacing is `snap_grid` in Level Properties (default 0.25 m).
4. Press **Validate** (`V`). Fix untextured walls (skipped if `meta.style` is set), missing floor/ceiling, edge-on arches, and style/preset errors. Use **Select** on a warning to frame that polyline.
5. Select an EyePath, pick a directed edge, click **Render Preview** in Properties to confirm the 3D view.
6. **File → Save** (`.passages.json`).
7. From the tool folder:

```bat
bake.bat verify
```

That writes `scene_out/` (component `.egg` files), `renders_out/` (PNG viewpoints, midpoints, `manifest.json`), and `shipping_out/` (JPEG/KTX2). Drop `basisu.exe` in `bin/` for KTX2; otherwise JPEG/PNG fallbacks are written.

---

## 4. Interface Layout

```
┌──────────────────────────────────────────────────────────────────────────────┐
│ File  Edit  View │ Select  Draw Wall  Place Arch  Draw EyePath  Place Anchor │ Snap │ Validate │ fps │
├────────────┬─────────────────────────────────────────────────┬───────────────┤
│ Textures   │                                                 │ Properties    │
│ [Browse…]  │              Viewport                           │ type-specific │
│ [thumbs]   │         (pan, zoom, draw, select)               │ vertices      │
│  detail    │                                                 │ level meta    │
└────────────┴─────────────────────────────────────────────────┴───────────────┘
```

| Region | Description |
|---|---|
| **Menu bar** | File / Edit / View (UI Scale), tool modes (colour-coded), snap toggle, Validate, FPS |
| **Textures** (left) | Recursive thumbnail browser |
| **Viewport** (centre) | XZ plan of the level |
| **Properties** (right) | Selected polyline, plus level-wide meta when nothing (or anything) is selected |

Window title: `Passages Level Editor — <filename> *` (`*` = unsaved).

---

## 5. Viewport Navigation

Orthographic camera looking along +Y. Editing is in the **XZ plane**.

| Action | Input |
|---|---|
| **Pan** | Hold **middle mouse** and drag |
| **Zoom in / out** | **Scroll wheel** |
| **Fit on open** | File → Open zooms to the level bounds |

The background grid matches **snap spacing** (`meta.snap_grid`). Minor lines = snap; major lines every 8 minors. If snap is tiny, the drawer thins the lines so the view does not fill with ink.

Letter shortcuts (`S` `W` `A` `E` `R` `G` `V`) and Delete are ignored while a text field in ImGui has focus. Ctrl+S still saves.

**View → UI Scale** enlarges the menu bar, side panels, and vertex fields (100/125/150/200%). The grid and geometry stay in world metres — zoom the viewport separately. The choice is remembered in `editor_state.json`.

---

## 6. Tool Modes

| Mode | Shortcut | Description |
|---|---|---|
| **Select** | `S` | Click a vertex handle to select and drag; click a wall/eyepath segment to select; click empty space to deselect |
| **Draw Wall** | `W` | Left-click adds vertices; Enter or right-click finishes and auto-selects |
| **Place Arch** | `A` | One left-click places an arch and selects it |
| **Draw EyePath** | `E` | Left-click adds viewpoint vertices (consecutive edges are added as you draw); Enter or right-click finishes |
| **Place Anchor** | `R` | One left-click places an interaction slot and selects it |

The active tool is tinted in its type colour (wall yellow, arch cyan, eyepath green, anchor blue-violet).

---

## 7. Working with Geometry

Colours: **Wall** yellow (hatch ticks on the **exterior / left** side; interior is the **right-hand** side when walking vertices in creation order). **Arch** cyan. **EyePath** spring green with arrowheads. **Anchor** blue-violet (not red — red is the Validate highlight).

### Walls

1. `W`, left-click vertices, Enter/RMB to finish.
2. Closed walls: tick **Closed** in Properties (closing edge is textured by an interval that reaches the last vertex).
3. Texture with **intervals** (from-vertex → to-vertex, texture, x-offset). Overlapping intervals are rejected.
4. **Ins** on a vertex row inserts a midpoint after that vertex.

### Arches

One click. If you place near a wall, the tool offers a perpendicular snap: **Enter** accepts, **Esc** or another click / tool switch keeps **billboard**.

### EyePaths

Vertices are standing points. Directed **edges** are the baked views (`v_from` looking at `v_to`). Drawing consecutive vertices adds those edges automatically. Insert-vertex **splits** the spanned edge (and the reverse if present).

Bake and preview use the **first** EyePath only. Validate warns if there is more than one.

### Anchors

Sprite slots for the runtime. They are not meshed into `.egg`. Visibility occlusion is baked per eyepoint; FOV culling is done in the game.

### Select, move, delete

- **Select:** click a handle (~12 px) or a segment.
- **Move vertex:** left-drag the handle (snap applies if Snap is on). You can also type X/Z in Properties.
- **Delete vertex:** **X** on that row in Properties.
- **Delete polyline:** `Delete` key or **Delete polyline** (ignored while typing in a field).
- **Change type:** the type combo asks for confirmation and drops fields the new type does not use.

Undo coalesces a slider/drag into one step. The first click of a new wall is one undo step, not two.

---

## 8. Texture Palette

1. First launch scans `assets/sample_textures/` (including subfolders). **Browse folder…** to pick another; the path is remembered.
2. Click a thumbnail to select it.
3. Assign from Properties: wall **interval** Assign, arch texture Assign, or Level **Floor / Ceiling** Assign.

Names are paths relative to the folder (`base/brick.png` if nested). Folders named `presets/`, `_style_cache/`, and `_meta_cache/` are hidden from the palette.

### Style packs (optional)

A style is `styles/<id>.json` plus `presets/<name>/diffuse.png` in **this same texture folder**. Set `"style": "<id>"` on the level `meta` (no picker yet). Untextured wall edges then get **band-composed** unique maps in **meters** (rooms need not match PNG size). An interval **with** a PNG is an override (old UV path). Floor/ceiling assignment is unchanged.

Authoring the pack: `writer_docs/passages_style_preparation_20SEP26.md`. Engineering plan: `design_docs/passages_style_dressing_20SEP26.md`. Overlay densities > 0 stamp wetness/moss/graffiti (seeded; 0 = unchanged bands).

---

## 9. Properties Panel

### Level (always available)

Name, author, wall height, eye height, **FOV vertical** (horizontal is shown read-only: derived from VFOV × `render_width`/`render_height`), fog, snap grid, bake resolution, floor/ceiling textures. Optional dressing: `meta.style` / `overlay_seed` / `pom_enabled` in the JSON (style picker not in the panel yet).

Default bake size is **1024×576** (16:9). At 60° VFOV that yields about **91.5°** HFOV. Changing resolution or VFOV rewrites `fov_h` on save so the game client stays aligned with the baker.

### Wall

Closed flag; texture intervals (assign, x-offset, split, remove, add); vertex list.

### Arch

Position; billboard vs angle; auto-snap to walls; width / height override; texture; transparency (`none` / `alpha_test` / `alpha_blend`); z-offset; v-at-floor; optional point light. Optional JSON: `kind` (`opening`), `profile` (`rect`/`round`/`gothic`), `depth_m`, `side_texture` — 3D slab that punches the wall (billboard stays a card).

### EyePath

Directed edge list (add/remove by vertex index); **Render Preview** for an edge; vertex list.

### Anchor

Position, radius, height, z-offset, tags.

---

## 10. Validate

**Validate** on the menu bar or `V`. Checks:

- Untextured wall edges (including the closing edge of a closed wall), missing floor/ceiling. Skipped for walls when `meta.style` is set (bands cover those edges)
- Overlapping texture intervals
- Fixed arches that are edge-on from an EyePath view (within fog)
- Style pack: missing `styles/<id>.json`, invalid JSON, missing `presets/<id>/diffuse.png`, unknown opening profile

Flagged polylines turn red. Click **Select** on a warning to frame that object. Floor/ceiling warnings have no polyline to jump to.

---

## 11. File Operations

| Action | Menu | Keyboard |
|---|---|---|
| New | File → New | `Ctrl+N` |
| Open | File → Open… | `Ctrl+O` |
| Save | File → Save | `Ctrl+S` |
| Save As | File → Save As… | `Ctrl+Shift+S` |
| Exit | File → Exit | window close / Alt+F4 |
| Undo | Edit → Undo | `Ctrl+Z` |
| Redo | Edit → Redo | `Ctrl+Y` |
| UI Scale | View → UI Scale | 100 / 125 / 150 / 200% |

New, Open, Exit, and the window **X** prompt if the document is dirty. Files use the `.passages.json` extension (added if omitted). v1 files migrate in memory on load; save to write v2. A `version` newer than 2 is refused.

---

## 12. Keyboard & Mouse Reference

### Keyboard

| Key | Action |
|---|---|
| `S` | Select |
| `W` | Draw Wall |
| `A` | Place Arch |
| `E` | Draw EyePath |
| `R` | Place Anchor |
| `G` | Toggle snap |
| `V` | Validate |
| `Enter` | Finish wall/eyepath, or accept arch snap |
| `Esc` | Keep billboard on arch snap |
| `Delete` | Delete selected polyline |
| `Ctrl+Z` / `Ctrl+Y` | Undo / Redo |
| `Ctrl+S` / `Ctrl+Shift+S` | Save / Save As |
| `Ctrl+O` / `Ctrl+N` | Open / New |

### Mouse

| Input | Action |
|---|---|
| Left click (draw) | Place vertex or arch/anchor |
| Left click (select) | Select handle or segment |
| Left drag (select) | Move vertex |
| Middle drag | Pan |
| Scroll | Zoom (not over ImGui panels) |
| Right click | Finish wall/eyepath |

---

## 13. Level File Format

UTF-8 JSON, `"version": 2`. See the README for a full sample. Summary:

| Field | Notes |
|---|---|
| `meta.fov_v`, `render_width`, `render_height` | Authored. `fov_h` is derived and rewritten on load/save |
| `meta.pixels_per_meter` | Texture scale (legacy `texture_pixel_size` migrates). With a style, this is unique-map resolution (default 256 px/m), not room size |
| `meta.style` | Optional style id → `styles/<id>.json` under the texture folder |
| `meta.overlay_seed` | Optional; overrides style `overlays.seed` for stamps |
| `meta.pom_enabled` | Optional; stored, POM not in stills yet |
| `meta.snap_grid` | Editor snap and visual grid |
| `grid.cell_size` | Serialized leftover; the viewport does not use it |
| `tiles` | Legacy; ignored on load, not written |
| `polylines[].type` | `wall` \| `arch` \| `eyepath` \| `anchor` |
| Wall `texture_intervals` | `from_vertex`, `to_vertex`, `texture`, `x_offset` |
| EyePath `edges` | Directed `[from, to]` pairs |
| Arch `kind`, `profile`, `depth_m`, `side_texture` | Optional. `opening` or `depth_m`>0 → 3D slab + wall punch |

---

## 14. Convert, bake, and ship

From the tool directory (venv created by `run.bat`):

```bat
REM Geometry only (component eggs + scene.egg File-includes for pview)
.venv\Scripts\python.exe -m passages_tool.converter json\verify.passages.json scene_out --textures assets\sample_textures

REM Viewpoints + midpoints + manifest (no combined scene.egg)
bake.bat verify

REM pview the combined file from scene_out so the <File> includes resolve
REM pview scene_out\scene.egg

REM Optional KTX2 / JPEG
.venv\Scripts\python.exe -m passages_tool.renderer.convert_to_jpeg renders_out shipping_out
```

Bake uses **every** EyePath. Vertex indices in `render_vXXXX_to_vYYYY` are global (first path starts at 0; later paths continue). Midpoint frames are the geometric 50% of each undirected edge. The baker also writes optional `yaw_vXXXX.png` strips (360° unwrap) and records them on `eyepoints.*.yaw_strip` when present. `bake.bat` still produces the same stills; `--no-yaw-strip` skips the extras. Clients without strips keep the old turn crossfade. Each **closed** wall gets its own floor and ceiling (a room). Open walls get none. Nested or overlapping closed walls both fill — that is an authoring error, not a courtyard hole.

---

## 15. Troubleshooting

### Window opens but no ImGui panels

```bat
.venv\Scripts\python.exe -c "import p3dimgui; print('OK')"
```

If that fails: `.venv\Scripts\python.exe -m pip install panda3d-imgui`

### `ModuleNotFoundError: No module named 'p3dimgui'` / `No Python at '...miniconda3...'`

The local `.venv` was built against an interpreter that is gone (often leftover Miniconda). Delete it and let the launcher recreate it; do not point `python` at some other project's venv:

```bat
rmdir /s /q .venv
run.bat
```

### `Read timed out` during pip install

```bat
.venv\Scripts\python.exe -m pip install panda3d-imgui --timeout 120 --retries 5
```

### Scrolling does not zoom

Mouse is over a panel. Move it over the viewport.

### Letter keys change tools while typing

They should not. If a field is focused, `S`/`W`/… are ignored. Click the viewport if a shortcut seems dead.

### Validate flags every closed wall as untextured

You are on a build older than the shared closing-edge helper. Update the tool.

### Level version newer than this tool

The file’s `"version"` is greater than 2. Update the tool, or only downgrade the field if you know the JSON is compatible.

### Sprites do not line up with baked backgrounds

`fov_h` in an old JSON may not match the baker (which always uses VFOV × aspect). Re-save the level in this editor so `fov_h` is rewritten, then re-bake if you also changed resolution or VFOV.
