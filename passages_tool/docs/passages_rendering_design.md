# Passages Minigame — Rendering System Design Document

> **Status:** Decisions locked as of 2026-06-16  
> **Tool:** `_local/tools/passages_tool/`  
> **Relates to:** `design_docs/arc_dev_spec_<latest>.md` (Passages minigame entry)

---

## 1. System Overview

Passages is a first-person corridor exploration minigame rendered using a **pre-computed viewpoint** strategy rather than a real-time engine.  Geometry is authored in the Passages Level Editor, converted to textured triangle strips (initially as `.egg` files), and rendered as single still images at each allowed viewpoint/direction combination.  Transitions between viewpoints are represented by a short blurred animation sequence.

The key insight is that **viewpoints are chosen by the designer**, not the player.  This allows the geometry to be cheap and the illusion of a varied environment to be maintained by ensuring that no viewpoint ever exposes the system's structural simplifications.

---

## 2. World Coordinate System

| Axis | Meaning |
|---|---|
| **X** | Horizontal position (left/right) |
| **Y** | Depth / forward direction (unused in editor; camera axis in 3D) |
| **Z** | Height (up/down) |

All polylines are drawn in the **XZ plane** in the editor.  The 3D converter extrudes Wall geometry vertically along Z, places Arch quads in the XY plane (rotated to face along the path), and places floor/ceiling quads at Z = 0 and Z = `level_wall_height` respectively.

**World units:** 1 world unit = a calibrated real-world distance (to be set in level metadata).  All texture pixel sizes, eye heights, and wall heights are expressed in world units.

---

## 3. Level-Wide Parameters

These are stored in the level metadata and apply to the entire level:

| Parameter | Description | Default |
|---|---|---|
| `wall_height` | Height of all walls and the implicit ceiling, in world units | `4.0` |
| `eye_height` | Camera height above floor for all EyePath viewpoints | `1.7` |
| `fov_h` | Horizontal field of view for all renders, in degrees | `90.0` |
| `fov_v` | Vertical field of view for all renders, in degrees | `60.0` |
| `texture_pixel_size` | World units per texture pixel (sets dimensional texture scale) | `0.01` |
| `fog_start` | World-unit depth at which fog begins (limits visible range) | `20.0` |
| `fog_end` | World-unit depth at which fog is fully opaque | `40.0` |
| `snap_grid` | Editor snap grid size in world units (small; keeps paths natural) | `0.25` |
| `render_width` | Horizontal resolution of baked viewpoint renders in pixels | `1024` |
| `render_height` | Vertical resolution of baked viewpoint renders in pixels | `768` |


---

## 4. Polyline Types

The editor supports three polyline types.  Each is displayed in a distinct colour with distinct visual cues.

### 4.1 Wall

A Wall is a vertical planar surface of uniform height (`wall_height`) rising from the floor (Z = 0).

**Visual representation in editor:**
- **Colour:** Yellow (`#E8C840`)
- **Interior side indicator:** Light hatching or a parallel dotted line on the **exterior** side (right-hand side when traversing vertices in creation order = interior side).  This asymmetry must be immediately legible to the user.
- The interior (right-hand) side is the textured, visible face in 3D.

**Geometry:**
- Each edge between consecutive vertices generates two triangles (a quad): bottom-left → bottom-right → top-right → top-left, where top = Z + `wall_height`.
- Normals point toward the interior (inward-facing).
- Both the floor edge and the top edge of each quad strip are explicit vertices.

**Data fields:**
```
type:               "wall"
vertices:           [[x, z], ...]          # XZ positions in creation order
texture_intervals:  [                      # see §6.1
  { from_vertex: int, to_vertex: int,
    texture: str, x_offset: float }
]
```

**Interior facing rule:** The interior (rendered) side is the **right-hand side** when traversing vertices in creation order.  If the level has a single closed corridor, walls are drawn clockwise when viewed from above so their interior sides face inward.

---

### 4.2 Arch

An Arch is a flat, vertically-oriented quad placed at a specific point in the level.  It is always the full `wall_height` tall (unless `height_override` is set).  Arches are two-sided (like the cross-plane tree models used in flight simulators).

