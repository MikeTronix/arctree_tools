# Passages Tool — Proposed Improvements

Assessment of `_local/tools/passages_tool` (the directory is `passages_tool`, not `passages-tool`). Canonical GitHub copy is the `passages_tool/` folder of [MikeTronix/arctree_tools](https://github.com/MikeTronix/arctree_tools). The nested local git repo cannot `git push` that folder directly; overlay the tracked tree into the monorepo.

**Policy so far:** ship core-function P0/P1 first. Leave content-visible design forks (midpoint camera path, multi-room floors) until they are explicitly chosen.

| Tag | Meaning |
|---|---|
| **P0** | Wrong output, data loss, or tests that green-light a broken contract |
| **P1** | Daily authoring friction or silent no-ops |
| **P2** | Architecture, DX, and coverage that will slow the next features |

Status: **done** · **partial** · **open**

---

## Progress

| Area | Status | Notes |
|---|---|---|
| §2 P0 correctness / data-loss | **done** | Nested `b9011b6`; GitHub `6ed69e8` |
| §3 P1 editor interaction | **done** (3.13 typed issues still **partial**) | Nested `f07a0e3`; GitHub `b9f5b0a` |
| §4 P1 bake / converter | **partial** | Core plumbing done; 4.3 and 4.8 left as forks; 4.2/4.9 docs leftover |
| §5 P2 architecture | **open** | `Level.eyepaths()` landed as a side effect of 4.1 |
| §6 Docs / onboarding | **open** | User guide and README still describe v1 / `P` / no vertex drag |
| §7 Tests | **partial** | P0/P1 contracts covered; `main.py` / ImGui still untested |
| §8 Feature opportunities | **open** | After remaining P1 forks and docs |

Tests at last P1 commit: **167 passed**.

---

## New helpers and call sites (for later work)

Do not re-derive these; extend them.

| Symbol | Where | Role |
|---|---|---|
| `derived_fov_h(fov_v, width, height)` | `config.py` | HFOV from VFOV × render aspect. `Level.sync_derived_fov_h()` / `to_dict` / `from_dict` always write this; the inspector is read-only. Client still reads JSON `fov_h` — re-save levels so 4:3 maps stop shipping `90`. |
| `CAMERA_NEAR`, `CAMERA_FAR`, `HEADLIGHT_ATTENUATION`, `PICK_RADIUS_PX` | `config.py` | Shared bake lens / pick radius. Far plane is still a constant `100`, not `fog_end`. |
| `wall_edge_index_pairs(pl)` | `editor/level.py` | Wall segments including the closing edge (`n ≥ 3`). Used by validator, occluder, and viewport edge-pick. |
| `interval_edge_indices(pl, iv)` | `editor/level.py` | Edges covered by one texture interval, including closing edge when `to_vertex == n-1`. Wall builder and `validate_textures` share this. |
| `_texture_intervals_overlap(a, b)` | `editor/level.py` | Half-open `[from, to)` overlap. `add_texture_interval` no-ops on overlap; `validate_textures` still warns for intervals already on disk. |
| `Level.eyepaths()` | `editor/level.py` | All EyePath polylines. Bake/preview/validator still use **the first**. `validate_structure` warns if `len > 1`. `Level.walls()` / `Level.anchors()` are not added yet. |
| `Level.sync_derived_fov_h()` | `editor/level.py` | Updates `meta.fov_h` without touching `dirty`. |
| `History.redo(current_snapshot)` | `editor/history.py` | Pushes current onto `_undos` before popping redo (undo→redo→undo no longer skips). |
| `validate_structure(level)` | `editor/validator.py` | Extra-EyePath warning. Called from editor Validate together with textures + arch visibility. |
| `build_scene(..., write_combined=True)` | `converter/scene_builder.py` | Writes the four component eggs from one geometry pass. Combined `scene.egg` is a **second** pass (Egg nodes cannot be dual-parented). Preview and baker pass `write_combined=False`; converter CLI still writes combined for pview. |
| `_write_egg(path, groups)` | `converter/scene_builder.py` | One-file EggData writer used by the four parts. |
| `local_basisu_binary()` | `renderer/convert_to_jpeg.py` | `passages_tool/bin/basisu[.exe]` (`Path(__file__).parents[3]`). Drop the encoder there; `bake.bat` still does not chain the transcoder. |
| `_manifest_edge_entries(manifest)` | `renderer/convert_to_jpeg.py` | v2 nested `edges` plus legacy flat manifests. |
| `PassagesApp._hist(key=None)` | `main.py` | Snapshot undo. Repeating `key` coalesces slider/drag/meta edits; `key=None` always pushes. |
| `PassagesApp._imgui_wants_keyboard()` | `main.py` | Gates `s/w/a/e/r/g/v`, Delete, Enter, Esc, snap, Validate. Ctrl+S still saves while typing. |
| `PassagesApp._select_at(wx, wz, mx, my)` | `main.py` | Screen-space vertex pick (`PICK_RADIUS_PX`) starts a drag; edge pick (NDC point-to-segment) selects. |
| `_point_seg_dist2` | `main.py` | NDC distance² from mouse to a segment. |
| `_convert_polyline_type(pl, new_type)` | `main.py` | After a yes/no dialog: arch/anchor keep vertex 0 and drop intervals/edges; wall drops edges; eyepath drops intervals. |
| `ViewportCamera.film_h`, `.win_w`, `.win_h` | `viewport/camera.py` | Resize-aware film and pick math. `_on_window_event` ignores offscreen buffers (`window != self.win`). |
| `BackgroundGrid.rebuild(..., cell=)` | `viewport/grid.py` | Minor spacing from `meta.snap_grid`; doubles `cell` if more than ~240 lines would be drawn. `Level.grid.cell_size` is still serialized and unused. |
| Editor state | `editor_state.json` (gitignored, tool root) | Remembers last texture directory. First launch scans `assets/sample_textures` if present. Texture scan is recursive (`relative/posix` names). |

Dirty tracking: `PassagesApp._saved_snapshot` + `_capture_saved` / `_refresh_dirty`. Do not trust `Level.from_dict().dirty` after undo.

Preview: `TOOL_ROOT / "temp_preview"` (`main.py` `parents[2]`). `ViewpointRenderer` does **not** reparent the 3D scene onto the editor `render`.

---

## 1. What is already in good shape

Keep these; most of the original list was about making them trustworthy. They still hold, plus:

- Screen-space pick/drag, snap-sized grid, Save As, and remembered textures now match how the editor is actually used.
- FOV is one-way: author `fov_v` + resolution; persist derived `fov_h` for the client.
- Closed-wall texture coverage is one helper, not two disagreeing loops.

---

## 2. P0 — correctness and data-loss

All **done**. Original findings kept as context.

### 2.1 Undo after redo skips states — **done**

`History.redo(current_snapshot)` appends current onto `_undos`. Test: `test_undo_redo_undo_restores_intermediate`.

### 2.2 File → Exit discards unsaved work — **done**

`cmd_exit` + `win.setCloseRequestEvent("passages-close")`. Cancel leaves the window open.

### 2.3 Dirty flag is cleared by undo/redo — **done**

Last-saved dict comparison. Title bar also shows ` *`. No unit test of `_refresh_dirty` itself (lives in `main.py`).

### 2.4 Shipping manifest rewrite does not understand v2 — **done**

`_manifest_edge_entries` rewrites nested `edges`. Test: `test_manifest_rewriting_v2_nested_edges`. Legacy flat fixtures still pass.

### 2.5 Closed-wall texture validator is wrong — **done**

Shared `interval_edge_indices` / `wall_edge_index_pairs`. Test: `test_validate_textures_closed_wall_full_interval`.

### 2.6 `fov_h` is authored and then ignored — **done**

Derived; inspector is read-only. Tests: `test_fov_h_is_derived_from_fov_v_and_aspect`. Existing JSON with `fov_h: 90` at 1024×768 becomes ~75.2° on load/save. **Client still trusts the JSON field** until those files are re-saved (or the client also derives).

### 2.7 In-editor preview path and scene graph — **done**

Tool-root `temp_preview/`; bake scene is its own graph.

### 2.8 Auto-snap width update is a silent no-op — **done**

`_draw_arch_props(..., level)` uses the live `Level`. Auto-snap still calls `set_field` from `draw()` when width differs (one history step via coalesce).

---

## 3. P1 — editor interaction

### 3.1 Vertex drag — **done**

Select-mode LMB on a handle (screen-space) drags; history coalesces per `drag:{pid}:{idx}` and only pushes after the vertex actually moves. Snap applies while dragging.

### 3.2 Pick radius / edges unselectable — **done**

`PICK_RADIUS_PX = 12`. Edge hit-test selects walls (including closing edge) and EyePath edges.

### 3.3 Drawn grid vs snap grid — **done** (serialization leftover)

Viewport uses `meta.snap_grid`. `Level.grid.cell_size` is still in JSON and unused — drop or alias in a format bump (P2-adjacent).

### 3.4 Keyboard shortcuts while typing — **done**

`_imgui_wants_keyboard()` on letter tools, Delete, Enter, Esc, G, V.

### 3.5 Window resize — **done**

`window-event` → `ViewportCamera.on_resize` + grid. Offscreen preview windows are ignored.

### 3.6 History too coarse for sliders — **done** (coalesce, not ImGui activate)

`_hist(key)` coalesces by field/drag id. Discrete actions pass `key=None`.

### 3.7 First wall click two undo steps — **done**

Create polyline + first vertex share one `_hist()`.

### 3.8 EyePath insert-vertex drops connectivity — **done**

Spanned directed edge and its reverse split. Test: `TestInsertVertexEyePath`.

### 3.9 Type combo footgun — **done**

Yes/no dialog + `_convert_polyline_type`. Combo remains; conversion is explicit.

### 3.10 Save As / title bar — **done**

File → Save As, `Ctrl+Shift+S`, `WINDOW_TITLE — filename *`.

### 3.11 Arch snap confirm misfire — **done**

Enter accepts; Esc, viewport click, and tool-switch keep billboard.

### 3.12 Texture palette non-recursive / session-only — **done**

Recursive scan; `editor_state.json`; default `assets/sample_textures`.

### 3.13 Validate is a modal dump — **partial**

Each warning with `arch_id` has a Select button that frames the polyline. `ValidationWarning` is still arch-shaped (`arch_id=""`, `v_from`/`v_to` reused). Floor/ceiling issues cannot jump. A typed `{kind, target_id, edge}` list is remaining scope.

---

## 4. P1 — bake and converter pipeline

### 4.1 Only the first EyePath exists — **partial**

`validate_structure` warns. Bake, preview, and `validate_arch_visibility` still use `eyepaths()[0]`. Namespaced multi-path keys (`pathId/v0000_to_v0001`) are remaining scope if more than one path is a real authoring need.

### 4.2 `build_scene` builds every mesh twice — **partial**

Four component eggs share one build. Combined `scene.egg` is still a second build when `write_combined=True` (converter CLI). Preview/baker skip it (`load_scene` never read `scene.egg`). Remaining: a combined file without a second tessellation, or drop `scene.egg`.

### 4.3 Midpoint bake ignores the “safe travel” path — **open** (design fork)

`render_midpoint` stays at geometric 50%. `compute_transition_path` / `edge_on_check` remain unused by the baker (tests still cover them). Validator uses `asin(|dot|)` (angle to plane); `edge_on_check` uses `acos(|dot|)` (angle from face-on). Do **not** switch bake cameras without deciding that existing mid frames may change. If implemented later: one `arch_view_angle()` shared by validator and the cap.

### 4.4 `find_basisu` wrong `bin/` — **done** (transcoder chain leftover)

`local_basisu_binary()` → tool-root `bin/`. `bake.bat` still only runs the PNG baker; JPEG/KTX2 is a separate `python -m passages_tool.renderer.convert_to_jpeg` step.

### 4.5 Baker does not delete stale images — **done**

After the final manifest rewrite, `find_stale_images` unlinks orphans.

### 4.6 Near/far and headlight magic numbers — **done** (fog coupling leftover)

Named constants in `config.py`, used by `ViewpointRenderer` and `setup_lighting`. Far plane is not derived from `fog_end`.

### 4.7 Overlapping texture intervals — **done** (load leftover)

Add is rejected; Validate warns. A v2 file that already contains overlaps still loads; remaining: strip or error in `Level.from_dict`.

### 4.8 Floor = largest loop + holes — **open** (design fork; documented)

`build_triangulated_polygons` docstring states the limitation. Two disjoint closed rooms still punch a hole in the larger one. Remaining: per-loop floors or a union. Do not “fix” silently — it changes every multi-room bake.

### 4.9 CLI help / defaults disagree — **partial**

Baker `--height` help now says typically 576. Config default is still 576 / derived ~91.5 HFOV. README sample JSON and `docs/passages_rendering_design.md` still show 768 / 90. Remaining is a docs pass (§6), not another code default.

---

## 5. P2 — architecture

All **open** except as noted.

### 5.1 `main.py` is the application — **open**

Now larger (~1000 lines) after P0/P1. Split is still valid: input, commands, preview. Do not split as a drive-by; it is a dedicated PR.

### 5.2 One `Polyline` dataclass for four types — **open**

`_convert_polyline_type` papers over illegal in-memory states. A union type is still the long-term fix.

### 5.3 Repeated “find the EyePath” loops — **partial**

`Level.eyepaths()` exists. `walls()` / `anchors()` do not. Manifest / viewpoint renderer still hand-scan for the first path.

### 5.4 `render_edge` / `render_midpoint` copies — **open**

Near/far/headlight now share config, but the two methods are still duplicated. A `_render_camera(pos, look_at, path)` is remaining.

### 5.5 Converter `EggContext` vs raw `EggData` — **open**

`_write_egg` is a small step. Texture nodes still may not be `add_child`’d onto EggData.

### 5.6 Tiles are dead — **open**

### 5.7 Logging is `print` — **open**

### 5.8 Generated / local junk — **partial**

`editor_state.json` and `.venv_uv/` are gitignored. Nested `.git` vs monorepo overlay is the established publish path. `pyproject.toml` package-data `assets/**` / `icons/**` still point at the wrong place.

---

## 6. Docs and onboarding — **open**

Highest remaining mismatch. Vertex drag (3.1) is implemented; the table below is still what the docs say.

| User guide / README | Code now |
|---|---|
| Draw Polyline, shortcut `P` | Wall `W`, Arch `A`, EyePath `E`, Anchor `R` |
| Format version 1, single `texture` | Version 2, intervals, arches, eyepaths, anchors |
| “Newer than version 1 will refuse” | `LEVEL_FILE_VERSION = 2` |
| Vertex drag in the viewport | **Implemented** (3.1) — docs still useful if updated |
| Properties: closed + texture + vertex list | Intervals, lights, edges, preview, derived FOV Horiz |
| README sample `render_height` 768 / `fov_h` 90 | Config 576; `fov_h` derived |

Also still missing: File → Bake Level…; `run.bat` `cd /d %~dp0`; a one-page empty-window-to-`renders_out/` README; rendering-design tables (anchors, N-slice, v2 manifest).

---

## 7. Tests

**Added with P0/P1**

| Test | Covers |
|---|---|
| `test_undo_redo_undo_restores_intermediate` | 2.1 |
| `test_validate_textures_closed_wall_full_interval` | 2.5 |
| `test_manifest_rewriting_v2_nested_edges` | 2.4 |
| `test_fov_h_is_derived_from_fov_v_and_aspect` | 2.6 |
| `TestInsertVertexEyePath` | 3.8 |
| `TestOverlapIntervals` | 4.7 |
| `test_validate_structure_multiple_eyepaths` | 4.1 |
| `test_local_basisu_binary_is_under_tool_root` | 4.4 |

**Still open**

| Gap | Why |
|---|---|
| Dirty-after-undo in `PassagesApp` | 2.3 lives only in `main.py` |
| Wall-builder closing-edge UV vs validator | Agreement is via shared helper; no UV assertion |
| `main.py` pick/drag, ImGui capture, resize | Manual checklist in the user guide is enough unless a headless smoke is added |
| `test_webp_mislabeled_as_png` in `test_validator.py` | Wrong file; move when touching tests |

---

## 8. Feature opportunities

Unchanged, except: slider grouping (item 8’s premise) is done via `_hist` coalesce; command-pattern history is only needed if levels outgrow full-document snapshots.

1. Bake from the editor (progress / cancel).
2. Marquee / multi-select.
3. Copy/paste and duplicate (`Ctrl+D`).
4. Measure / ruler and north indicator.
5. EyePath as a drawn graph (drag to connect).
6. Live 3D peek without a full egg rebuild per preview.
7. Overlay baked `occ_coverage` in the 2D view.
8. Command-pattern history (optional; snapshots + coalesce are enough for current sizes).
9. JSON Schema for `.passages.json` and `manifest.json`.
10. Drop tkinter file dialogs.

Out of scope: `passages_dm` bindings, combat, runtime FOV. Do not grow tags into a content editor.

---

## 9. Remaining order of work

P0 and core P1 are done. Next, if continuing this list:

1. **Docs pass** (§6) — user guide, README shortcuts, sample `fov_h`/`render_height`, `run.bat` cd. Highest user-facing leftover.
2. **Decide 4.3** — keep geometric midpoints (current) or cap travel with a shared `arch_view_angle()`. Content-visible.
3. **Decide 4.8** — keep largest-loop+holes (documented) or per-room floors. Content-visible.
4. **Small leftovers** — typed Validate issues (3.13), `from_dict` overlap error (4.7), chain KTX2 in `bake.bat` (4.4), `grid.cell_size` (3.3), `walls()`/`anchors()` (5.3).
5. **P2 splits** — `main.py` modules, `_render_camera` helper, logging, tiles.

Do not start 2 or 3 without an explicit product choice.

---

## 10. File map

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
| Publish | GitHub `MikeTronix/arctree_tools` folder `passages_tool/` (not a standalone remote) |
