"""Unit test: plan_outputs.save_set supersedes the whole set (incl. QA PNG, 3D HTML, report) and only that set."""
import datetime, os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "scripts"))
import plan_outputs

SET = ["TooleCH_nadir90.plan", "TooleCH_oblA45_2.plan", "TooleCH_orbit_r40_h30_p30.plan", "TooleCH_flights.csv",
       "TooleCH_walls_QA.png", "TooleCH_3D.html", "TooleCH_report.json"]


def test_supersedes_whole_set_only(tmp_path):
    src, dst = tmp_path / "src", tmp_path / "dst"
    src.mkdir(); dst.mkdir()
    for f in SET:
        (src / f).write_text("new"); (dst / f).write_text("old")
    other = ["TooleCH_B_nadir90.plan", "TooleCH_notes.txt", "TooleCHX_nadir90.plan"]   # another set / user files
    for f in other:
        (dst / f).write_text("keep")
    sup = plan_outputs.save_set(str(src), SET, "TooleCH", [str(dst)], "rerun", datetime.date(2026, 1, 2))[str(dst)]
    assert sorted(os.listdir(sup)) == sorted(SET)
    assert all((dst / f).read_text() == "new" for f in SET)
    assert all((dst / f).read_text() == "keep" for f in other)
