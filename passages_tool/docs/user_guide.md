# Passages Level Editor — User's Guide

> **Version 1.0** · Tool located at `_local/tools/passages_tool/`

---

## Table of Contents

1. [Overview](#1-overview)
2. [Installation & Launch](#2-installation--launch)
3. [Interface Layout](#3-interface-layout)
4. [Viewport Navigation](#4-viewport-navigation)
5. [Tool Modes](#5-tool-modes)
6. [Working with Polylines](#6-working-with-polylines)
7. [Texture Palette](#7-texture-palette)
8. [Properties Panel](#8-properties-panel)
9. [File Operations](#9-file-operations)
10. [Keyboard & Mouse Reference](#10-keyboard--mouse-reference)
11. [Level File Format](#11-level-file-format)
12. [Troubleshooting](#12-troubleshooting)

---

## 1. Overview

The **Passages Level Editor** is a standalone 2D editor for designing level geometry used by the *Passages* minigame. It lets you:

- Draw and edit **polylines** — the primary level geometry primitive
- Assign **textures** to polylines from a browsable palette
- Pan and zoom a grid-backed **orthographic viewport**
- Save and load levels as human-readable **JSON files**
- Undo and redo any edit

The tool runs as a desktop Panda3D application with a Dear ImGui overlay for all panels and menus.

---

## 2. Installation & Launch

### Prerequisites

| Requirement | Version |
|---|---|
| Python | 3.10 or higher (Miniconda 3.12 confirmed working) |
| Panda3D | 1.10.16 (installed automatically) |
| panda3d-imgui | 1.2.0 (installed automatically) |

### First Run

Double-click `run.bat` in the `passages_tool/` folder. On the first run it will:

1. Create a `.venv/` virtual environment
2. Install all dependencies from PyPI (~80 MB download)
3. Launch the editor window

Subsequent launches skip steps 1–2 and open immediately.

```bat
cd _local\tools\passages_tool
run.bat
```

### Running from a terminal

```bat
cd _local\tools\passages_tool
.venv\Scripts\python.exe -m passages_tool.main
```

### Running from VSCode

Open `_local/tools/passages_tool/` as the workspace root. VSCode will automatically activate `.venv` in its integrated terminal (configured via `.vscode/settings.json`). Use the **Run** button or press `F5`.

> [!IMPORTANT]
> If VSCode shows import errors, select the correct interpreter: `Ctrl+Shift+P` → **Python: Select Interpreter** → choose `.venv\Scripts\python.exe`.

---

## 3. Interface Layout

```
┌─────────────────────────────────────────────────────────────────────────────┐
│  File  Edit  │  Tool: [ Select ]  [ Draw Polyline ]                         │  ← Menu bar
├───────────┬─────────────────────────────────────────────────────┬───────────┤
│           │                                                     │           │
│ Textures  │                                                     │Properties │
│           │              Viewport                               │           │
│ [thumb]   │         (pan, zoom, draw, select)                   │ Polyline  │
│ [thumb]   │                                                     │ ID: …     │
│ [thumb]   │                                                     │ Vertices  │
│           │                                                     │ Texture   │
│  detail   │                                                     │           │
│           │                                                     │           │
└───────────┴─────────────────────────────────────────────────────┴───────────┘
```

| Region | Description |
|---|---|
| **Menu bar** | File / Edit menus and in-line tool mode buttons |
| **Textures panel** (left) | Browse and select texture files; shows thumbnail grid and detail view |
| **Viewport** (centre) | Main editing canvas — the level geometry is drawn here |
| **Properties panel** (right) | Inspect and edit the selected polyline: vertices, texture, closed flag |

---

## 4. Viewport Navigation

The viewport uses an **orthographic camera** looking straight down the Y axis. All editing happens in the XZ plane.

| Action | Input |
|---|---|
| **Pan** | Hold **middle mouse button** and drag |
| **Zoom in** | **Scroll wheel up** |
| **Zoom out** | **Scroll wheel down** |

The background grid updates automatically as you zoom. Minor grid lines are drawn every **1 world unit**; major lines every **8 world units**.

> [!TIP]
> When a level is opened via **File → Open**, the viewport automatically zooms to fit the entire level.

---

## 5. Tool Modes

Switch modes with the buttons in the menu bar, or use keyboard shortcuts:

| Mode | Shortcut | Description |
|---|---|---|
| **Select** | `S` | Click to select a polyline; drag vertex handles to move them |
| **Draw Polyline** | `P` | Left-click on the viewport to add vertices one at a time |

The active mode button is highlighted green in the menu bar.

---

## 6. Working with Polylines

### Drawing a new polyline

1. Press `P` (or click **[ Draw Polyline ]**) to enter Draw mode.
2. **Left-click** anywhere in the viewport to place the first vertex.
   - A new polyline is created automatically on the first click.
3. Continue clicking to add more vertices.
4. Press **Enter** or **Right-click** to finish the current polyline.
   - You can immediately start drawing a new one by clicking again.

### Selecting a polyline

1. Press `S` (or click **[ Select ]**) to enter Select mode.
2. **Left-click** near a vertex handle (small white circle) to select its polyline.
3. The selected polyline turns **green**; unselected polylines are yellow.
4. Click empty space to deselect.

### Moving a vertex

Select the polyline, then type new coordinates directly in the **Properties panel** (see §8). Moved vertices are reflected immediately in the viewport.

### Deleting a vertex

In the Properties panel, click the **X** button next to any vertex row.

### Deleting a polyline

- Select the polyline, then press the **Delete** key.
- Or click **"Delete polyline"** in the Properties panel.

### Closing a polyline

Tick the **Closed** checkbox in the Properties panel. A closed polyline draws a final segment from its last vertex back to its first.

---

## 7. Texture Palette

The **Textures** panel on the left manages the texture library.

### Loading textures

1. Click **Browse folder…**
2. Select a folder containing image files (`.png`, `.jpg`, etc.).
3. Thumbnails appear in the panel.

### Selecting a texture

Click any thumbnail. The selected texture is highlighted green and its full-size preview appears below the thumbnail grid.

### Assigning a texture to a polyline

1. Select a texture in the palette.
2. Select a polyline in the viewport.
3. In the Properties panel, click **"Assign: \<texture name\>"**.

### Clearing a texture assignment

Click **"Clear"** next to the texture name in the Properties panel.

---

## 8. Properties Panel

The Properties panel shows details for the currently selected polyline.

| Field | Description |
|---|---|
| **ID** | Auto-generated UUID (first 16 characters shown) |
| **Vertices** | Count of vertices in this polyline |
| **Closed** | Checkbox — draws a closing segment back to vertex 0 |
| **Texture** | Currently assigned texture filename, or *(none)* |
| **Assign** button | Assigns the palette selection to this polyline |
| **Clear** button | Removes the texture assignment |
| **Vertex list** | Editable X/Z coordinate fields; **X** button deletes that vertex |
| **Delete polyline** | Permanently removes this polyline (undoable) |

> [!NOTE]
> Coordinates are in **world units**. The grid cell size is 1.0 world unit by default.

---

## 9. File Operations

### Menu bar shortcuts

| Action | Menu | Keyboard |
|---|---|---|
| New level | File → New | `Ctrl+N` |
| Open level | File → Open… | `Ctrl+O` |
| Save level | File → Save | `Ctrl+S` |
| Exit | File → Exit | `Alt+F4` |
| Undo | Edit → Undo | `Ctrl+Z` |
| Redo | Edit → Redo | `Ctrl+Y` |

- The title bar shows **"Save \*"** when there are unsaved changes.
- Opening or creating a new level with unsaved changes will prompt for confirmation.
- Files are saved with the `.passages.json` extension, added automatically if omitted.

---

## 10. Keyboard & Mouse Reference

### Keyboard

| Key | Action |
|---|---|
| `S` | Switch to Select tool |
| `P` | Switch to Draw Polyline tool |
| `Enter` | Finish current polyline (Draw mode) |
| `Delete` | Delete selected polyline |
| `Ctrl+Z` | Undo |
| `Ctrl+Y` | Redo |
| `Ctrl+S` | Save |
| `Ctrl+O` | Open |
| `Ctrl+N` | New |

### Mouse

| Button / Wheel | Action |
|---|---|
| **Left click** | Place vertex (Draw) / Select polyline (Select) |
| **Middle drag** | Pan viewport |
| **Scroll up** | Zoom in |
| **Scroll down** | Zoom out |
| **Right click** | Finish current polyline (Draw mode) |

> [!NOTE]
> When the mouse is over an ImGui panel (palette, properties, menu bar), viewport interactions are automatically suppressed so clicks do not accidentally place or select geometry.

---

## 11. Level File Format

Levels are saved as `.passages.json` files — plain UTF-8 JSON.

```json
{
  "version": 1,
  "meta": {
    "name": "My Level",
    "author": ""
  },
  "grid": {
    "cell_size": 1.0
  },
  "tiles": [
    { "x": 0, "y": 0, "texture": "grass.png" }
  ],
  "polylines": [
    {
      "id": "3f8a2b1c-…",
      "vertices": [[0.0, 0.0], [5.0, 0.0], [5.0, 3.0]],
      "texture": "wall.png",
      "closed": false
    }
  ]
}
```

| Field | Type | Description |
|---|---|---|
| `version` | integer | Format version (currently `1`) |
| `meta.name` | string | Human-readable level name |
| `meta.author` | string | Author name (optional) |
| `grid.cell_size` | float | World units per grid cell |
| `tiles` | array | Tile-based layer (reserved for future use) |
| `tiles[].x / .y` | integer | Tile grid coordinates |
| `tiles[].texture` | string \| null | Texture filename |
| `polylines` | array | All polylines in the level |
| `polylines[].id` | string | UUID, stable across saves |
| `polylines[].vertices` | `[[x,z],…]` | Ordered vertex list in world coords |
| `polylines[].texture` | string \| null | Assigned texture filename |
| `polylines[].closed` | boolean | If `true`, last vertex connects back to first |

> [!IMPORTANT]
> If you open a file whose `version` field is higher than the tool supports (currently `1`), the tool will refuse to open it and display an error. Always use the same tool version that created the file, or manually downgrade the version field at your own risk.

---

## 12. Troubleshooting

### Window opens but no ImGui panels are visible

The `p3dimgui` (panda3d-imgui) package failed to load. In the terminal:

```bat
.venv\Scripts\python.exe -c "import p3dimgui; print('OK')"
```

If this fails, reinstall:

```bat
.venv\Scripts\python.exe -m pip install panda3d-imgui
```

---

### `AttributeError: 'NodePath' has no attribute 'setBackgroundColor'`

Outdated code from before commit `66bb9ec`. Pull the latest version and retry.

---

### `ModuleNotFoundError: No module named 'p3dimgui'`

The venv was created with a broken pip shim (a Miniconda quirk). Fix:

```bat
REM Delete and recreate the venv
rmdir /s /q .venv
python -m venv .venv
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -e .[dev]
```

---

### `Read timed out` during pip install

PyPI download timed out. Retry with a larger timeout:

```bat
.venv\Scripts\python.exe -m pip install panda3d-imgui --timeout 120 --retries 5
```

---

### VSCode uses the wrong Python / shows import errors

1. Open the `passages_tool/` folder as the **workspace root** (`File → Open Folder`).
2. `Ctrl+Shift+P` → **Python: Select Interpreter** → pick `.venv\Scripts\python.exe`.

The `.vscode/settings.json` file locks this setting for the workspace permanently.

---

### Scrolling does not zoom

If the mouse is hovering over a panel (palette or properties), scroll events are captured by ImGui rather than the viewport. Move the mouse over the viewport background before scrolling.

---

### Level file from a newer version of the tool

The error *"Level version N is newer than this tool"* means the file was created by a future version. You will need to either update the tool or manually edit the `"version"` field back to `1` in a text editor (only if you are certain the format is compatible).
