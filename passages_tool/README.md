# Passages Tool — Level Editor & Render Pipeline

A standalone Python + Panda3D application for designing, compiling, and baking 2D level layouts into 3D environments for the **Passages** minigame (ArcTree Visual Novel Engine).

---

## Features

- **Orthographic 2D Viewport** — Pan (middle-mouse drag) and zoom (scroll wheel) with corrected camera projection matrix mappings.
- **Advanced Polyline Editor** — Draw, move, and edit vertex lists for **Walls**, **Arches** (supporting billboards and fixed orientation), and **EyePaths** (transition viewpoints).
- **Texture Intervals** — Assign multiple textures along different segments of a single Wall polyline with custom horizontal offsets.
- **Grid Snapping** — Toggle grid snap on/off (via `G` key) and customize the grid snap spacing metadata.
- **In-Editor 3D Preview** — Render an offscreen perspective view directly from a selected EyePath vertex inside an ImGui preview panel.
- **Asset Visibility Validator** — Toggle validation checks (via `V` key) to locate fixed arches that deviate near edge-on from the player's line of sight, highlighting them in bright red.
- **Automatic 3D Scene Compiler** — Exports level geometry into structured `.egg` files, performing triangulation for floors (CCW winding) and ceilings (CW winding) to ensure correct face-culling.
- **Baking & Midpoint Renderer** — Offscreen bakes static viewpoint frames (PNG) and midpoint traversal frames (PNG) with player headlight illumination and fog depth fading.
- **Shipping Transcoder** — Pillow and Basis Universal-based packaging script that compiles renders to `.ktx2` formats (with JPEG fallbacks) and alerts on any transparency anomalies before deployment.
- **Undo / Redo** — Robust history snapshot stack (`Ctrl+Z` / `Ctrl+Y`).

---

## Directory Architecture

```
passages_tool/
├── src/passages_tool/
│   ├── main.py            Editor entry point — ShowBase controller
│   ├── config.py          App-wide parameters and default style configurations
│   ├── converter/         3D Scene Compiler (JSON -> .egg)
│   │   ├── arch_builder.py          Arch geometry quads and billboard setup
│   │   ├── floor_ceiling_builder.py  Triangulated floors and ceilings with winding
│   │   ├── wall_builder.py           UV-wrapped continuous wall quads
│   │   ├── lighting_builder.py       Ambient and Arch point light sources
│   │   ├── scene_builder.py          Combined scene assembler and loader
│   │   └── egg_writer.py             EggData writer context wrapper
│   ├── renderer/          Offscreen Viewpoint Baker & Packager
│   │   ├── viewpoint_renderer.py     Panda3D offscreen perspective bakes
│   │   ├── transition_renderer.py    Linear traversal path calculator & Midpoint frame generator
│   │   ├── manifest.py               Render manifest manager
│   │   └── convert_to_jpeg.py        Game deployment KTX2/JPEG transcoder
│   ├── editor/            Core Data Model & Logic
│   │   ├── level.py       Level structure, migration, and CRUD handlers
│   │   ├── polyline.py    Scene graph representation of drawable lines
│   │   ├── history.py     Undo/redo command snapshot manager
│   │   └── validator.py   Fixed-arch visibility check engine
│   ├── ui/                Dear ImGui Panel Overlays
│   │   ├── toolbar.py     Top toolbar, mode selector, grid status
│   │   ├── palette.py     Texture browser, thumbnails, detail view
│   │   └── properties.py  Metadata inspector, vertex editor, preview panel
│   ├── io/                File Serialization
│   │   └── level_format.py JSON serializer supporting v1->v2 migrations
│   ├── textures/          Asset Management
│   │   └── manager.py     PIL thumbnail cached preloader & WebP mipmap handler
│   └── viewport/          Orthographic Cam & Rendering
│       ├── camera.py      Coordinate space raycaster and pan/zoom lens
│       └── grid.py        LineSegs layout grid background
├── assets/
│   └── sample_textures/   PNG textures and sprites for testing
└── json/                  Sample level JSON files
```

---

## Setup & Execution

