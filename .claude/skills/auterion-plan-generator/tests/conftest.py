"""Seam tests record failures with check() into a module-level FAILS list; fail the pytest test when any did."""
import pytest


@pytest.fixture(autouse=True)
def _check_fails(request):
    fails = getattr(request.module, "FAILS", None)
    n0 = len(fails) if fails is not None else 0
    yield
    if fails is not None and len(fails) > n0:
        pytest.fail("check() failures: " + "; ".join(fails[n0:]))
