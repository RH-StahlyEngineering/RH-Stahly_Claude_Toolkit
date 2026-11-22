"""Catch-up: skip unchanged folders, resume, budget, coverage, concurrent safety. CLI output only."""
import json
import shutil
import subprocess
import sys

import pytest

from conftest import CLI, CP60, TREE, run


def index(db, root, *extra):
    return json.loads(run("index", root, "--db", db, *extra))


def search(db, *extra):
    return json.loads(run("search", *CP60, "--db", db, "--all", *extra))


def keys(out):
    return sorted((r["source_path"], r["point_name"]) for r in out["results"])


@pytest.fixture
def tree(tmp_path):
    dst = tmp_path / "tree"
    shutil.copytree(TREE, dst)
    return dst


@pytest.fixture
def db(tmp_path):
    return tmp_path / "control.sqlite"


def test_unchanged_folders_not_reread_on_second_run(tree, db):
    first = index(db, tree)
    assert first["files_read"] > 0 and first["complete"] is True
    second = index(db, tree)
    assert second["files_read"] == 0
    assert second["folders_skipped"] == first["folders_read"] + first["folders_skipped"]


def test_new_file_in_folder_is_picked_up(tree, db):
    index(db, tree)
    src = next(tree.rglob("261110-BD-MRC.jxl"))
    shutil.copy(src, src.with_name("copy-MRC.jxl"))
    again = index(db, tree)
    assert again["files_read"] >= 1
    # copies group under one result: look in every result's sources
    assert any(s["source_path"].endswith("copy-MRC.jxl") for r in search(db)["results"] for s in r["sources"])


def test_deleted_file_records_removed(tree, db):
    index(db, tree)
    next(tree.rglob("261110-BD-MRC.jxl")).unlink()
    index(db, tree)
    assert not any(r["source_path"].endswith("261110-BD-MRC.jxl") for r in search(db)["results"])


def test_stopped_run_resumes_and_finishes(tree, db, tmp_path):
    full_db = tmp_path / "full.sqlite"
    index(full_db, tree)
    part = index(db, tree, "--max-files", 1)
    assert part["complete"] is False and part["files_read"] == 1
    assert search(db)["coverage"]["complete"] is False
    rest = index(db, tree)
    assert rest["complete"] is True
    assert keys(search(db)) == keys(search(full_db))
    assert search(db)["coverage"]["complete"] is True


def test_budget_stops_crawl_cleanly(tree, db):
    out = index(db, tree, "--budget", 0)
    assert out["complete"] is False and out["stopped"] == "budget"
    assert out["files_read"] == 0
    cov = search(db)["coverage"]
    assert cov["complete"] is False
    assert index(db, tree)["complete"] is True


def test_search_reports_coverage_counts(tree, db):
    index(db, tree, "--max-files", 1)
    cov = search(db)["coverage"]
    assert cov["folders_pending"] >= 1
    index(db, tree)
    cov = search(db)["coverage"]
    assert cov["folders_pending"] == 0 and cov["folders_indexed"] > 0
    assert cov["last_complete_run"]


def test_two_concurrent_runs_leave_valid_database(tree, db, tmp_path):
    full_db = tmp_path / "full.sqlite"
    index(full_db, tree)
    procs = [subprocess.Popen([sys.executable, str(CLI), "index", str(tree), "--db", str(db)],
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) for _ in range(2)]
    for p in procs:
        _, err = p.communicate(timeout=120)
        assert p.returncode == 0, err
    out = search(db)
    assert keys(out) == keys(search(full_db))
    assert len(keys(out)) == len(set(keys(out)))


def test_pending_counts_job_folders_not_yet_reached(tree, db):
    # fixture tree holds two jobs (Toole 2071-07D26, Conrad 2423-00519); a run stopped at once reached neither
    index(db, tree, "--budget", 0)
    assert search(db)["coverage"]["folders_pending"] >= 3  # the root it stopped in + both job folders
    shutil.rmtree(next(tree.rglob("-00519-*")))
    index(db, tree)
    assert search(db)["coverage"]["folders_pending"] == 0