**Typical uses:**

| Use case | Transparency | Orientation |
|---|---|---|
| Corridor arch / tunnel profile | Partial (alpha-tested) | Fixed, perpendicular to passage direction |
| Doorway | High (alpha-blended) | Fixed, perpendicular to passage |
| Torch or wall sconce | Partial | Billboard (always faces viewpoint) |
| Column or post | Opaque or partial | Fixed or billboard |
| Floor item (rug, stair illusion) | Partial | Fixed, horizontal — use a Z-offset |

**Visual representation in editor:**
- **Colour:** Cyan (`#40C8E8`)
- Displayed as a line segment with small perpendicular tick marks indicating its orientation in the XZ plane.
- A circular arc on one end indicates "billboard" mode.

**Orientation modes:**

| Mode | Description |
|---|---|
| `fixed` | Orientation is set by the user (angle stored in data).  Snaps to perpendicular to the nearest Wall polyline if within threshold.  A warning flag is raised if path tangent is ambiguous at this location. |
| `billboard` | Quad always rotates to face the current viewpoint.  Suitable for small items (torches, posts). |

**Placement:** User-placed.  Position stored as a single `(x, z)` point; orientation stored as an angle or as `billboard`.  There is no auto-spacing; the designer controls all placements.  Phasing (irregular spacing) is intentional to avoid regularity.

**Texture stretching policy:** Some stretching is acceptable, but extreme stretching (aspect ratio > 3:1 from the intended pixel size) must be flagged by the editor as a warning.

**Data fields:**
```
type:              "arch"
position:          [x, z]
orientation:       "billboard" | angle_degrees
height_override:   float | null    # null = use level wall_height
width:             float           # full width of the quad in world units
texture:           str | null
transparency:      "none" | "alpha_test" | "alpha_blend"
z_offset:          float           # 0.0 for normal, >0 for floor items
v_at_floor:        bool            # true = V=0 always at Z=0 regardless of z_offset
is_light_source:   bool            # true = also place a PointLight at this position
light_color:       [r, g, b]       # RGB 0.0-1.0; only used when is_light_source=true
light_intensity:   float           # multiplier; only used when is_light_source=true
```

---

### 4.3 EyePath

An EyePath defines the allowed viewpoint locations and the connectivity between them.

**Visual representation in editor:**
- **Colour:** Green (`#40E880`)
- Displayed as connected dots with directed arrows showing which pairs of points are accessible from each other (connectivity graph).

**Viewpoint model:**
- Each EyePath vertex is a viewpoint at `(x, eye_height, z)` in 3D.
- At each viewpoint, the player can face in any direction that leads to an **adjacent accessible viewpoint**.  No other yaw angles are rendered.
- The player selects facing direction with **arrow keys** or **`A` / `D`** (cycle through accessible neighbours).

**Connectivity:**
- Stored as an undirected graph: each vertex has a list of indices of its accessible neighbours.
- In the editor, the user draws EyePath edges explicitly (like polyline edges) or uses an auto-connect-to-nearest tool.

**Data fields:**
```
type:              "eyepath"
vertices:          [[x, z], ...]
edges:             [[v_from, v_to], ...]   # undirected pairs
```

---

### 4.4 Anchor (Sprite Slot)

An Anchor defines a physical slot in the level where dynamic 2D billboard sprites (NPCs, items, monsters) can be dynamically projected and rendered at runtime. Anchors do not compile into 3D meshes in the exported level geometry; instead, they serve as semantic positioning landmarks and are processed during the baking phase to precalculate viewpoint visibility and screen-space projections.

**Visual representation in editor:**
- **Colour:** Magenta (`#E840C8`)
- Displayed as a circle with crosshairs and a bounding radius representing the sprite's occupancy/interaction area.

