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
| §3 P1 editor interaction | **done** | Nested `f07a0e3`; GitHub `b9f5b0a`; 3.13 typed warnings |
| §4 P1 bake / converter | **partial** | Per-room floors; geometric midpoints kept; first EyePath only; 4.2 combined `scene.egg` still a second CLI pass |
| §5 P2 architecture | **partial** | 5.1–5.4, 5.6–5.8 done; 5.5 EggContext still open |
| §6 Docs / onboarding | **done** | User guide rewritten; README shortcuts + 1024×576 sample; `run.bat`/`bake.bat` share `_ensure_venv.bat` (repairs leftover Miniconda venvs); rendering design marked superseded and tables patched |
| §7 Tests | **partial** | P0/P1 contracts covered; `main.py` / ImGui still untested |
| §8 Feature opportunities | **open** | After remaining P1 forks |

Tests at last polyline-union commit: **175 passed**.

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
| `Level.eyepaths()` / `walls()` / `anchors()` / `arches()` | `editor/level.py` | Typed polyline lists. Bake/preview still use the **first** EyePath. |
| `arch_view_angle(orientation, view)` | `editor/arch_utils.py` | Shared face-on/edge-on math → `ArchViewAngle` or `None`. Validator: `to_plane_deg`; `edge_on_check`: `from_normal_deg`. |
| `Level.sync_derived_fov_h()` | `editor/level.py` | Updates `meta.fov_h` without touching `dirty`. |
| `History.redo(current_snapshot)` | `editor/history.py` | Pushes current onto `_undos` before popping redo (undo→redo→undo no longer skips). |
| `validate_structure(level)` | `editor/validator.py` | Extra-EyePath warning. Called from editor Validate together with textures + arch visibility. |
| `build_scene(..., write_combined=True)` | `converter/scene_builder.py` | Writes the four component eggs from one geometry pass. Combined `scene.egg` is a **second** pass (Egg nodes cannot be dual-parented). Preview and baker pass `write_combined=False`; converter CLI still writes combined for pview. |
| `_write_egg(path, groups)` | `converter/scene_builder.py` | One-file EggData writer used by the four parts. |
| `local_basisu_binary()` | `renderer/convert_to_jpeg.py` | `TOOL_ROOT/bin/basisu[.exe]`. Drop the encoder there; `bake.bat` still does not chain the transcoder. |
| `_manifest_edge_entries(manifest)` | `renderer/convert_to_jpeg.py` | v2 nested `edges` plus legacy flat manifests. |
| `PassagesApp._hist(key=None)` | `app/commands.py` | Snapshot undo. Repeating `key` coalesces slider/drag/meta edits; `key=None` always pushes. |
| `PassagesApp._imgui_wants_keyboard()` | `app/input.py` | Gates `s/w/a/e/r/g/v`, Delete, Enter, Esc, snap, Validate. Ctrl+S still saves while typing. |
| `PassagesApp._select_at(wx, wz, mx, my)` | `app/input.py` | Screen-space vertex pick (`PICK_RADIUS_PX`) starts a drag; edge pick (NDC point-to-segment) selects. |
| `_point_seg_dist2` | `app/input.py` | NDC distance² from mouse to a segment. |
| `convert_polyline_type(pl, new_type)` | `app/commands.py` | After a yes/no dialog: arch/anchor keep vertex 0 and drop intervals/edges; wall drops edges; eyepath drops intervals. |
| `ViewpointRenderer._render_camera` | `renderer/viewpoint_renderer.py` | Shared offscreen camera + headlight + PNG write. |
| `get_logger` / `configure_cli` | `log.py` | Shared logging. |
| `TOOL_ROOT` / `EDITOR_STATE_PATH` | `config.py` | Tool checkout root (not `src/`). |
| `ViewportCamera.film_h`, `.win_w`, `.win_h` | `viewport/camera.py` | Resize-aware film and pick math. `_on_window_event` ignores offscreen buffers (`window != self.win`). |
| `BackgroundGrid.rebuild(..., cell=)` | `viewport/grid.py` | Minor spacing from `meta.snap_grid`; doubles `cell` if more than ~240 lines would be drawn. `Level.grid.cell_size` is still serialized and unused. |
| Editor state | `editor_state.json` (gitignored, tool root) | Remembers last texture directory. First launch scans `assets/sample_textures` if present. Texture scan is recursive (`relative/posix` names). |

Dirty tracking: `PassagesApp._saved_snapshot` + `_capture_saved` / `_refresh_dirty`. Do not trust `Level.from_dict().dirty` after undo.

Preview: `TOOL_ROOT / "temp_preview"`. `ViewpointRenderer` does **not** reparent the 3D scene onto the editor `render`.

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

### 3.3 Drawn grid vs snap grid — **done**

Viewport uses `meta.snap_grid`. On save, `grid.cell_size` is written as `snap_grid` (alias). On load, `cell_size` is ignored.

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

### 3.13 Validate is a modal dump — **done** (typed; floor/ceiling still no jump)

