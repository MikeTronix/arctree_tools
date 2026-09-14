# Passages Tool — Proposed Improvements

Assessment of `_local/tools/passages_tool` (the directory is `passages_tool`, not `passages-tool`). **No code was changed.** This is a review of the current editor, converter, baker, and shipping pipeline as they stand.

The tool is a working authoring stack: a Panda3D + ImGui 2D editor, JSON v1→v2 load, `.egg` conversion, viewpoint/midpoint baking, CPU occlusion for anchors, and a KTX2/JPEG ship step. The data model, interval editor, and occluder math are the strongest parts. The biggest gaps are **correctness bugs that tests do not catch**, **editor interaction that the README claims but does not implement**, and **docs that still describe an earlier prototype**.

Priority:

| Tag | Meaning |
|---|---|
| **P0** | Wrong output, data loss, or tests that green-light a broken contract |
| **P1** | Daily authoring friction or silent no-ops |
| **P2** | Architecture, DX, and coverage that will slow the next features |

Effort is a rough size, not a schedule.

---

## 1. What is already in good shape

Keep these; most of the list below is about making them trustworthy.

- Clear package layout (`editor` / `converter` / `renderer` / `ui` / `io`) and a pure-Python `Level` model with no Panda3D dependency.
- Texture intervals, closed-wall winding, N-slice arch configs, and auto-snap raycasts are real features, not stubs.
- Anchor occlusion is GPU-free, unit-tested, and matches `design_docs/passages_anchor_visibility_bake_06JUL26.md` (bake occlusion, runtime FOV).
- Converter and baker CLIs, plus `run.bat` / `bake.bat`, are enough to ship a level without the GUI.
- Pytest coverage of the data model, wall/arch builders, occluders, and (legacy) history API is better than typical prototype tools.

---

## 2. P0 — correctness and data-loss

### 2.1 Undo after redo skips states

`History.redo()` pops the redo stack and **never pushes the current state back onto `_undos`**. After undo then redo, the intermediate snapshot is gone; the next undo jumps over it.

```
S0 --A--> S1 --B--> S2
undo → S1, redo → S2, undo → S0   # S1 lost
```

`tests/test_history.py` only asserts `redo()` is not `None`. It never checks a three-step undo/redo/undo round-trip.

**Fix:** `redo(current_snapshot)` should append current onto `_undos` (mirror of `undo`). Add a test that undo→redo→undo restores the intermediate state.

- File: `src/passages_tool/editor/history.py` (`redo`)
- File: `src/passages_tool/main.py` (`cmd_redo`)

### 2.2 File → Exit discards unsaved work

`"exit": sys.exit` is wired straight to the menu. New / Open go through `_confirm_discard()`; Exit does not. The window close button has no handler either.

**Fix:** one `cmd_exit` that prompts if `level.dirty`, then `self.userExit()` / `self.finalizeExit()`. Bind `window-event` / `Panda3D` close the same way.

- File: `src/passages_tool/main.py` (toolbar callbacks, ~line 121)

### 2.3 Dirty flag is cleared by undo/redo

`Level.from_dict()` always sets `dirty = False`. `_apply_snapshot` rebuilds from a snapshot, so **any undo/redo turns off the “Save *” marker**, even when the restored document is not the last-saved file.

**Fix:** keep a hash or serialized copy of the last-saved dict; set `dirty` from `to_dict() != last_saved`. Do not trust `from_dict`’s dirty bit after history apply.

### 2.4 Shipping manifest rewrite does not understand v2

`build_manifest()` writes:

```json
{ "version": 2, "edges": { "v0000_to_v0001": { "image_path": "..." } }, "eyepoints": {} }
```

`convert_renders()` walks **top-level** `manifest_data.items()` and looks for `image_path` on those values. `version` and `eyepoints` have none; edge entries are nested and never rewritten. Shipped `manifest.json` still points at `.png` after a successful KTX2/JPEG convert.

The tests pass because they use the **old flat** shape (`{ "v0000_to_v0001": { ... } }`), not the production v2 document.

**Fix:** rewrite `manifest["edges"][key]` (and leave `eyepoints` alone). Change `tests/test_convert_to_jpeg.py` to use a v2 fixture. Optionally fail the test if a v2 manifest is rewritten with unchanged `.png` paths.

