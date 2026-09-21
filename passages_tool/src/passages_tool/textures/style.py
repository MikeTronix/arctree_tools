"""Style pack load (S1). No compose, no eggs, no visual change.

A style is ``styles/<id>.json`` under the texture directory. Preset maps live
in ``presets/<id>/diffuse.png``. See ``design_docs/passages_style_dressing_20SEP26.md``.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

BUILTIN_OPENING_PROFILES: tuple[str, ...] = ("rect", "round", "gothic")


class StyleError(ValueError):
    """Invalid or unreadable style JSON."""


@dataclass(frozen=True)
class StyleBand:
    id: str
    z0: float
    z1: float
    preset: str
    tile_meters: Optional[tuple[float, float]] = None
    pom: bool = False
    height_scale_m: Optional[float] = None


@dataclass(frozen=True)
class StyleOpeningDefaults:
    profile: str = "rect"
    depth_m: float = 0.4
    side_preset: Optional[str] = None


@dataclass(frozen=True)
class StyleNiche:
    height_scale_m: float = 0.35
    pom: bool = True


@dataclass(frozen=True)
class StyleOverlays:
    seed: int = 0
    wetness: float = 0.0
    moss: float = 0.0
    graffiti: float = 0.0


@dataclass(frozen=True)
class StyleSurface:
    preset: str
    tile_meters: Optional[tuple[float, float]] = None


@dataclass(frozen=True)
class StyleBeams:
    spacing_m: float = 2.0
    width_m: float = 0.2
    depth_m: float = 0.15
    preset: Optional[str] = None


@dataclass(frozen=True)
class StyleCeiling:
    preset: Optional[str] = None
    tile_meters: Optional[tuple[float, float]] = None
    mode: str = "closed"
    beams: Optional[StyleBeams] = None


@dataclass(frozen=True)
class StylePack:
    version: int
    id: str
    wall_height_m: float
    bands: tuple[StyleBand, ...]
    opening_profiles: tuple[str, ...]
    default_opening: StyleOpeningDefaults
    niche: StyleNiche
    overlays: StyleOverlays
    ceiling: Optional[StyleCeiling] = None
    floor: Optional[StyleSurface] = None
    loop_u: bool = True
    path: Optional[Path] = None

    def preset_ids(self) -> tuple[str, ...]:
        ids: list[str] = []
        for b in self.bands:
            ids.append(b.preset)
        if self.default_opening.side_preset:
            ids.append(self.default_opening.side_preset)
        if self.ceiling and self.ceiling.preset:
            ids.append(self.ceiling.preset)
        if self.ceiling and self.ceiling.beams and self.ceiling.beams.preset:
            ids.append(self.ceiling.beams.preset)
        if self.floor:
            ids.append(self.floor.preset)
        # unique, stable order
        seen: set[str] = set()
        out: list[str] = []
        for i in ids:
            if i not in seen:
                seen.add(i)
                out.append(i)
        return tuple(out)


def style_json_path(texture_dir: Path, style: str) -> Path:
    """Resolve ``LevelMeta.style`` (id or relative .json) under ``texture_dir``."""
    raw = str(style).strip().replace("\\", "/")
    if not raw:
        raise StyleError("empty style id")
    p = Path(raw)
    if p.is_absolute():
        return p
    if raw.endswith(".json") or "/" in raw:
        return texture_dir / p
    return texture_dir / "styles" / f"{raw}.json"


def preset_dir(texture_dir: Path, preset_id: str) -> Optional[Path]:
    """``texture_dir/presets/<id>``, or None if the id is unsafe."""
    name = str(preset_id).strip()
    if not name or name in (".", "..") or "/" in name or "\\" in name:
        return None
    root = (texture_dir / "presets").resolve()
    dest = (root / name).resolve()
    try:
        dest.relative_to(root)
    except ValueError:
        return None
    return dest


def preset_has_diffuse(texture_dir: Path, preset_id: str) -> bool:
    d = preset_dir(texture_dir, preset_id)
    return bool(d and (d / "diffuse.png").is_file())


def _pair_meters(raw: Any, *, field: str) -> Optional[tuple[float, float]]:
    if raw is None:
        return None
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        raise StyleError(f"{field} must be [u, v] meters")
    u, v = float(raw[0]), float(raw[1])
    if u <= 0.0 or v <= 0.0:
        raise StyleError(f"{field} values must be > 0")
    return (u, v)


def _parse_band(raw: Any, index: int) -> StyleBand:
    if not isinstance(raw, dict):
        raise StyleError(f"bands[{index}] must be an object")
    bid = str(raw.get("id") or "").strip()
    if not bid:
        raise StyleError(f"bands[{index}] missing id")
    preset = str(raw.get("preset") or "").strip()
    if not preset:
        raise StyleError(f"bands[{index}] ({bid}) missing preset")
    z = raw.get("z")
    if not isinstance(z, (list, tuple)) or len(z) != 2:
        raise StyleError(f"bands[{index}] ({bid}) z must be [z0, z1]")
    z0, z1 = float(z[0]), float(z[1])
    if z1 <= z0:
        raise StyleError(f"bands[{index}] ({bid}) z[1] must be > z[0]")
    hsm = raw.get("height_scale_m")
    return StyleBand(
        id=bid,
        z0=z0,
        z1=z1,
        preset=preset,
        tile_meters=_pair_meters(raw.get("tile_meters"), field=f"bands[{index}].tile_meters"),
        pom=bool(raw.get("pom", False)),
        height_scale_m=float(hsm) if hsm is not None else None,
    )


def _parse_beams(raw: Any) -> Optional[StyleBeams]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise StyleError("ceiling.beams must be an object")
    spacing = float(raw.get("spacing_m", 2.0))
    width = float(raw.get("width_m", 0.2))
    depth = float(raw.get("depth_m", 0.15))
    if spacing <= 0.0 or width <= 0.0 or depth <= 0.0:
        raise StyleError("ceiling.beams spacing_m/width_m/depth_m must be > 0")
    preset = raw.get("preset")
    return StyleBeams(
        spacing_m=spacing,
        width_m=width,
        depth_m=depth,
        preset=(str(preset).strip() or None) if preset is not None else None,
    )


def _parse_ceiling(raw: Any) -> Optional[StyleCeiling]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise StyleError("ceiling must be an object")
    mode = str(raw.get("mode") or "closed").strip()
    if mode not in ("closed", "none"):
        raise StyleError("ceiling.mode must be 'closed' or 'none'")
    preset = str(raw.get("preset") or "").strip() or None
    return StyleCeiling(
        preset=preset,
        tile_meters=_pair_meters(raw.get("tile_meters"), field="ceiling.tile_meters")
        if raw.get("tile_meters") is not None
        else None,
        mode=mode,
        beams=_parse_beams(raw.get("beams")),
    )


def _parse_surface(raw: Any, field: str) -> Optional[StyleSurface]:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        raise StyleError(f"{field} must be an object")
    preset = str(raw.get("preset") or "").strip()
    if not preset:
        raise StyleError(f"{field} missing preset")
    return StyleSurface(
        preset=preset,
        tile_meters=_pair_meters(raw.get("tile_meters"), field=f"{field}.tile_meters"),
    )


def load_style(path: Path) -> StylePack:
    """Load and structurally validate a style JSON file."""
    p = Path(path)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except OSError as e:
        raise StyleError(f"cannot read {p}: {e}") from e
    except json.JSONDecodeError as e:
        raise StyleError(f"invalid JSON in {p}: {e}") from e
    if not isinstance(data, dict):
        raise StyleError("style root must be an object")
    if int(data.get("version", 0)) != 1:
        raise StyleError("style version must be 1")
    sid = str(data.get("id") or "").strip()
    if not sid:
        raise StyleError("style missing id")

    bands_raw = data.get("bands")
    if not isinstance(bands_raw, list) or not bands_raw:
        raise StyleError("style must have a non-empty bands list")
    bands: list[StyleBand] = []
    seen: set[str] = set()
    for i, item in enumerate(bands_raw):
        b = _parse_band(item, i)
        if b.id in seen:
            raise StyleError(f"duplicate band id {b.id!r}")
        seen.add(b.id)
        bands.append(b)

    profiles_raw = data.get("opening_profiles")
    if profiles_raw is None:
        profiles = BUILTIN_OPENING_PROFILES
    elif not isinstance(profiles_raw, list) or not profiles_raw:
        raise StyleError("opening_profiles must be a non-empty list")
    else:
        profiles = tuple(str(x).strip() for x in profiles_raw)
        if any(not x for x in profiles):
            raise StyleError("opening_profiles contains an empty name")

    od = data.get("default_opening") or {}
    if not isinstance(od, dict):
        raise StyleError("default_opening must be an object")
    profile = str(od.get("profile") or profiles[0]).strip()
    side = od.get("side_preset")
    opening = StyleOpeningDefaults(
        profile=profile,
        depth_m=float(od.get("depth_m", 0.4)),
        side_preset=(str(side).strip() or None) if side is not None else None,
    )
    if opening.depth_m <= 0.0:
        raise StyleError("default_opening.depth_m must be > 0")
    if opening.profile not in profiles:
        raise StyleError(
            f"default_opening.profile {opening.profile!r} not in opening_profiles"
        )

    nd = data.get("niche") or {}
    if not isinstance(nd, dict):
        raise StyleError("niche must be an object")
    niche = StyleNiche(
        height_scale_m=float(nd.get("height_scale_m", 0.35)),
        pom=bool(nd.get("pom", True)),
    )

    ov = data.get("overlays") or {}
    if not isinstance(ov, dict):
        raise StyleError("overlays must be an object")
    overlays = StyleOverlays(
        seed=int(ov.get("seed", 0)),
        wetness=float(ov.get("wetness", 0.0)),
        moss=float(ov.get("moss", 0.0)),
        graffiti=float(ov.get("graffiti", 0.0)),
    )

    return StylePack(
        version=1,
        id=sid,
        wall_height_m=float(data.get("wall_height_m", 4.0)),
        bands=tuple(bands),
        opening_profiles=profiles,
        default_opening=opening,
        niche=niche,
        overlays=overlays,
        ceiling=_parse_ceiling(data.get("ceiling")),
        floor=_parse_surface(data.get("floor"), "floor"),
        loop_u=bool(data.get("loop_u", True)),
        path=p,
    )


def load_level_style(texture_dir: Path, style: str) -> StylePack:
    return load_style(style_json_path(texture_dir, style))