`ValidationWarning` has `kind` + `target_id` (`untextured_wall`, `interval_overlap`, `missing_floor`, `missing_ceiling`, `extra_eyepath`, `arch_edge_on`). `arch_id` is an alias of `target_id`. Select still frames a polyline when `target_id` is set; floor/ceiling remain level-meta (nothing to frame).

---

## 4. P1 — bake and converter pipeline

### 4.1 Only the first EyePath exists — **open**

`validate_structure` warns. Bake, preview, and `validate_arch_visibility` still use `eyepaths()[0]`. Namespaced or offset multi-path keys are a **separate** follow-up (client + baker together).

### 4.2 `build_scene` builds every mesh twice — **partial**

Four component eggs share one build. Combined `scene.egg` is still a second build when `write_combined=True` (converter CLI). Preview/baker skip it (`load_scene` never read `scene.egg`). Remaining: a combined file without a second tessellation, or drop `scene.egg`.

### 4.3 Shared `arch_view_angle()` / midpoint camera — **done** (geometric midpoints kept)

`arch_view_angle()` is shared. **Bake midpoints stay at geometric 50%** (explicit choice). Cap-travel remains unused in `compute_transition_path`.

### 4.4 `find_basisu` / bake shipping chain — **done**

`local_basisu_binary()` → tool-root `bin/`. `bake.bat` runs the PNG baker then `convert_to_jpeg` into `shipping_out/` (JPEG/PNG fallback if `basisu` is missing).

### 4.5 Baker does not delete stale images — **done**

After the final manifest rewrite, `find_stale_images` unlinks orphans.

### 4.6 Near/far and headlight magic numbers — **done** (fog coupling leftover)

Named constants in `config.py`, used by `ViewpointRenderer` and `setup_lighting`. Far plane is not derived from `fog_end`.

### 4.7 Overlapping texture intervals — **done**

Add is rejected; Validate warns (`interval_overlap`). `Polyline.from_dict` **drops later overlapping intervals** rather than refusing the file.

### 4.8 Floor = largest loop + holes — **done** (per-room floors)

Each closed wall is triangulated on its own (`_triangulate_loop`). Open walls contribute no floor. Nested loops both fill (authoring overlap; no pit/courtyard holes — Passages has no stairs/ramps). Bbox fallback only if nothing triangulates. Tests: `test_floor_two_disjoint_rooms`, `test_nested_closed_walls_both_get_floors`.

### 4.9 CLI help / defaults disagree — **done**

Config, baker `--height` help, README sample, user guide, and rendering-design tables all use **1024×576** and derived HFOV (~91.5° at 60° V). Older on-disk sample levels may still say 768/90 until re-saved.

---

## 5. P2 — architecture

### 5.1 `main.py` is the application — **done**

`PassagesApp` stays in `main.py` (ShowBase init, ImGui, grid/title). Mixins:

| Mixin | Path | Role |
|---|---|---|
| `InputMixin` | `app/input.py` | mouse/keyboard, draw, pick, snap, Validate |
| `CommandsMixin` | `app/commands.py` | file, undo, properties callbacks, history |
| `PreviewMixin` | `app/preview.py` | in-editor 3D peek |

Helpers `_point_seg_dist2` and `convert_polyline_type` live next to those mixins. Tests: `tests/test_app_helpers.py`.

### 5.2 One `Polyline` dataclass for four types — **done**

Runtime records are `Wall | Arch | EyePath | Anchor` (`editor/polyline_data.py`). `Polyline` is a factory namespace (`make_wall`, `from_dict`). `convert_polyline_type` returns a **new** object; `Level.replace_polyline` swaps it in. Type-specific fields (`edges`, `texture_intervals`, `closed`, …) exist only on the matching class.

### 5.3 Repeated “find the EyePath” loops — **done** (first-path policy remains)

`Level.eyepaths()`, `walls()`, `anchors()`, `arches()` exist. Manifest, baker, occluder, and viewpoint renderer still use the first EyePath.

### 5.4 `render_edge` / `render_midpoint` copies — **done**

`ViewpointRenderer._render_camera(pos, look_at, path, …)` owns buffer/lens/headlight/screenshot. `render_edge` looks from the start vertex; `render_midpoint` from the geometric 50% point. Placement is unchanged.

### 5.5 Converter `EggContext` vs raw `EggData` — **open**

`_write_egg` is a small step. Texture nodes still may not be `add_child`’d onto EggData.

### 5.6 Tiles are dead — **done**

`Tile` / `set_tile` / `get_tile` removed. `from_dict` ignores a legacy `tiles` key; `to_dict` does not write it. Floor-cell tiles were never used by the viewport or baker.

### 5.7 Logging is `print` — **done**

`passages_tool.log`: `get_logger`, `configure_cli` (INFO→stdout, WARNING+→stderr, message-only), `configure_editor`. Editor and CLIs use it. CLI output text is unchanged aside from a dropped extra blank line before midpoint baking.

### 5.8 Generated / local junk — **done**