- File: `src/passages_tool/renderer/convert_to_jpeg.py` (~lines 149–166)
- File: `tests/test_convert_to_jpeg.py` (`test_manifest_rewriting_fallback`)

### 2.5 Closed-wall texture validator is wrong

`validate_textures` treats a closed wall as having `n` edges (last is `n-1 → 0`). Coverage is `range(iv.from_vertex, iv.to_vertex)`, so an interval `0 … n-1` covers edges `0 … n-2` only. The closing edge is **always** reported untextured.

`build_wall_strips` special-cases that closing edge onto the last interval with `to_vertex == n-1`. Validator and baker disagree; Validate will light up every closed corridor.

**Fix:** share one `iter_wall_edges(pl)` helper used by validator, wall builder, and occluder. For a closed interval that reaches vertex `n-1`, include edge `n-1`. Add a test with a 4-vertex closed wall and one full-span interval — expect zero texture warnings.

- File: `src/passages_tool/editor/validator.py` (`validate_textures`)
- File: `src/passages_tool/converter/wall_builder.py`

### 2.6 `fov_h` is authored and then ignored

Level Properties expose horizontal FOV. `ViewpointRenderer` loads `fov_h` and never uses it; HFOV is always derived from `fov_v` and the buffer aspect.

```
fov_h_calc = 2 * atan(aspect * tan(fov_v/2))
lens.set_fov(fov_h_calc, fov_v)
```

On 1024×768 that is ~75°, not the 90° stored in sample levels. On 1024×576 it happens to be ~91.5° (`config.DEFAULT_FOV_H`). Changing FOV Horiz in the panel is a no-op.

**Fix:** either drive the lens from `fov_h` (and derive V), or hide `fov_h` and document that VFOV + resolution define the frustum. Do not leave a live control that does nothing.

- File: `src/passages_tool/renderer/viewpoint_renderer.py` (`render_edge`, `render_midpoint`)
- File: `src/passages_tool/ui/properties.py` (`_draw_level_meta`)

### 2.7 In-editor preview path and scene graph

`_cb_render_preview` writes to `Path("_local/tools/passages_tool/temp_preview")` (CWD-relative). Double-clicking `run.bat` uses the tool directory as CWD, so the preview lands in a nested `_local/tools/...` folder inside the tool, not the repo path.

`ViewpointRenderer` reuses the editor `ShowBase` and `reparent_to(self.base.render)`. For the duration of the bake, 3D walls are parented onto the 2D orthographic viewport. `close()` removes the root but does not isolate a hidden scene.

**Fix:** preview dir = `Path(__file__).resolve().parents[N] / "temp_preview"` (or `tempfile.mkdtemp`). Render into an offscreen buffer with a dedicated scene root, never the editor `render`.

- File: `src/passages_tool/main.py` (`_cb_render_preview`)
- File: `src/passages_tool/renderer/viewpoint_renderer.py`

### 2.8 Auto-snap width update is a silent no-op

When “Auto-snap to walls” is checked, properties calls `find_snap_points(self.level, ...)`. `PropertiesPanel` has **no** `self.level` (the live `Level` is only an argument to `draw()`). The `except Exception: pass` swallows `AttributeError`, so snapped width never updates in the inspector.

**Fix:** store `self._level` from `draw()`, or pass `level` into `_draw_arch_props`. Do not bare-`except` around this.

- File: `src/passages_tool/ui/properties.py` (~line 407)

---

## 3. P1 — editor interaction

### 3.1 Vertex drag is advertised and not implemented

README / user guide: “Move vertex: left-drag handle.” `main.py` has `_drag_pid` / `_drag_idx` / `_drag_last` and handle PythonTags (`polyline_id`, `vertex_idx`), but:

- `_select_at` only does a world-space nearest-vertex search
- `_update` never moves a dragged vertex
- `_on_lclick_up` only clears the unused drag fields

The only way to move a vertex is typing coordinates in Properties.

**Fix:** on select-mode mouse-down, pick the nearest handle in **screen space** (constant pixel radius). While LMB is down and not over ImGui, write `move_vertex` (one history push on mouse-down, not per frame). Mouse-up commits.

### 3.2 Pick radius is world-space and edges are unselectable