### Prerequisites
- Python 3.10 or higher
- A virtual environment containing dependencies: `panda3d`, `panda3d-imgui`, `Pillow`, `numpy`, `pytest`, `pytest-mock`

### Initializing Sample Assets
Image assets are excluded from version control to keep the repository lightweight. Before running the editor or CLIs for the first time, extract the universal sample textures:
```bash
tar -xf sample_assets.tar
```
This will extract the standard assets into the `assets/sample_textures/` directory.

### Running the Editor
To run the 2D layout editor:
```bash
python -m passages_tool.main
```

### Running the 3D Geometry Converter CLI
To compile a level JSON into `.egg` models:
```bash
python -m passages_tool.converter json/onion.passages.json scene_out/ --textures assets/sample_textures/
```

### Running the Rendering Baker CLI
To bake viewpoints and midpoint frames:
```bash
python -m passages_tool.renderer json/onion.passages.json scene_out/ renders_out/ --textures assets/sample_textures/ --force
```

### Running the Shipping Transcoder CLI
To package PNGs into optimized game-ready KTX2 and JPEG fallbacks:
```bash
python -m passages_tool.renderer.convert_to_jpeg renders_out/ shipping_out/
```

### Running Tests
To execute the test suite:
```bash
python -m pytest
```

---

## Controls

| Category | Action | Input |
|---|---|---|
| **Viewport** | Pan viewport | Middle-mouse drag |
| | Zoom viewport | Scroll wheel |
| **Tools** | Select tool | `S` or toolbar |
| | Draw Polyline tool | `P` or toolbar |
| | Toggle Grid Snap | `G` or toolbar |
| | Toggle Asset Validator | `V` or toolbar |
| **Editing** | Add vertex | Left-click (draw mode) |
| | Select vertex / polyline | Left-click (select mode) |
| | Move vertex | Left-drag handle (select mode) |
| | Delete vertex | `Del` key |
| | Finish polyline | `Enter` or right-click |
| **App** | Undo | `Ctrl+Z` |
| | Redo | `Ctrl+Y` |
| | New level | `Ctrl+N` |
| | Open level | `Ctrl+O` |
| | Save level | `Ctrl+S` |

---

## Level File Format (v2)

Levels are serialized to JSON in a version 2 format that stores scale details, texture settings, point lights, and viewpoints:

```json
{
  "version": 2,
  "meta": {
    "name": "Pickle Dungeon",
    "author": "MRW",
    "wall_height": 4.0,
    "eye_height": 1.7,
    "fov_h": 90.0,
    "fov_v": 60.0,
    "pixels_per_meter": 256.0,
    "fog_start": 20.0,
    "fog_end": 40.0,
    "snap_grid": 0.5,
    "render_width": 1024,
    "render_height": 768,
    "floor_texture": "floor.png",
    "ceiling_texture": "ceiling_1.png"
  },
  "grid": {
    "cell_size": 1.0
  },
  "tiles": [],
  "polylines": [
    {
      "id": "wall_0",
      "type": "wall",
      "vertices": [[-7.0, 2.0], [-3.0, 2.0], [-3.0, 8.0], [-7.0, 8.0]],
      "closed": true,
      "texture_intervals": [
        {
          "from_vertex": 0,
          "to_vertex": 3,
          "texture": "elven_wall.png",
          "x_offset": 0.0
        }
      ]
    },
    {
      "id": "torch_0",
      "type": "arch",
      "position": [7.0, 0.0],
      "orientation": "billboard",
      "width": 4.0,
      "height_override": null,
      "texture": "arch_torch_alpha.png",
      "transparency": "alpha_test",
      "z_offset": 0.0,
      "v_at_floor": true,
      "is_light_source": true,
      "light_color": [1.0, 0.75, 0.4],
      "light_intensity": 1.0,
      "warning": false
    },
    {
      "id": "path_0",
      "type": "eyepath",
      "vertices": [[-6.0, 0.0], [-2.0, 0.0], [2.0, 0.0]],
      "edges": [[0, 1], [1, 2]]
    }
  ]
}
```
