from pathlib import Path

import pytest

from msa.validation.experiments.execution.rca.manifest import (
    build_c008c_b_rca_manifest,
    load_b_sources,
)


ROOT = Path(__file__).resolve().parents[5]


@pytest.fixture(scope="session")
def rca_manifest():
    return build_c008c_b_rca_manifest(ROOT)


@pytest.fixture(scope="session")
def b_report():
    return load_b_sources(ROOT)[1]


@pytest.fixture(scope="session")
def b_sources():
    return load_b_sources(ROOT)
