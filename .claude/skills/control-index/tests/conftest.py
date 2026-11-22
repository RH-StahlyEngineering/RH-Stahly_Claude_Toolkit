"""Seam: the control_index CLI. Tests run `index` on the fixture tree, then assert on `search` JSON only."""
import json
import subprocess
import sys
from pathlib import Path

import pytest

HERE = Path(__file__).parent
CLI = HERE.parent / "scripts" / "control_index.py"
TREE = HERE / "fixtures" / "tree"
CP60 = (48.505051, -111.855085)  # MDT 2" cap near Toole County courthouse, Shelby MT


def run(*args):
    p = subprocess.run([sys.executable, str(CLI), *map(str, args)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    return p.stdout


@pytest.fixture(scope="session")
def db(tmp_path_factory):
    path = tmp_path_factory.mktemp("idx") / "control.sqlite"
    run("index", TREE, "--db", path)
    return path


@pytest.fixture(scope="session")
def search(db):
    def _search(lat, lon, *extra):
        return json.loads(run("search", lat, lon, "--db", db, *extra))
    return _search


@pytest.fixture(scope="session")
def search_args(db):
    def _search(*args):
        return json.loads(run("search", *args, "--db", db))
    return _search
