"""Shared fixtures. The suite runs against the real dataset — no synthetic stand-in."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.config import get_settings          # noqa: E402
from app.ml.data import load_clean_panel     # noqa: E402
from app.ml.features import build_origin_features  # noqa: E402


@pytest.fixture(scope="session")
def settings():
    return get_settings()


@pytest.fixture(scope="session")
def loaded(settings):
    return load_clean_panel(settings.data_csv)


@pytest.fixture(scope="session")
def panel(loaded) -> pd.DataFrame:
    return loaded[0]


@pytest.fixture(scope="session")
def clean_report(loaded):
    return loaded[1]


@pytest.fixture(scope="session")
def schema(loaded):
    return loaded[2]


@pytest.fixture(scope="session")
def origin_df(panel) -> pd.DataFrame:
    return build_origin_features(panel)


@pytest.fixture(scope="session")
def raw_csv(settings) -> pd.DataFrame:
    return pd.read_csv(settings.data_csv)