`CLICK_RADIUS_WORLD = 0.4`. At default zoom that is ~19 px; at `ZOOM_MAX` (film width 200) it is ~3 px. Long walls with distant vertices are hard to select; you cannot click the segment.

**Fix:** screen-space radius (~8–12 px) and a point-to-segment test so clicking a wall/eyepath edge selects it.

### 3.3 Drawn grid does not match snap grid

Three independent grids:

| Source | Used for |
|---|---|
| `config.GRID_CELL` (1.0) | `BackgroundGrid` lines |
| `Level.grid.cell_size` | serialized, unused by the viewport |
| `Level.meta.snap_grid` | snap when G is on |

Default snap is 0.25 (or 0.5 in sample JSON) while the visual grid is always 1.0. Authors think they are snapping to the lines they see.

**Fix:** draw the grid from `meta.snap_grid` (minor = snap, major = 8×). Drop or wire `grid.cell_size`. Rebuild the grid when snap size changes (already attempted via `_cb_set_meta_field`).

### 3.4 Keyboard shortcuts fire while typing in ImGui

`s/w/a/e/r/g/v` and Delete are bound globally with no `io.want_capture_keyboard` check. Typing a level name that contains those letters, or pressing Delete in a text field, changes tool mode or deletes the polyline.

**Fix:** in every key handler, return early if ImGui wants the keyboard (same pattern as mouse capture).

### 3.5 Window resize is ignored

`ViewportCamera.on_resize` exists; nothing calls it. `_rebuild_grid` uses the compile-time `WINDOW_W` / `WINDOW_H`. A resized window shears the ortho projection and the grid.

**Fix:** accept `"window-event"` and pass the new size into the camera + grid.

### 3.6 History is too coarse for sliders

Every Properties mutation does `history.push(level.to_dict())`. `slider_float` (arch angle, light intensity) and `input_float` fire continuously, so one drag fills the 100-deep stack with near-duplicate snapshots and makes undo unusable.

**Fix:** begin/end a history group on ImGui activate/deactivate (`is_item_activated` / `is_item_deactivated_after_edit`). Alternatively debounce: push only when the value is committed.

### 3.7 Drawing a wall records two undo steps for the first click

Creating the polyline and adding the first vertex are separate `push()` calls. First undo leaves a 0-vertex polyline in the document.

**Fix:** one command for “start polyline + first vertex”.

### 3.8 EyePath insert-vertex drops connectivity

`insert_vertex` shifts edge indices but does not split the edge that was broken. Inserting on `0 → 1` turns it into `0 → 2`; the new vertex is isolated. Walls extend texture intervals across the split; eyepaths should analogously become `0 → new` and `new → old_to`.

**Fix:** if an edge `(a, b)` spanned the insertion, replace it with `(a, new)` and `(new, b)` (and the reverse edge if present). Add a test; `test_level_operations_v2.py` only covers `delete_vertex` on eyepaths.

### 3.9 Type combo is a footgun

The Properties type dropdown can turn a wall into an arch (or anything else) in place. Extra vertices, intervals, and edges stay in memory until the next save/load, which drops them via `to_dict()`. No confirmation, no field conversion.

**Fix:** hide the combo, or convert explicitly (wall → arch uses centroid; warn that intervals will be dropped).

### 3.10 Missing Save As; title bar is static

There is `_cmd_save_as` but no menu item and no `Ctrl+Shift+S`. The window title is always `Passages Level Editor` — no filename, no dirty marker (only the menu “Save *”).

**Fix:** File → Save As, update `window-title` / a status line with `path + (" *" if dirty)`.

### 3.11 Arch snap confirm is easy to misfire

The overlay says Enter = snap, Esc = billboard. Left-click **also** accepts, so the next click in the viewport (intending to place the next arch) confirms the previous one. `set_tool` auto-accepts as well.

**Fix:** only Enter accepts; click-elsewhere and tool-switch should cancel or require an explicit choice. Bind Esc in `_on_escape` (already does) and make that the documented cancel.

### 3.12 Texture palette is non-recursive and session-only

`scan_directory` lists only the top of the folder. `assets/sample_textures/base/` is invisible. The last-used folder is not remembered, so every launch starts empty even though sample textures sit next to the tool.

**Fix:** recurse (or follow one `textures/` convention), persist `base_dir` in a small config JSON, and auto-scan `assets/sample_textures` on first run.

