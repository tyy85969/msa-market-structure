from dataclasses import FrozenInstanceError, replace

import pytest

from msa.research.msa_core import (
    MSACoreConfig,
    MSACoreConfigurationError,
    MSACorePipeline,
)
from tests.research.active_box_contract.fixtures import config as active_config
from tests.research.resonance.fixtures import H4_PRIMARY, config as frame_config
from tests.research.resonance_scoring.fixtures import scoring_config

from .fixtures import config


def test_config_is_frozen_slotted_and_round_trips() -> None:
    value = config()
    assert not hasattr(value, "__dict__")
    with pytest.raises(FrozenInstanceError):
        value.engine_id = "changed"  # type: ignore[misc]
    assert MSACoreConfig.from_dict(value.to_dict()) == value


@pytest.mark.parametrize("field", ["engine_id", "engine_version", "policy_id"])
def test_config_requires_integration_identity(field: str) -> None:
    with pytest.raises(MSACoreConfigurationError):
        config(**{field: ""})


def test_config_rejects_strict_false() -> None:
    with pytest.raises(MSACoreConfigurationError):
        config(strict=False)


def test_config_rejects_non_config_children() -> None:
    for field in ("frame_config", "scoring_config", "active_box_config"):
        with pytest.raises(MSACoreConfigurationError):
            config(**{field: object()})


def test_config_rejects_symbol_conflict() -> None:
    with pytest.raises(MSACoreConfigurationError):
        config(active_box_config=active_config(symbol="EURUSD"))


def test_config_rejects_context_coverage_conflict() -> None:
    with pytest.raises(MSACoreConfigurationError):
        config(scoring_config=scoring_config(contexts=(H4_PRIMARY,)))


def test_config_rejects_tampered_child_config() -> None:
    child = frame_config()
    object.__setattr__(child, "strict", False)
    with pytest.raises(MSACoreConfigurationError):
        config(frame_config=child)


def test_pipeline_is_frozen_slotted_and_stateless() -> None:
    value = MSACorePipeline(config())
    assert not hasattr(value, "__dict__")
    assert tuple(value.__slots__) == ("config",)
    with pytest.raises(FrozenInstanceError):
        value.config = config()  # type: ignore[misc]


def test_direct_replace_revalidates_config() -> None:
    with pytest.raises(MSACoreConfigurationError):
        replace(config(), strict=False)