**Visibility & Projection Processing:**
During the offline baking phase, for each directed EyePath edge `v_from -> v_to`, the renderer calculates if the Anchor is visible and precomputes its screen-space coordinates.
An Anchor is considered **visible** from a viewpoint if:
1. It is within the camera's horizontal field of view (`fov_h` / 2) relative to the gaze direction.
2. The distance from the viewpoint to the anchor is less than or equal to `max_distance` (and within `fog_end`).
3. **Line-of-Sight (LOS) check:** The straight-line segment from the viewpoint coordinate to the anchor coordinate does not intersect any Wall polylines or opaque/non-transparent Arch polylines.

If visible, the renderer projects the anchor's 3D position `(x, y, z_offset)` onto the viewpoint camera plane and writes the projected screen-space coordinate and distance-based scale factor into the manifest JSON.

**Data fields:**
```
type:              "anchor"
position:          [x, y]          # Editor vertical axis is ground-Y under Z-up
z_offset:          float           # Height offset above floor (default: 0.0)
radius:            float           # Bounding occupancy/interaction radius in world units (default: 0.5)
max_distance:      float           # Maximum visibility distance (default: 10.0)
fov_limit:         float | null    # Optional restriction on horizontal view angle (default: null = use camera FOV)
sprite_count:      int             # Expected number of sprites allowed at this slot (default: 1)
```

---

## 5. Implicit Geometry (Generated by Converter)

### 5.1 Floor

- A single quad at Z = 0.
- Spans the bounding box of all Wall polylines in the level, plus a small margin.
- UV-mapped using the level's `texture_pixel_size` from a designated floor texture.
- No perturbations; always perfectly flat.

### 5.2 Ceiling

- A single quad at Z = `wall_height`.
- Same XZ extent as the floor.
- Textured with a designated ceiling texture.
- No cutouts or perturbations.  Arches provide the *illusion* of varied ceiling height; the ceiling itself is always flat.

> **Note:** The ceiling is visible from all viewpoints through any gaps between Arches.  Arches must be designed so their opaque or alpha regions prevent the ceiling from looking structurally false.

---

## 6. Texture System

### 6.1 Per-Segment Texture Intervals (Walls)

Walls use `texture_intervals` instead of a single texture.  Each interval covers a range of consecutive vertices and specifies:

- `from_vertex` / `to_vertex` — inclusive vertex indices
- `texture` — filename of the texture for this segment
- `x_offset` — horizontal pixel offset into the texture at the start of this segment (default: 0.0)

**UV continuity:** When a texture interval ends and a new one begins, the new interval starts at its own `x_offset`.  If two consecutive intervals use the **same texture**, the UV offset is carried over automatically so there is no seam.

**Dimensional UV mapping:**
- U coordinate along the wall = `distance_along_wall / texture_pixel_size / texture_width_pixels`
- V coordinate vertically = `z / texture_pixel_size / texture_height_pixels`
- V = 0 is always at the floor (Z = 0); V = 1 is at the top of the texture as authored.
- V offsets when starting a new texture are **not supported** (textures are authored with a defined floor baseline).

### 6.2 Arch Textures

- Each Arch has a single texture covering its full quad.
- Stretching is controlled by `width` and `height_override`; the converter maps U=[0,1] × V=[0,1] across the quad.
- Pixel-accurate sizing is a secondary concern for Arches; the designer is responsible for choosing textures that look acceptable at the quad's aspect ratio.

### 6.3 Floor and Ceiling Textures

- Tiled using `texture_pixel_size` with U along X and V along Z.
- Stored in level metadata as `floor_texture` and `ceiling_texture`.

---

## 7. Converter Pipeline

The converter reads a `.passages.json` level file and produces geometry.

### 7.1 Output Format

- **Primary:** Panda3D `.egg` files, one per logical region or per full level.  EGG format is human-readable, inspectable in `pview`, and suitable for early debugging.
- **Future:** Direct Panda3D `.bam` binary or runtime `GeomNode` generation.

### 7.2 Wall Strip Generation

For each edge `(v_i, v_{i+1})` in a Wall polyline within a single texture interval:

1. Compute the four 3D vertices: `(x_i, 0, z_i)`, `(x_{i+1}, 0, z_{i+1})`, `(x_{i+1}, 0, z_{i+1} + wall_height)`, `(x_i, 0, z_i + wall_height)`.
2. Compute inward-facing normal (right-hand rule from interior side).
3. Compute U coordinates from cumulative arc length; carry UV offset across interval boundaries.
4. Emit two triangles (one quad).