### 3.13 Validate is a modal dump

Warnings are a floating list of strings; highlight is “all flagged ids red.” Clicking a warning does not frame the arch/wall. Floor/ceiling warnings reuse `ValidationWarning.arch_id=""` because the type is arch-centric.

**Fix:** a typed issue list (`kind`, `target_id`, `edge`) and click-to-frame. Split texture vs visibility vs geometry.

---

## 4. P1 — bake and converter pipeline

### 4.1 Only the first EyePath exists

`build_manifest`, `ViewpointRenderer`, `validate_arch_visibility`, `compute_transition_path`, and the baker CLI all `break` on the first `type == EYEPATH`. A second path is silently ignored. Either enforce “exactly one EyePath” in Validate, or iterate all of them with namespaced keys (`pathId/v0000_to_v0001`).

### 4.2 `build_scene` builds every mesh twice

Individual `walls.egg` / `floor.egg` / … and then `scene.egg` each call `build_wall_strips` / `build_floor` / `build_arches` again. Preview from the editor pays this cost on every click.

**Fix:** build groups once, write both the parts and the combined file from the same Egg nodes (or skip `scene.egg` if the loader already composes parts — `load_scene` loads the four parts, not `scene.egg`).

### 4.3 Midpoint bake ignores the “safe travel” path

`compute_transition_path` in `transition_renderer.py` caps travel so fixed arches stay face-on. `render_midpoint` instead places the camera at the **geometric 50%** of the edge. The module even says `TransitionRenderer` is retired. Either delete the dead path math or use it; the design doc’s “don’t expose edge-on arches mid-move” is currently unenforced at bake time.

`edge_on_check` uses `acos(|dot|)` (angle from face-on, default 60°). `validate_arch_visibility` uses `asin(|dot|)` (angle to plane, default 30°). Same geometry, two APIs, easy to desync.

**Fix:** one `arch_view_angle()` used by validator, transition cap, and any future baker.

### 4.4 `find_basisu` looks in the wrong `bin/`

Comment: “local bin subdirectory (`../../bin/basisu`)”. Code: `Path(__file__).parent.parent.parent / "bin"` → `src/bin`, not the project `passages_tool/bin/`. The folder at the tool root is empty. Shipping therefore almost always falls back to JPEG/PNG unless `basisu` is on `PATH`.

**Fix:** resolve `Path(__file__).resolve().parents[3] / "bin"` (tool root) and document dropping `basisu.exe` there. `bake.bat` could chain the transcoder after PNG bake.

### 4.5 Baker does not delete stale images

`find_stale_images` exists and is tested; `__main__.py` never calls it. Renaming/removing an edge leaves orphan `render_*.png` / `mid_*.png` in `renders_out/`.

### 4.6 Near/far and headlight are magic numbers

Lens far plane is 100; fog_end in sample levels is 40. Headlight attenuation `(0, 0, 0.03)` is duplicated in lighting_builder and both render methods. Pull from config / level meta so bake lighting matches the converter lights.

### 4.7 Overlapping texture intervals produce stacked quads

`add_texture_interval` appends and sorts; it does not reject overlap. The wall builder emits a quad per interval edge, so overlaps z-fight. Validate should error on overlapping or inverted intervals (`from >= to` is already a no-op on add, but load can still contain them).

### 4.8 Floor triangulation is “largest closed loop + other loops as holes”

That is wrong for multi-room maps that are separate closed walls (two rooms become one outer + one hole). Document the limitation, or switch to a union-of-polygons approach (even a per-loop floor with unique materials would be more honest).

### 4.9 CLI help / defaults disagree

| Place | `render_height` | `fov_h` |
|---|---|---|
| `config.py` | 576 | 91.5 |
| sample JSON / design doc | 768 | 90 |
| renderer CLI help | “or 768” | — |

Pick one set of defaults and make config, CLI help, README sample, and `docs/passages_rendering_design.md` match.

---

## 5. P2 — architecture

### 5.1 `main.py` is the application

~750 lines: input, tools, file I/O, history, validation, preview, tk dialogs. Split along the seams that already exist in comments:

- `app/input.py` — mouse/keys, ImGui capture
- `app/commands.py` — new/open/save/undo and property callbacks
- `app/preview.py` — isolated bake-to-ImGui

