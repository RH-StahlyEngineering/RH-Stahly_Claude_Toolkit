"""CSV exports + ground-scaled projects. Fixture: real Shelby 'Converted to Ground' .vce (MT SPC 2SP,
scaled about CP1 by 1.0004209515) trimmed to points 1, 60, 50000; CSV in ground ift (TBC 'Export to CAD')."""
import json
import math
from pathlib import Path

import pytest

from conftest import HERE, run

TREE = HERE / "fixtures" / "ground_tree"
PT60 = (48.50505063, -111.85508541)  # truth: ground -> grid (about CP1) -> geodetic


@pytest.fixture(scope="module")
def db(tmp_path_factory):
    db = tmp_path_factory.mktemp("g") / "control.sqlite"
    run("index", TREE, "--db", db)
    return db


@pytest.fixture(scope="module")
def out(db):
    return json.loads(run("search", *PT60, "--db", db, "--all", "--radius", "50"))


def metres(a, b):
    return math.hypot((a[0] - b[0]) * 111320, (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0])))


def rows(out, src_end):
    return [r for r in out["results"] if r["source_path"].endswith(src_end)]


def test_csv_with_sibling_project_indexed_with_ground_correction(out):
    r = next(r for r in rows(out, "ground-export.csv") if r["point_name"] == "60")
    assert metres((r["locator"]["lat"], r["locator"]["lon"]), PT60) < 10
    assert r["feature_code"] == "CP" and r["kind"] == "control"
    assert "ground_scaled" in r["flags"]
    assert "Montana" in r["coord_system"]
    assert r["job_number"] == "2423-00519"


def test_grid_only_vce_point_projected_in_ground_scaled_2sp_system(out):
    r = next((r for r in rows(out, "shelby-ground.vce") if r["point_name"] == "50000"), None)
    assert r is not None
    assert "ground_scaled" in r["flags"]
    assert metres((r["locator"]["lat"], r["locator"]["lon"]), PT60) < 5000


def test_csv_without_sibling_coordinate_system_skipped_and_listed(out, db):
    assert not rows(out, "orphan.csv")
    assert out["skipped_total"] >= 1
    by_job = json.loads(run("search", "--job", "2423-00777", "--db", db))
    assert [s["source_path"].endswith("orphan.csv") for s in by_job["skipped_files"]] == [True]


def test_same_number_but_different_monument_type_stays_separate(tmp_path):
    import shutil
    tree = tmp_path / "t"
    shutil.copytree(TREE, tree)
    csv = next(tree.rglob("ground-export.csv"))
    # same point number, same spot as the MDT aluminum cap, but described as a Stahly RPC
    csv.with_name("rpc.csv").write_text("60,1559874.885,1397787.398,3478.21,CP /STAHLY RPC" + chr(10))
    db = tmp_path / "c.sqlite"
    run("index", tree, "--db", db)
    res = json.loads(run("search", *PT60, "--db", db, "--radius", "0.01"))["results"]
    groups = [sorted(Path(s["source_path"]).name for s in r["sources"]) for r in res
              if "60" in {s["point_name"] for s in r["sources"]}]
    assert ["rpc.csv"] in groups
    assert ["ground-export.csv"] in groups


def test_ground_scale_undone_about_project_origin_to_sub_metre():
    import sys
    sys.path.insert(0, str(HERE.parent / "scripts"))
    from vce import vce_grid
    grid, _ = vce_grid(next(TREE.rglob("shelby-ground.vce")))
    ft = 0.3048
    lat, lon = grid.to_latlon(1559874.885 * ft, 1397787.398 * ft)  # pt 60 ground ift
    assert metres((lat, lon), PT60) < 0.3
    lat, lon = grid.to_latlon(1559522.922 * ft, 1398329.542 * ft)  # CP1 = scaling origin
    assert metres((lat, lon), (48.50413113, -111.85280692)) < 0.3
