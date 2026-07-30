from msa.validation.experiments import (
    AblationSupportStatus,
    default_c008c_experiment_plan,
)


def test_ablation_registry_has_supported_and_unsupported_boundaries() -> None:
    ablations = default_c008c_experiment_plan().ablations
    supported = [
        item
        for item in ablations
        if item.support_status
        is AblationSupportStatus.SUPPORTED_BY_PUBLIC_CONFIG
    ]
    unsupported = [
        item
        for item in ablations
        if item.support_status
        is AblationSupportStatus.UNSUPPORTED_BY_PUBLIC_CONFIG
    ]
    assert [item.code for item in supported] == [
        "DEPENDENCY_REPEAT_NEUTRALIZED",
        "SOURCE_DIVERSITY_NEUTRALIZED",
        "CONTEXT_DIVERSITY_NEUTRALIZED",
        "ACTIVE_BOX_HYSTERESIS_NEUTRALIZED",
    ]
    assert {item.code for item in unsupported} == {
        "RESONANCE_CLUSTERING_ALGORITHM_REMOVAL",
        "LIFECYCLE_REMOVAL",
        "DIRECTION_ENGINE_REMOVAL",
        "ACTIVE_BOX_SELECTOR_REMOVAL",
    }
    assert all(item.core_config_snapshot is None for item in unsupported)