Keep `PassagesApp` as the ShowBase shell.

### 5.2 One `Polyline` dataclass for four types

Wall intervals, arch lights, eyepath edges, and anchor tags share one type with a dozen unused fields. `to_dict` / `from_dict` already branch. A small union (`Wall | Arch | EyePath | Anchor`) would make illegal states unrepresentable and simplify the type combo problem (3.9).

Not urgent if tagged methods stay behind `pl.type` guards — but every new field currently lands on the god object.

### 5.3 Repeated “find the EyePath” loops

At least six call sites copy the same scan. Add `Level.eyepaths()` / `Level.anchors()` / `Level.walls()`.

### 5.4 `ViewpointRenderer.render_edge` and `render_midpoint` are copies

Camera, lens, headlight, double `render_frame`, screenshot, teardown — duplicated. One `_render_camera(pos, look_at, path)` is enough.

### 5.5 Converter `EggContext` vs raw `EggData`

`scene_builder` constructs `EggData` by hand; `wall_builder` uses `EggContext` per polyline (so many vertex pools). `egg_writer.get_or_create_texture` never `add_child`s the `EggTexture` onto the egg (Panda often still serializes via polygon references — worth confirming with a textured pview, not just polygon counts).

### 5.6 Tiles are dead

`Level.tiles`, `set_tile`, and JSON `tiles: []` have no editor, no converter, no baker. Either remove from v2 (keep a migrator) or actually paint tiles. As-is they are a lie in the file format docs.

### 5.7 Logging is `print` + `traceback.print_exc`

UI errors vanish into the console; bake errors are unstructured. A `logging` logger with a small ImGui “log” window would help when p3dimgui or a texture fails.

### 5.8 Generated / local junk in the tree

Present next to source: `imgui.ini`, `src/passages_tool.egg-info/` (SOURCES.txt is stale — no converter/renderer), `__pycache__`, `renders_out/`, `scene_out/`, `shipping_out/`. The tool has its own nested `.git`. Decide whether this stays a nested repo or is just a folder in `browser_vn`, and gitignore the rest.

`pyproject.toml` package-data lists `assets/**/*` and `icons/**/*` inside the package; assets actually live at the **project** `assets/` root. The extra glob does nothing.

---

## 6. Docs and onboarding

The user guide is the highest-cost mismatch: it teaches a tool that no longer exists.

| User guide / README | Code |
|---|---|
| Draw Polyline, shortcut `P` | Wall `W`, Arch `A`, EyePath `E`, Anchor `R` |
| Format version 1, single `texture` | Version 2, intervals, arches, eyepaths, anchors |
| “Newer than version 1 will refuse” | `LEVEL_FILE_VERSION = 2` |
| Vertex drag in the viewport | Not implemented (3.1) |
| Properties: closed + texture + vertex list | Intervals, lights, edges, preview, level meta |
| README sample `render_height` 768 | Config default 576 |

`docs/passages_rendering_design.md` still lists three polyline types, `texture_pixel_size`, and FOV 90/768. Anchors, N-slice arches, and the v2 manifest (`edges` + `eyepoints.visible_anchors`) are missing.

**Fix (one sitting):** rewrite `docs/user_guide.md` from the toolbar + properties panel. Point README controls at W/A/E/R/G/V. Mark the rendering design “partially superseded” or patch the tables.

Also worth adding:

- File → Bake Level… (wraps the renderer CLI so authors do not need `bake.bat`).
- A one-page “from empty window to `renders_out/`” in the README (extract `sample_assets.tar` is already there; the missing piece is “open `json/onion.passages.json`, browse textures, Validate, bake”).

`run.bat` does not `cd /d %~dp0`. `bake.bat` does. First-run from a random CWD can install the venv in the right place (it uses `%~dp0`) but then fail to import if `PYTHONPATH` is odd. Add `cd /d %~dp0` to `run.bat` to match bake.

---

## 7. Tests — gaps that hide the P0s

Existing tests are good at “this function returns a polygon.” They are weak at contracts between stages.

Add at least:

