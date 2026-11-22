"""TBC .vce projects indexed beside .jxl. Fixture: real MILK RIVER LCC .vce trimmed to points 60 and 204."""
import json

import pytest

from conftest import CP60, HERE, run

VCE_TREE = HERE / "fixtures" / "vce_tree"


@pytest.fixture(scope="module")
def out(tmp_path_factory):
    db = tmp_path_factory.mktemp("vce") / "control.sqlite"
    run("index", VCE_TREE, "--db", db)
    return json.loads(run("search", *CP60, "--db", db, "--all"))


def by_name(out, name):
    return next(r for r in out["results"] if r["point_name"] == name)


def test_geodetic_point_read_with_its_code(out):
    r = by_name(out, "204")  # Checkin 261110-BD-MRC.jxl: 48.504608, -111.860324
    assert r["recorded"] == "FND /1/2 IN. REBAR BENT OBS. VP"
    assert r["kind"] == "monument" and r["flags"] == ["bent"]
    lat, lon = r["locator"]["lat"], r["locator"]["lon"]
    assert abs(lat - 48.504608) * 111320 < 7.2 and abs(lon - -111.860324) * 111320 * 0.663 < 7.2
    assert r["source_path"].endswith("courthouse.vce")
    assert r["job_number"] == "2071-07D26"
    assert r["coord_system"] == "RMCRS / MILK RIVER"


def test_grid_only_point_projected_from_vce_coordinate_system(out):
    r = by_name(out, "60")  # same mark as CP60 (48.505051, -111.855085); code from latest non-check obs
    assert r["feature_code"] == "CP"
    assert r["description"] == "MDT 2 IN. ACR 'CP 60'"
    assert abs(r["locator"]["lat"] - CP60[0]) < 0.0002
    assert abs(r["locator"]["lon"] - CP60[1]) < 0.0003


def test_unreadable_vce_listed(out):
    assert [b["source_path"].endswith("corrupt.vce") for b in out["unparsed_files"]] == [True]
