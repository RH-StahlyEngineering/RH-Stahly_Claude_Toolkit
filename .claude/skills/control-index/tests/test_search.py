from conftest import CP60


def names(out):
    return [r["point_name"] for r in out["results"]]


def test_finds_mdt_cap_near_courthouse(search):
    out = search(*CP60)
    cp = next(r for r in out["results"] if r["point_name"] == "CP60")
    assert cp["kind"] == "control"
    assert cp["feature_code"] == "CP"
    assert cp["description"] == "MDT 2 IN. ACR 'CP 60'"
    assert cp["job_number"] == "2071-07D26"
    assert cp["source_path"].endswith("261110-BD-MRC.jxl")


def by_name(out, name):
    return next(r for r in out["results"] if r["point_name"] == name)


def test_default_radius_is_one_mile_and_excludes_far_job(search):
    out = search(*CP60)
    assert out["query"]["radius_mi"] == 1.0
    assert all(r["distance_mi"] <= 1.0 for r in out["results"])
    assert "2423-00519" not in {r["job_number"] for r in out["results"]}


def test_wider_radius_reaches_conrad_job(search):
    out = search(*CP60, "--radius", 30)
    far = [r for r in out["results"] if r["job_number"] == "2423-00519"]
    assert [r["point_name"] for r in far] == ["10"]
    assert 22 < far[0]["distance_mi"] < 24  # 48.17 vs 48.505 N, ~23 mi


def test_ranked_control_then_monument_then_distance(search):
    out = search(*CP60, "--all")
    kinds = [r["kind"] for r in out["results"]]
    assert kinds == sorted(kinds, key=["control", "monument", "other"].index)
    for k in ("control", "monument", "other"):
        d = [r["distance_mi"] for r in out["results"] if r["kind"] == k]
        assert d == sorted(d)
    assert kinds[0] == "control" and "other" in kinds


def test_other_points_hidden_unless_asked(search):
    assert "50018" not in names(search(*CP60))
    assert "50018" in names(search(*CP60, "--all"))


def test_bent_and_broken_marks_flagged_not_hidden(search):
    out = search(*CP60)
    assert by_name(out, "204")["flags"] == ["bent"]
    assert by_name(out, "204")["kind"] == "monument"
    assert by_name(out, "203")["flags"] == ["broken"]
    assert by_name(out, "200")["flags"] == []


def test_grid_only_point_located_from_job_projection(search):
    # 60R (UV job) is keyed-in grid only, same mark as CP60 (WGS84 stored in MRC job)
    out = search(*CP60)
    r = by_name(out, "60R")
    assert r["kind"] == "control"
    assert abs(r["locator"]["lat"] - 48.5051) < 0.0002
    assert abs(r["locator"]["lon"] - -111.8551) < 0.0003


def test_locator_rounded_and_labelled_no_survey_values(search):
    for r in search(*CP60, "--all")["results"]:
        loc = r["locator"]
        assert loc["label"] == "locator only"
        assert set(loc) == {"lat", "lon", "label"}
        assert round(loc["lat"], 4) == loc["lat"] and round(loc["lon"], 4) == loc["lon"]
        assert not {"north", "east", "elevation", "height"} & {k.lower() for k in r}


def test_unparseable_file_listed(search):
    bad = search(*CP60)["unparsed_files"]
    assert [b["source_path"].endswith("corrupt.jxl") for b in bad] == [True]


def test_tight_radius_keeps_only_the_mark_itself(search):
    # CP 10 is ~0.06 mi south of CP60
    assert sorted(names(search(*CP60, "--radius", 0.05, "--all"))) == ["60R", "CP60"]
