from copy import deepcopy

import pytest

from msa.research.msa_core import (
    MSACoreConfig,
    MSACoreRun,
    MSACoreSerializationError,
)

from .fixtures import batch_run, config


@pytest.mark.parametrize("contract_factory", [config, batch_run])
def test_contract_strict_round_trip(contract_factory) -> None:
    value = contract_factory()
    assert type(value).from_dict(value.to_dict()) == value


@pytest.mark.parametrize("contract_factory", [config, batch_run])
def test_unknown_field_is_rejected(contract_factory) -> None:
    value = contract_factory()
    payload = value.to_dict()
    payload["unknown"] = True
    with pytest.raises(MSACoreSerializationError):
        type(value).from_dict(payload)


@pytest.mark.parametrize("contract_factory", [config, batch_run])
def test_unknown_schema_is_rejected(contract_factory) -> None:
    value = contract_factory()
    payload = value.to_dict()
    payload["schema_version"] = 2
    with pytest.raises(MSACoreSerializationError):
        type(value).from_dict(payload)


def test_tuple_fields_serialize_to_ordered_lists() -> None:
    payload = batch_run().to_dict()
    assert isinstance(payload["processing_times"], list)
    assert isinstance(payload["frame_bundles"], list)
    assert isinstance(payload["report"]["assumptions"], list)


def test_naive_datetime_payload_is_rejected() -> None:
    payload = batch_run().to_dict()
    payload["processing_times"][0] = "2026-07-20T00:00:00"
    with pytest.raises(MSACoreSerializationError):
        MSACoreRun.from_dict(payload)


def test_non_string_id_payload_is_rejected() -> None:
    payload = deepcopy(batch_run().to_dict())
    payload["run_id"] = 7
    with pytest.raises(MSACoreSerializationError):
        MSACoreRun.from_dict(payload)


def test_config_nested_unknown_field_is_rejected() -> None:
    payload = config().to_dict()
    payload["frame_config"]["unknown"] = True
    with pytest.raises(MSACoreSerializationError):
        MSACoreConfig.from_dict(payload)
