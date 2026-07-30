from msa.reference import core_alpha_v1_profile
from msa.validation import (
    StructuralMetricConfig,
    default_metric_formula_registry,
    default_metric_registry,
)
from msa.validation.experiments import (
    EXECUTION_BASE_COMMIT,
    core_experiment_baseline,
)


def test_baseline_uses_formal_profile_and_metric_registries() -> None:
    baseline = core_experiment_baseline()
    profile = core_alpha_v1_profile()
    assert baseline.execution_base_commit == EXECUTION_BASE_COMMIT
    assert baseline.core_reference_commit == profile.reference_commit_sha
    assert baseline.core_config_snapshot == profile.core_config
    assert baseline.metric_config_snapshot == StructuralMetricConfig()
    assert baseline.metric_definition_ids == tuple(
        item.metric_definition_id for item in default_metric_registry()
    )
    assert baseline.metric_formula_ids == tuple(
        item.metric_formula_id
        for item in default_metric_formula_registry()
    )
    assert type(baseline).from_dict(baseline.to_dict()) == baseline
