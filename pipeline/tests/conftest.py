from __future__ import annotations

import pandas as pd
import pytest

from pitchiq.config import load_leagues, load_settings
from pitchiq.ingest.run import Ingestor
from pitchiq.storage.parquet import Store
from tests.fakeworld import TODAY, FakeHTTP, World, shrink_config


@pytest.fixture(scope="session")
def world() -> World:
    return World().build()


@pytest.fixture(scope="session")
def cfg():
    return shrink_config(load_settings(), load_leagues())


@pytest.fixture(scope="session")
def ingested(tmp_path_factory, world, cfg):
    """A store populated by a full ingest + build of the synthetic world."""
    from pitchiq.build import build_core

    settings, leagues = cfg
    root = tmp_path_factory.mktemp("data")
    store = Store(root)
    clients = {
        src: FakeHTTP(src, world, store.raw) for src in ("understat", "football_data", "clubelo")
    }
    ingestor = Ingestor(
        store, settings, leagues, clients=clients, now=pd.Timestamp(TODAY, tz="UTC")
    )
    result = ingestor.run()
    build_core(store)
    return store, result, clients
