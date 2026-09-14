import math

from passages_tool.renderer.occlusion import (
    sample_grid_points,
    occlusion_coverage,
)


# ── sample grid geometry ──────────────────────────────────────────────────────

def test_grid_count_and_extent():
    eye = (0.0, 0.0, 1.7)
    pts = sample_grid_points(eye, (0.0, 5.0), z_offset=0.0, radius=0.5,
                             height=2.0, n_wide=3, n_tall=4)
    assert len(pts) == 12

    # Anchor is straight ahead in +Y, so the width axis is world X.
    xs = sorted({round(p[0], 6) for p in pts})
    zs = sorted({round(p[2], 6) for p in pts})
    # Width samples inset within [-radius, +radius].
    assert min(xs) > -0.5 and max(xs) < 0.5
    assert abs(min(xs) + max(xs)) < 1e-9          # symmetric about the anchor
    # Height samples inset within [0, height].
    assert min(zs) > 0.0 and max(zs) < 2.0
    # All samples share the anchor's Y (rectangle ⊥ to eye→anchor).
    assert all(abs(p[1] - 5.0) < 1e-9 for p in pts)


def test_grid_perpendicular_to_view():
    # Anchor off to the side: width axis must rotate to stay ⊥ to eye→anchor.
    eye = (0.0, 0.0, 1.7)
    pts = sample_grid_points(eye, (5.0, 5.0), z_offset=0.0, radius=1.0,
                             height=1.0, n_wide=2, n_tall=1)
    # eye→anchor dir is (1,1)/√2; perpendicular is (-1,1)/√2. The two width
    # samples should straddle the anchor along that perpendicular.
    (x0, y0, _), (x1, y1, _) = pts
    mx, my = (x0 + x1) / 2, (y0 + y1) / 2
    assert abs(mx - 5.0) < 1e-9 and abs(my - 5.0) < 1e-9   # centred on anchor
    span = (x1 - x0, y1 - y0)
    view = (1.0, 1.0)
    assert abs(span[0] * view[0] + span[1] * view[1]) < 1e-9  # ⊥ to view


# ── coverage fraction ─────────────────────────────────────────────────────────

def test_fully_visible():
    eye = (0.0, 0.0, 1.7)
    pts = sample_grid_points(eye, (0.0, 5.0), 0.0, 0.5, 2.0)
    cov = occlusion_coverage(eye, pts, lambda p: math.inf)
    assert cov == 1.0


def test_fully_occluded():
    eye = (0.0, 0.0, 1.7)
    pts = sample_grid_points(eye, (0.0, 5.0), 0.0, 0.5, 2.0)
    cov = occlusion_coverage(eye, pts, lambda p: 0.5)   # wall right in front
    assert cov == 0.0


def test_half_occluded_lower_rows():
    # A low wall (z below ~1.0) blocks only the bottom half of the extent.
    eye = (0.0, 0.0, 1.7)
    pts = sample_grid_points(eye, (0.0, 5.0), 0.0, 0.5, 2.0, n_wide=2, n_tall=4)

    def sampler(p):
        return 1.0 if p[2] < 1.0 else math.inf   # occlude only low samples

    cov = occlusion_coverage(eye, pts, sampler)
    assert abs(cov - 0.5) < 1e-9


def test_cutout_hole_passes():
    # Emulate an arch: a solid frame occludes edge columns, the open span (centre
    # column) lets the anchor through. Bottom rows still visible etc.
    eye = (0.0, 0.0, 1.7)
    pts = sample_grid_points(eye, (0.0, 5.0), 0.0, 1.0, 2.0, n_wide=3, n_tall=1)

    def sampler(p):
        # centre column (x≈0) is the arch opening → unobstructed
        return math.inf if abs(p[0]) < 0.1 else 1.0

    cov = occlusion_coverage(eye, pts, sampler)
    assert abs(cov - (1.0 / 3.0)) < 1e-9


def test_bias_absorbs_resting_surface():
    # Occluder sits a hair in front of the sample (the surface the anchor rests
    # against). Within bias → still counts visible.
    eye = (0.0, 0.0, 0.0)
    p = (0.0, 5.0, 0.0)
    d = 5.0
    assert occlusion_coverage(eye, [p], lambda q: d - 0.02, bias=0.05) == 1.0
    assert occlusion_coverage(eye, [p], lambda q: d - 0.20, bias=0.05) == 0.0


def test_empty_points():
    assert occlusion_coverage((0, 0, 0), [], lambda p: math.inf) == 0.0
