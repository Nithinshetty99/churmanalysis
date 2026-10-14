import pytest

from churn_platform import simulate
from churn_platform.db import build_db, load_queries


@pytest.fixture(scope="session")
def sim():
    """A small simulation (600 customers) shared by all tests."""
    return simulate.simulate(simulate.SimConfig(n_customers=600, seed=7))


@pytest.fixture(scope="session")
def con(sim, tmp_path_factory):
    d = tmp_path_factory.mktemp("data")
    simulate.write_csvs(*sim, out_dir=d)
    return build_db(d, ":memory:")


@pytest.fixture(scope="session")
def queries():
    return load_queries()