### 7.3 Path Tangent Computation (for Arches)

For a fixed-orientation Arch placed along a passage:
- The snap target orientation is perpendicular to the nearest Wall polyline edge.
- If the nearest Wall edge tangent is ambiguous (e.g. at a sharp corner), the editor flags the Arch with a warning and requests manual orientation confirmation.

### 7.4 Arch Quad Generation

For each Arch:
1. Place a quad centred at `(x, z_offset + height/2, z)` in 3D.
2. If `fixed`: rotate quad around the vertical axis by the stored angle.
3. If `billboard`: mark node as a Panda3D billboard that rotates around its vertical axis toward the camera each frame.
4. Set `TransparencyAttrib` per the `transparency` field.
5. Place as a separate `GeomNode` (not merged) to allow correct depth sorting.

> **Depth sorting:** Panda3D's `NodePath.setTransparency(TransparencyAttrib.MAlpha)` handles back-to-front sorting automatically when nodes are separate.  `TransparencyAttrib.MDual` (two-pass) is the fallback for overlapping arches.

### 7.5 Floor and Ceiling Generation

- Two large quads with tiled UV mapping.
- No alpha; always rendered first (no depth sorting needed).

### 7.6 Lighting

- **Model:** Simple diffuse point lighting.
- **Sources:** Torch and window Arches also create `PointLight` nodes at the same position.
- **Shader:** Panda3D's default auto-shader.  No custom GLSL needed at this stage.
- **Fog:** `ExponentialFog` (or linear) applied to limit visible depth and disguise the geometry cutoff.

### 7.7 Visibility and Culling (per EyePath viewpoint)

The converter (or a companion pre-computation tool) produces, for each `(eyepath_vertex, facing_direction)` pair:

1. **Frustum cull** — discard objects outside the view frustum (FOV + depth range).
2. **Range cull** — discard objects beyond `fog_end` (they are invisible through fog).
3. **Occlusion approximation** — project each surviving object's bounding box onto the focal plane, record `(min_col, max_col, min_row, max_row)`, and discard objects that are fully covered by closer opaque objects.  (Panda3D's built-in portal occlusion system may be usable here if the level is structured as cells/portals.)
4. **Sort transparent objects** back-to-front for correct alpha rendering.
5. Render remaining objects with Panda3D.

> Panda3D resources for culling: `BoundingVolume`, `Camera.setLens` with `PerspectiveLens`, `CullBinManager`, `ShaderTerrainMesh` (not applicable here), `SceneGraphAnalyzer`.  For per-viewpoint occlusion, a simple Python pre-computation loop is more controllable than the automatic system.

---

## 8. Rendered Output and Transitions

### 8.1 Per-Viewpoint Render

- One still image per `(eyepath_vertex, facing_direction)` combination.
- Rendered offline using Panda3D's offscreen buffer.
- **Format during authoring: PNG** (lossless, preserves any residual transparency
  for inspection and debugging).
- **Format for shipping: JPEG** — after all renders are finalised and confirmed
  fully opaque, a one-time conversion tool (`convert_to_jpeg.py`) composites
  each PNG onto a black background, checks for any remaining transparent pixels
  (warns if found — these indicate an unresolved geometry gap), and saves at
  a configured quality level (default 92).
- Stored in the level's `renders/` directory (PNG) or `shipping/` directory (JPEG).

### 8.2 Viewpoint Transitions

To represent movement between eye points:

1. Render a short sequence of frames along a small linear path from the old viewpoint toward the new viewpoint (distance chosen so no Arch becomes edge-on during the traversal).
2. Apply a motion blur or temporal blend to produce a brief animation (e.g. 0.3–0.5 seconds, 6–10 frames).
3. Also render the same short sequence in reverse from the new viewpoint looking back, for returning along the same path.
4. Store both sequences as short looping GIFs or sprite strips; play the appropriate one on player movement.