| Test | Why |
|---|---|
| History undo→redo→undo restores S1 | 2.1 |
| `validate_textures` on a closed 4-gon with one full interval | 2.5 |
| `convert_renders` with a **v2** `manifest.json` | 2.4 |
| `insert_vertex` on an eyepath splits edges | 3.8 |
| `Level.from_dict` dirty vs “apply snapshot keeps dirty if ≠ last save” | 2.3 |
| Wall builder closing-edge UV when `closed=True` | baker/validator agreement |
| `find_basisu` resolves tool-root `bin/` | 4.4 |
| Overlapping intervals rejected or last-wins, documented | 4.7 |

There is **no** test for `main.py`, camera, palette, or “ImGui capture.” That is fine if interaction is covered by a short manual checklist in the user guide (open onion, snap, validate, preview one edge). A headless smoke that `PassagesApp` constructs is optional and Panda-heavy.

`test_validator.py`’s `test_webp_mislabeled_as_png` does not belong in that file.

---

## 8. Feature opportunities (after the P0/P1 list)

These are worthwhile once the tool stops lying about its own controls.

1. **Bake from the editor** — progress bar, cancel, write next to the `.passages.json` (or a chosen `renders_out`). Today bake is a separate CLI/bat.
2. ** marquee / box select and multi-select** — deleting or moving a cluster of arches is painful one-id at a time.
3. **Copy/paste and duplicate** (`Ctrl+D`) for arches and anchors.
4. **Measure / ruler and north indicator** — world units are meters; nothing in the viewport says so.
5. **EyePath as a graph, not a polyline-plus-edges** — draw a vertex, drag to another to create a directed edge, rather than typing V-from / V-to.
6. **Live 3D peek** — a locked offscreen camera at the selected eyepath vertex, updated on move, instead of a full egg rebuild per “Render Preview.”
7. **Anchor occupancy debug** — overlay baked `occ_coverage` in the 2D view after a bake (read `manifest.json` eyepoints).
8. **Command-pattern history** instead of full-document snapshots, if levels grow past “hundreds of vertices.” Snapshots are fine until sliders are grouped (3.6).
9. **Schema / JSON Schema** for `.passages.json` and `manifest.json` so the client and the tool cannot drift the way convert_to_jpeg already did.
10. **Drop tkinter dialogs** for native-os or ImGui file pickers — mixing Tk and a Panda window on Windows is a known focus-stealing source.

Out of scope for this tool (already assigned elsewhere): bindings (`passages_dm`), combat, runtime FOV. Do not grow tags into a content editor.

---

## 9. Suggested order of work

A sequence that removes landmines before adding surface area:

1. **History redo + dirty-after-undo + Exit prompt** (2.1–2.3) — data integrity.
2. **v2 manifest rewrite + tests** (2.4) — shipping is currently wrong.
3. **Closed-wall texture coverage helper** (2.5) — Validate is misleading today.
4. **Docs pass** (section 6) — stop teaching `P` and v1 JSON.
5. **Vertex drag + screen-space pick + grid = snap** (3.1–3.3) — the editor feels unfinished without these.
6. **ImGui keyboard capture, resize, slider history grouping** (3.4–3.6).
7. **Preview isolation + fov policy + auto-snap `self.level`** (2.6–2.8).
8. **EyePath insert, first-EyePath policy, stale-image cleanup, basisu path** (3.8, 4.1, 4.4–4.5).
9. Split `main.py` and rewrite the user guide’s remaining Phase-1 panels.

---

## 10. File map for the items above

| Area | Paths |
|---|---|
| App shell | `src/passages_tool/main.py` |
| Document | `src/passages_tool/editor/level.py`, `history.py`, `validator.py`, `arch_utils.py` |
| Viewport gfx | `src/passages_tool/editor/polyline.py`, `viewport/camera.py`, `viewport/grid.py` |
| UI | `src/passages_tool/ui/toolbar.py`, `properties.py`, `palette.py` |
| I/O | `src/passages_tool/io/level_format.py` |
| Convert | `src/passages_tool/converter/*.py` |
| Bake | `src/passages_tool/renderer/viewpoint_renderer.py`, `manifest.py`, `occluder.py`, `convert_to_jpeg.py`, `__main__.py` |
| Docs | `README.md`, `docs/user_guide.md`, `docs/passages_rendering_design.md` |
| Launch | `run.bat`, `bake.bat`, `pyproject.toml` |
