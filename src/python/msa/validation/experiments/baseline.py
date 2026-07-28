"""Authority-bound Core and metric baseline for C-008C."""

from __future__ import annotations

from msa.reference import (
    core_alpha_v1_profile,
    validate_core_alpha_v1_config,
    validate_core_alpha_v1_profile,
)
from msa.validation.metric_registry import default_metric_registry
from msa.validation.metrics.contracts import StructuralMetricConfig
from msa.validation.metrics.formula_registry import (
    default_metric_formula_registry,
)

from .contracts import (
    EXECUTION_BASE_COMMIT,
    CoreExperimentBaseline,
)
from .identity import digest, semantic_id


_ASSUMPTIONS = (
    "Parameters have not been optimized for XAUUSD",
    "The baseline is a semantic reference",
    "Active Box is a structural research object not a trading signal",
    "C-008C studies structural robustness only",
    "The baseline does not establish profitability or production readiness",
)
_PROVENANCE = (
    "Core authority is msa.reference.core_alpha_v1_profile",
    "Core config is read from the validated Profile",
    "Metric config is the formal StructuralMetricConfig default",
    "Metric definition and formula order comes from formal registries",
    "No tests fixture supplies production authority",
)


def core_experiment_baseline() -> CoreExperimentBaseline:
    profile = validate_core_alpha_v1_profile(core_alpha_v1_profile())
    config = validate_core_alpha_v1_config(profile.core_config)
    metric_config = StructuralMetricConfig()
    definition_ids = tuple(
        item.metric_definition_id for item in default_metric_registry()
    )
    formula_ids = tuple(
        item.metric_formula_id for item in default_metric_formula_registry()
    )
    payload = {
        "execution_base_commit": EXECUTION_BASE_COMMIT,
        "core_reference_commit": profile.reference_commit_sha,
        "core_profile_semantic_id": profile.profile_semantic_id,
        "core_profile_id": profile.profile_id,
        "core_profile_version": profile.profile_version,
        "core_config_payload_digest": digest(config.to_dict()),
        "core_config_snapshot": config.to_dict(),
        "metric_config_payload_digest": digest(metric_config.to_dict()),
        "metric_config_snapshot": metric_config.to_dict(),
        "metric_definition_ids": list(definition_ids),
        "metric_formula_ids": list(formula_ids),
        "assumptions": list(_ASSUMPTIONS),
        "provenance": list(_PROVENANCE),
        "schema_version": 1,
    }
    return CoreExperimentBaseline(
        baseline_id=semantic_id(
            "c008c-core-experiment-baseline-v1-", payload
        ),
        execution_base_commit=EXECUTION_BASE_COMMIT,
        core_reference_commit=profile.reference_commit_sha,
        core_profile_semantic_id=profile.profile_semantic_id,
        core_profile_id=profile.profile_id,
        core_profile_version=profile.profile_version,
        core_config_payload_digest=digest(config.to_dict()),
        core_config_snapshot=config,
        metric_config_payload_digest=digest(metric_config.to_dict()),
        metric_config_snapshot=metric_config,
        metric_definition_ids=definition_ids,
        metric_formula_ids=formula_ids,
        assumptions=_ASSUMPTIONS,
        provenance=_PROVENANCE,
    )