> **Constraint:** The traversal sub-path for transition frames must be kept short enough that no Arch's angular orientation to the camera deviates enough from face-on to expose the billboard illusion.

---

## 9. Editor Requirements (additions to current tool)

### 9.1 Polyline Type System

- Add a `type` field to each polyline: `wall | arch | eyepath`.
- Type selector in the Properties panel.
- Type-specific property fields in Properties panel (see §4).
- Per-type display colours:

| Type | Viewport colour |
|---|---|
| Wall | Yellow `#E8C840` |
| Arch | Cyan `#40C8E8` |
| EyePath | Green `#40E880` |

### 9.2 Wall Interior Side Indicator

The editor must make the interior (right-hand) side of a Wall visually distinct.  Options (to be implemented):
- **Hatching:** Short diagonal tick marks perpendicular to the polyline, on the exterior (left-hand) side.
- **Dotted parallel line:** A dashed line offset 0.3 world units to the exterior.

The hatching approach is preferred as it is unambiguous and does not clutter the view.

### 9.3 EyePath Connectivity Graph

- EyePath edges drawn as directed arrows in the editor.
- Each vertex shows its accessible neighbours.
- Clicking a vertex highlights its neighbour set.

### 9.4 Arch Placement and Orientation Cues

- Arch displayed as a line with perpendicular tick marks in the editor.
- Billboard arches show a small circular arc symbol.
- Orientation snap: when placed near a Wall, the Arch snaps its orientation to be perpendicular to the nearest Wall edge.
- **Warning flag:** If path tangent near the Arch is ambiguous (sharp corner, branching), a yellow warning icon is shown and manual orientation confirmation is requested.

### 9.5 EyePath 3D Preview

- A "Render preview from here" button in the Properties panel for a selected EyePath vertex.
- Opens a small Panda3D offscreen render and displays the result as an image.
- Required before the full converter is complete; helps validate Arch placement.

### 9.6 Snap-to-Grid

- Global snap grid size: `snap_grid` (default 0.25 world units) from level metadata.
- Toggle: `G` key or a toolbar button.
- Applied in Draw Polyline and Select (vertex drag) modes.
- Small grid keeps paths natural-looking; not enforced for Arch position placement.

### 9.7 Texture Interval Editor

- In the Wall Properties panel, a list of texture intervals (start vertex, end vertex, texture, x_offset).
- Buttons to add/split/remove intervals.
- Colour-coded segment highlights in the viewport showing which interval covers which edges.

---

## 10. Data Model Changes (JSON v2)

The following changes are planned for level file version 2:

```json
{
  "version": 2,
  "meta": {
    "name": "str",
    "author": "str",
    "wall_height": 4.0,
    "eye_height": 1.7,
    "fov_h": 90.0,
    "fov_v": 60.0,
    "texture_pixel_size": 0.01,
    "fog_start": 20.0,
    "fog_end": 40.0,
    "snap_grid": 0.25,
    "floor_texture": "str | null",
    "ceiling_texture": "str | null"
  },
  "polylines": [
    {
      "id": "uuid",
      "type": "wall",
      "vertices": [[x, z]],
      "texture_intervals": [
        { "from_vertex": 0, "to_vertex": 3,
          "texture": "stone.png", "x_offset": 0.0 }
      ]
    },
    {
      "id": "uuid",
      "type": "arch",
      "position": [x, z],
      "orientation": "billboard | angle_degrees",
      "height_override": null,
      "width": 4.0,
      "texture": "arch_gothic.png",
      "transparency": "alpha_test | alpha_blend | none",
      "z_offset": 0.0,
      "v_at_floor": true,
      "is_light_source": false,
      "light_color": [1.0, 0.75, 0.4],
      "light_intensity": 1.0
    },
    {
      "id": "uuid",
      "type": "eyepath",
      "vertices": [[x, z]],
      "edges": [[0, 1], [1, 2]]
    }
  ]
}
```

> **Migration:** Version 1 files (plain polylines) are auto-migrated on open; type defaults to `wall`, and `texture_intervals` is synthesised from the single `texture` field.

---

## 11. Open Questions and Deferred Decisions

