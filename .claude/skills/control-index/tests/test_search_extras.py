from pathlib import Path

from conftest import CP60, HERE

LIMITS = HERE / "fixtures" / "limits.kml"


def names(out):
    return sorted(r["point_name"] for r in out["results"])


def test_job_search_returns_that_jobs_marks(search_args):
    out = search_args("--job", "2423-00519")
    assert out["query"] == {"job": "2423-00519"}
    assert names(out) == ["10"]
    assert out["results"][0]["distance_mi"] is None


def test_kml_limits_inside_points_are_distance_zero(search_args):
    out = search_args("--kml", LIMITS, "--radius", 0.0115)
    assert "kml" in out["query"]
    r200 = next(r for r in out["results"] if r["point_name"] == "200")  # inside the polygon
    assert r200["distance_mi"] == 0
    # 203 is ~0.009 mi west of the west edge, 204 ~0.014 mi
    assert "203" in names(out) and "204" not in names(out)


def test_kml_radius_measured_from_edge_not_centre(search_args):
    # CP60 is ~0.13 mi from the east edge, ~0.18 mi from the polygon centre
    assert "CP60" in names(search_args("--kml", LIMITS, "--radius", 0.15))


def group_with(out, point_name):
    return next(r for r in out["results"] if point_name in {s["point_name"] for s in r["sources"]})


def test_same_mark_in_two_files_collapses_with_all_sources(search_args):
    out = search_args(*CP60, "--radius", 0.05)
    g = group_with(out, "60R")
    assert g is group_with(out, "CP60")
    assert sorted((s["point_name"], Path(s["source_path"]).name) for s in g["sources"]) == [
        ("60R", "261111_UV_RH.jxl"), ("CP60", "261110-BD-MRC.jxl")]
    assert [r["point_name"] for r in out["results"]] == ["CP60"]


def test_different_marks_in_same_locator_cell_stay_separate(search_args):
    # CP 10 (MDT cap L5765) and 1R (Stahly RPC) share a ~10 m locator but are different marks
    out = search_args(*CP60, "--radius", 0.2)
    assert group_with(out, "10") is not group_with(out, "1R")


def test_ungrouped_result_lists_its_own_source(search_args):
    g = group_with(search_args("--job", "2423-00519"), "10")
    assert [s["source_path"] for s in g["sources"]] == [g["source_path"]]


def test_unparseable_files_listed_in_every_mode(search_args):
    for args in (("--job", "2071-07D26"), ("--kml", LIMITS)):
        assert [Path(b["source_path"]).name for b in search_args(*args)["unparsed_files"]] == ["corrupt.jxl"]


def test_coverage_in_every_mode(search_args):
    for args in (("--job", "2071-07D26"), ("--kml", LIMITS)):
        assert "folders_indexed" in search_args(*args)["coverage"]
