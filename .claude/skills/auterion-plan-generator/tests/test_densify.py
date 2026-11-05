"""Unit test: densify terminates when no waypoint chain reaches the segment end."""
import os, sys
import numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import camera_plan_set as cps


class FlatSite:
    def ground(self, x, y):
        return np.zeros(np.shape(x))


def test_densify_no_chain_falls_back_to_max_spacing(monkeypatch):
    # 10-80 m defaults always chain; a 50-55 m window cannot split 120 m -> no chain to the end
    monkeypatch.setattr(cps, "MIN_WP_SPACING_M", 50.0)
    monkeypatch.setattr(cps, "MAX_WP_SPACING_M", 55.0)
    pts = cps.densify(FlatSite(), (0.0, 0.0), (120.0, 0.0), 60.0)
    xs = [p[0] for p in pts]
    assert xs[0] == 0.0 and xs[-1] == 120.0
    assert max(b - a for a, b in zip(xs[:-1], xs[1:])) <= 55.0 + 1e-9
    assert all(p[2] == 60.0 for p in pts)