| Item | Status | Note |

---

## 12. Addenda (agreed 2026-06-16)

### 12.1 Billboard arches and the transition-frame edge-on constraint

Billboard arches are immune to the no-edge-on constraint during transition animation frames (they always face the camera).  Fixed arches are **not** immune.  When generating transition sub-path frames, the same angular check used for static viewpoints must be applied along the sub-path.  The threshold angle (maximum deviation from face-on before the arch looks wrong) will be determined empirically during initial testing, but 60° is the starting estimate.

### 12.2 Arch V-baseline convention for floor-item arches

All arch textures are authored so that V = 0 corresponds to floor level (Z = 0).  For floor-item arches with `z_offset > 0`, the raised quad means V = 0 no longer aligns with Z = 0.  These arches carry an explicit boolean flag `v_at_floor: true` (default) or `v_at_floor: false`.  When `v_at_floor: true`, the converter shifts the V coordinate so the texture baseline stays at Z = 0 regardless of `z_offset`.

### 12.3 EyePath edge list as the render manifest

The EyePath adjacency graph is the **complete and authoritative render manifest**.  Each directed edge `(vertex_i → vertex_j)` defines exactly one rendered image: the view from vertex_i, looking toward vertex_j.  Image filenames are derived deterministically:

```
render_v{i:04d}_to_v{j:04d}.png
```

This means:
- The editor's connectivity graph and the renderer's output file set are always in sync.
- A missing image file = an edge that has not yet been rendered.
- An extra image file = an edge that has been removed from the graph (stale; can be deleted).
- The game runtime only needs the edge list and the image directory to know what views are available.

### 12.4 Arch light source fields

Arches that represent torches, windows, or other light sources carry three explicit fields:

| Field | Type | Description |
|---|---|---|
| `is_light_source` | bool | If `true`, a `PointLight` is placed at the arch position |
| `light_color` | `[r, g, b]` | Normalised RGB (0.0–1.0); default warm torch yellow `[1.0, 0.75, 0.4]` |
| `light_intensity` | float | Intensity multiplier; default `1.0` |

Light source status is **never inferred** from texture name or transparency mode.
Different torch arches may have different colours (e.g. blue magical flames) and
different intensities (e.g. a window letting in daylight vs a guttering candle).

### 12.5 PNG during authoring, JPEG at shipping

All rendered viewpoint images are saved as **PNG** during authoring:
- PNG is lossless and supports the alpha channel.
- Any transparent pixel in a finished render indicates an unresolved geometry gap
  (missing wall, ceiling, or floor coverage) — this is a **debugging signal**,
  not something to hide.

When the level is complete and all renders are confirmed fully opaque, the
`convert_to_jpeg` tool performs a one-time conversion:
- Composites each PNG onto a black background (catches any remaining transparency).
- Warns on any image with residual transparent pixels.
- Saves JPEG at configurable quality (default 92).
- Does **not** delete the source PNGs (they remain as the authoritative archive).

| Item | Status | Note |
|---|---|---|
| Light source flicker animation | Deferred | Arch will gain `flicker_rate` and `flicker_amplitude` fields when needed. For pre-rendered stills, two options: (a) bake multiple lighting variants per viewpoint and cycle them in-game, or (b) simpler post-process overlay (warm-tinted canvas layer pulsed near known torch positions). Approach TBD. |
| Corridor width visualisation in editor | Deferred | May not be needed once type colours and hatching are in place |

| Branching EyePath connectivity (non-linear paths) | Design TBD | Data model supports it (edge list); UI for editing not yet designed |
| Level-to-level transitions | Deferred | Default: walk through a doorway Arch; destination level defined as Arch metadata |
| `.bam` export from converter | Deferred | Start with `.egg`; add `.bam` when geometry is stable |
| Automatic Arch spacing / layout | Deferred | Currently user-placed; revisit after a full level has been hand-authored |
| Ramps and floor level changes | Out of scope (v1) | Use level-change doorways instead |
| Ceiling cutouts (real arched ceilings) | Out of scope (v1) | Flat ceiling + Arch texture illusion sufficient |