`editor_state.json` and `.venv_uv/` are gitignored. Nested `.git` vs monorepo overlay is the established publish path. Wrong `pyproject.toml` package-data globs (`assets/**`, `icons/**` inside the Python package) removed. `TOOL_ROOT` / `EDITOR_STATE_PATH` live in `config.py`.

---

## 6. Docs and onboarding — **done** (Bake-from-editor leftover)

| Item | Shipped |
|---|---|
| User guide matches W/A/E/R, v2, drag, derived FOV, Validate, Save As | `docs/user_guide.md` rewritten |
| README controls + sample 1024×576 / derived `fov_h` ≈ 91.5 | `README.md` |
| Empty-window → `renders_out/` walkthrough | README § and user guide §3 |
| `run.bat` / `bake.bat` via `_ensure_venv.bat` | Local `.venv` is intended; broken leftover (Miniconda) is deleted and recreated |
| Rendering design status + FOV / types / floor / anchors / manifest | `docs/passages_rendering_design.md` banner + tables |

**Still not a docs issue:** File → Bake Level… is an editor feature (§8.1), not a documentation gap. `bake.bat` is documented.

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
| Dirty-after-undo in `PassagesApp` | 2.3 lives in `app/commands.py`; still needs a ShowBase harness |
| Wall-builder closing-edge UV vs validator | Agreement is via shared helper; no UV assertion |
| `main.py` pick/drag, ImGui capture, resize | Manual checklist in the user guide is enough unless a headless smoke is added |
| `test_webp_mislabeled_as_png` in `test_validator.py` | Wrong file; move when touching tests |

---

## 8. Feature opportunities

Slider grouping is done via `_hist` coalesce. Command-pattern history is only needed if levels outgrow full-document snapshots.

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
11. **Turn slew from a per-node yaw strip (client + baker).** Turns today alpha-crossfade two directed stills, so a 40° glance and a 160° about-face feel the same (no optic flow; player checks the compass). Bake **one cylindrical 360°×`fov_v` strip per EyePath vertex** (four 90° cube faces unwrapped; not a single pinhole 360). Runtime: pan a sliding `fov_h` window for a duration proportional to |Δyaw| (min ~80 ms, cap ~400 ms), then land on the existing hi-res `vXXXX_to_vYYYY` still. Hide anchors during the slew. Sweet-spot strip ~**2048×341** at 1024×576 / 91.5° HFOV (~2× upscale in motion). This is mostly a **minigame** change; the baker must grow first (extra renders per node, manifest key e.g. `eyepoints.v0000.yaw_strip`). Do not replace sharp viewpoints with the strip.
12. **Adjustable / HiDPI UI scale (editor).** On high-resolution monitors the ImGui panels, menu bar, and vertex labels are too small to use at a normal sitting distance. Add a persistent UI scale (e.g. 100/125/150/200%, or a font-size slider) via `imgui.get_io().font_global_scale` and `style.scale_all_sizes`, stored in `editor_state.json`. Default could follow Windows DPI. Viewport world units stay unchanged; only overlay chrome and text grow.

Out of scope: `passages_dm` bindings, combat, runtime FOV. Do not grow tags into a content editor.

---

## 9. Remaining order of work

P0, core P1, docs pass, per-room floors, and small leftovers are done. Geometric midpoints kept.

P2 union types are done. Remaining: **4.1** multi-EyePath bake (separate step, tool + minigame), **5.5** EggContext texture parenting.

**POM / meta-texturing** (`design_docs/passages_pom_metatexture_14SEP26.md`): Phase 0 **answered** on this GPU — custom GLSL writes into `make_texture_buffer` on hosts A/B/C (`python -m passages_tool.renderer.shader_probe`). `sampler2DArray` not proven. Remainder of the meta/POM plan is **shelved** until after 5.5 and the other queued work. Later POM is **silhouette-aware relief** (ray miss discards the geometric quad), not interior-only POM.

Next after the probe: **5.5** EggContext texture parenting, then 4.1 / Feature 11 / Feature 12 as previously planned.

---

## 10. File map

| Area | Paths |
|---|---|
| App shell | `src/passages_tool/main.py`, `app/input.py`, `app/commands.py`, `app/preview.py`, `log.py` |
| Document | `src/passages_tool/editor/level.py`, `polyline_data.py`, `history.py`, `validator.py`, `arch_utils.py` |
| Viewport gfx | `src/passages_tool/editor/polyline.py`, `viewport/camera.py`, `viewport/grid.py` |
| UI | `src/passages_tool/ui/toolbar.py`, `properties.py`, `palette.py` |
| I/O | `src/passages_tool/io/level_format.py` |
| Convert | `src/passages_tool/converter/*.py` |
| Bake | `src/passages_tool/renderer/viewpoint_renderer.py`, `manifest.py`, `occluder.py`, `convert_to_jpeg.py`, `__main__.py` |
| Docs | `README.md`, `docs/user_guide.md`, `docs/passages_rendering_design.md` |
| Launch | `run.bat`, `bake.bat`, `_ensure_venv.bat`, `pyproject.toml` |
| Publish | GitHub `MikeTronix/arctree_tools` folder `passages_tool/` (not a standalone remote) |
