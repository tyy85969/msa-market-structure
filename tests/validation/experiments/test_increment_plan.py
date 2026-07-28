from msa.reference import core_alpha_v1_config
from msa.validation.experiments import default_c008c_experiment_plan


def test_increment_ladder_is_fixed_and_ends_at_baseline() -> None:
    steps = default_c008c_experiment_plan().increment_steps
    assert [item.step_index for item in steps] == [0, 1, 2, 3, 4]
    assert [item.restored_contribution for item in steps] == [
        "NONE_ALL_NEUTRALIZED",
        "DEPENDENCY_REPEAT",
        "SOURCE_DIVERSITY",
        "CONTEXT_DIVERSITY",
        "ACTIVE_BOX_HYSTERESIS",
    ]
    assert steps[-1].core_config_snapshot == core_alpha_v1_config()
