"""
converter/egg_writer.py
───────────────────────
Helper wrapper for Panda3D's EggData library to generate .egg mesh files.
"""
from __future__ import annotations

from pathlib import Path
from typing import Optional
from panda3d.core import Filename, CS_zup_right
from panda3d.egg import EggData, EggGroup, EggPolygon, EggVertexPool, EggVertex, EggTexture


class EggContext:
    """
    Wraps EggData creation, providing helper methods to build vertices,
    polygons, and manage a shared texture pool with Z-up coordinates.
    """

    def __init__(self, name: str = "scene") -> None:
        self.data = EggData()
        self.data.set_coordinate_system(CS_zup_right)

        self.vpool = EggVertexPool(f"{name}_vpool")
        self.data.add_child(self.vpool)

        # Cache to reuse texture nodes in the egg file
        self.textures: dict[str, EggTexture] = {}

    def get_or_create_texture(self, texture_name: str) -> EggTexture:
        """
        Get or create an EggTexture node for a texture file name.
        Assumes texture paths are relative to the level's texture directory.

        The node is cached only. Callers (or ``parent_textures``) must
        ``add_child`` it onto the EggData that is actually written — this
        context's ``self.data`` is discarded when builders reparent the
        vertex pool onto a group.
        """
        if texture_name in self.textures:
            return self.textures[texture_name]

        # Use forward slashes for the EGG file texture reference
        clean_path = texture_name.replace("\\", "/")
        name = Path(clean_path).stem
        egg_tex = EggTexture(f"tex_{name}", clean_path)
        self.textures[texture_name] = egg_tex
        return egg_tex

    def add_vertex(
        self,
        x: float,
        y: float,
        z: float,
        u: Optional[float] = None,
        v: Optional[float] = None,
        normal: Optional[tuple[float, float, float]] = None,
    ) -> EggVertex:
        """Add a vertex to the vertex pool with optional UVs and normals."""
        vertex = EggVertex()
        vertex.set_pos((x, y, z))
        if u is not None and v is not None:
            vertex.set_uv((u, v))
        if normal is not None:
            vertex.set_normal(normal)
        self.vpool.add_vertex(vertex)
        return vertex

    def add_polygon(
        self, vertices: list[EggVertex], texture: Optional[EggTexture] = None
    ) -> EggPolygon:
        """Create a polygon from vertices and optionally bind a texture."""
        poly = EggPolygon()
        for vert in vertices:
            poly.add_vertex(vert)
        if texture is not None:
            poly.set_texture(texture)
        return poly

    def write(self, path: str | Path) -> bool:
        """Write the egg data out to a file on disk."""
        for tex in self.textures.values():
            if tex.get_parent() is None:
                self.data.add_child(tex)
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        fn = Filename.from_os_specific(str(p))
        return self.data.write_egg(fn)


def iter_bound_textures(node):
    """Yield EggTexture objects referenced by polygons under ``node``."""
    if hasattr(node, "get_num_textures"):
        for i in range(node.get_num_textures()):
            tex = node.get_texture(i)
            if tex is not None:
                yield tex
    if hasattr(node, "get_first_child"):
        child = node.get_first_child()
        while child is not None:
            yield from iter_bound_textures(child)
            child = node.get_next_child()


def parent_textures(egg: EggData, groups) -> None:
    """``add_child`` each unique bound EggTexture onto ``egg`` if unparented.

    Polygons can ``set_texture`` without the texture sitting in the egg
    graph. ``write_egg`` then omits the ``<Texture>`` block and pview /
    extra stages lose the map.
    """
    seen: set[int] = set()
    for grp in groups:
        for tex in iter_bound_textures(grp):
            ident = id(tex)
            if ident in seen:
                continue
            seen.add(ident)
            parent = tex.get_parent()
            if parent is None:
                egg.add_child(tex)
