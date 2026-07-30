"""Test-only recursive canonical re-signing for source-authority attacks."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from msa.validation.experiments.identity import digest, semantic_id


_IDENTITIES = {
    "baseline_id": "c008c-core-experiment-baseline-v1-",
    "dataset_case_id": "c008c-dataset-case-v1-",
    "dataset_manifest_id": "c008c-dataset-manifest-v1-",
    "axis_id": "c008c-parameter-axis-v1-",
    "variant_id": "c008c-experiment-variant-v1-",
    "ablation_id": "c008c-experiment-ablation-v1-",
    "increment_step_id": "c008c-increment-step-v1-",
    "gate_definition_id": "c008c-gate-definition-v1-",
    "experiment_plan_id": "c008c-experiment-plan-v1-",
    "protected_source_manifest_id": (
        "c008c-protected-source-manifest-v1-"
    ),
}


def _replace(values: list[str], mapping: dict[str, str]) -> list[str]:
    return [mapping.get(item, item) for item in values]


def _sign(payload: dict[str, Any], id_field: str) -> dict[str, Any]:
    payload[id_field] = semantic_id(
        _IDENTITIES[id_field],
        {key: value for key, value in payload.items() if key != id_field},
    )
    return payload


def resign_authority_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Recursively recompute every C-008C identity and dependent reference."""

    result = deepcopy(payload)
    if "dataset_case_id" in result:
        result["source_input_payload_digest"] = digest(result["source_input"])
    if "dataset_manifest_id" in result and "cases" in result:
        result["cases"] = [
            resign_authority_payload(item) for item in result["cases"]
        ]
    if "experiment_plan_id" in result:
        old_axes = [item["axis_id"] for item in result["axes"]]
        result["axes"] = [
            resign_authority_payload(item) for item in result["axes"]
        ]
        axis_map = {
            old: new["axis_id"]
            for old, new in zip(old_axes, result["axes"], strict=True)
        }
        for variant in result["variants"]:
            if variant["axis_id"] is not None:
                variant["axis_id"] = axis_map[variant["axis_id"]]
        old_variants = [item["variant_id"] for item in result["variants"]]
        result["variants"] = [
            resign_authority_payload(item) for item in result["variants"]
        ]
        variant_map = {
            old: new["variant_id"]
            for old, new in zip(
                old_variants, result["variants"], strict=True
            )
        }
        result["execution_scope_policy"]["variant_ids"] = _replace(
            result["execution_scope_policy"]["variant_ids"], variant_map
        )
        result["baseline_replay_policy"]["variant_ids"] = _replace(
            result["baseline_replay_policy"]["variant_ids"], variant_map
        )
        result["variant_replay_policy"]["variant_ids"] = _replace(
            result["variant_replay_policy"]["variant_ids"], variant_map
        )
        baseline_id = result["fixed_cutoff_policy"]["baseline_variant_id"]
        result["fixed_cutoff_policy"]["baseline_variant_id"] = (
            variant_map.get(baseline_id, baseline_id)
        )
        for field in (
            "ablations",
            "increment_steps",
            "gate_definitions",
        ):
            result[field] = [
                resign_authority_payload(item) for item in result[field]
            ]
    for id_field in (
        "experiment_plan_id",
        "dataset_manifest_id",
        "dataset_case_id",
        "gate_definition_id",
        "variant_id",
        "axis_id",
        "ablation_id",
        "increment_step_id",
        "protected_source_manifest_id",
        "baseline_id",
    ):
        if id_field in result:
            return _sign(result, id_field)
    return result


__all__ = ["resign_authority_payload"]
