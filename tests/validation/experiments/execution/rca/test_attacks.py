from dataclasses import replace

import pytest

from msa.validation.experiments.execution.rca.contracts import C008CBRCAManifest
from msa.validation.experiments.execution.rca.errors import C008CBRCAError
from msa.validation.experiments.execution.rca.manifest import validate_c008c_b_rca_manifest
from msa.validation.experiments.identity import digest, semantic_id


def test_unknown_field_and_forged_identity_are_rejected(rca_manifest):
    payload = rca_manifest.to_dict()
    payload["unknown"] = True
    with pytest.raises(C008CBRCAError):
        C008CBRCAManifest.from_dict(payload)
    with pytest.raises(C008CBRCAError):
        replace(rca_manifest, rca_manifest_id="forged")


def test_resigned_source_inconsistent_schedule_is_rejected(rca_manifest):
    payload = rca_manifest.to_dict()
    payload["cutoff_checkpoint_indices"] = [0] * 15
    payload["cutoff_schedule_digest"] = digest([
        {
            "dataset_case_id": case_id,
            "cutoff_as_of_time": cutoff,
            "checkpoint_index": 0,
            "selection_kind": kind,
        }
        for case_id, cutoff, kind in zip(
            payload["cutoff_case_ids"],
            payload["cutoff_as_of_times"],
            payload["cutoff_selection_kinds"],
            strict=True,
        )
    ])
    payload["rca_manifest_id"] = semantic_id(
        rca_manifest._PREFIX,
        {key: value for key, value in payload.items() if key != "rca_manifest_id"},
    )
    resigned = type(rca_manifest).from_dict(payload)
    with pytest.raises((C008CBRCAError, ValueError)):
        validate_c008c_b_rca_manifest(resigned)
