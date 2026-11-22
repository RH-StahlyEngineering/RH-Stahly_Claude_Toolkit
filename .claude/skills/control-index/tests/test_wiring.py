"""Skill wiring: database path from config/env, catch-up exit contract, search JSON output contract."""
import json
import os
import subprocess
import sys

from conftest import CLI, CP60, TREE, run

SHARE_DB = r"\\Stahly\resource library\2 Department Resources\SURVEY_GIS\GIS Resources\Stahly Internal All Points GIS\Control_Index\control_index.sqlite"


def cli(*args, env=None):
    e = {k: v for k, v in os.environ.items() if k != "CONTROL_INDEX_DB"}
    e.update(env or {})
    return subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True, env=e)


def test_default_db_is_rhs_share_folder():
    p = cli("where-db")
    assert p.returncode == 0, p.stderr
    assert p.stdout.strip() == SHARE_DB


def test_env_overrides_config_and_flag_overrides_env(tmp_path):
    envdb = tmp_path / "env.sqlite"
    p = cli("index", TREE, env={"CONTROL_INDEX_DB": str(envdb)})
    assert p.returncode == 0, p.stderr
    assert envdb.exists()
    flagdb = tmp_path / "flag.sqlite"
    p = cli("search", *CP60, "--db", flagdb, env={"CONTROL_INDEX_DB": str(envdb)})
    assert json.loads(p.stdout)["results"] == []  # empty fresh flag db, not the env one


def test_catchup_stopped_by_budget_exits_zero_with_status(tmp_path):
    p = cli("index", TREE, "--db", tmp_path / "c.sqlite", "--budget", 0)
    assert p.returncode == 0, p.stderr
    out = json.loads(p.stdout)
    assert out["complete"] is False and out["stopped"] == "budget"


def test_search_output_contract(tmp_path):
    db = tmp_path / "c.sqlite"
    run("index", TREE, "--db", db)
    out = json.loads(run("search", *CP60, "--db", db))
    assert set(out) == {"query", "results", "unparsed_files", "skipped_files", "coverage"}
    r = out["results"][0]
    assert {"kind", "distance_mi", "point_name", "feature_code", "description", "recorded", "flags",
            "job_number", "source_path", "coord_system", "date", "locator", "sources"} <= set(r)
    assert {"folders_indexed", "folders_pending", "complete", "last_complete_run"} == set(out["coverage"])
    assert set(r["locator"]) == {"lat", "lon", "label"}
    assert {"source_path", "error"} == set(out["unparsed_files"][0])
