import hashlib
from pathlib import Path

from msa.validation.experiments import (
    build_c008c_synthetic_dataset,
    build_protected_source_manifest,
    core_experiment_baseline,
    default_c008c_experiment_plan,
)
from msa.validation.experiments.identity import digest


ROOT = Path(__file__).resolve().parents[3]


def test_c008c_authority_goldens() -> None:
    baseline = core_experiment_baseline()
    dataset = build_c008c_synthetic_dataset()
    plan = default_c008c_experiment_plan()
    protected = build_protected_source_manifest()
    assert baseline.baseline_id == (
        "c008c-core-experiment-baseline-v1-"
        "3b135b1843debedb2709811369a92ee0be729e9d2f04c510c5a0f9ca471983de"
    )
    assert baseline.core_config_payload_digest == (
        "992f9ab6b04384c69cb1f3a68d49a51480e2d67b579254ab9ce58677ac168a14"
    )
    assert baseline.metric_config_payload_digest == (
        "4b1071fc4727cabeb8dc7ba9a51b5b657384d09a1148cf645683af98591d5088"
    )
    assert digest([item.axis_id for item in plan.axes]) == (
        "5e7d3399a5a1b158c33694cfdb5bad20a77a05c48b418150a52c8a05f58e4c71"
    )
    assert digest([item.variant_id for item in plan.variants]) == (
        "134e89bad0481077e5b9aa9dd0650f57f8a75f4cd4e4524a13b0e9c8b09a2510"
    )
    assert digest([item.ablation_id for item in plan.ablations]) == (
        "56b2daed98c86da60295dab807921285ecdfd4150934447ae2d6f70d5e391c2a"
    )
    assert digest(
        [item.increment_step_id for item in plan.increment_steps]
    ) == "4417a630d6e798858d2f7b0d19db92f1bd5cafa82a56ae81b03255a168e99abb"
    assert digest([item.dataset_case_id for item in dataset.cases]) == (
        "6161e00ef6752cfb69288a5073c7c5b94053aab8adc489357c1190938a954a2f"
    )
    assert digest(
        [item.gate_definition_id for item in plan.gate_definitions]
    ) == "20d76739fa7c3fb40e4679da30725126013acbf9754e5d13dd8c5b6d6604e83d"
    assert digest(plan.execution_scope_policy.to_dict()) == (
        "7ca6eae71e48824c4535072555dab59e5e56c443f8896bdd99425acab1e60e6c"
    )
    assert digest(plan.baseline_replay_policy.to_dict()) == (
        "fb95bf4f6552db8c57b07d0f8aa559b84e1bc3bafd76472840c9ccc5a1f72c1d"
    )
    assert digest(plan.variant_replay_policy.to_dict()) == (
        "02b002dcb0d595487d5f5c3d5e264b895a98daa71d2be6ba14b34f1c0d843491"
    )
    assert digest(plan.fixed_cutoff_policy.to_dict()) == (
        "fb34e5714c2d80c9e5a64b2e34178b4db5201f57dd142b72da691de6d7aec353"
    )
    gates = {item.code: item for item in plan.gate_definitions}
    assert digest(
        [
            item.to_dict()
            for item in gates[
                "OOS_SAMPLE_COVERAGE"
            ].policy.sample_coverage_rules
        ]
    ) == "131317a5e9a0aaa3e3f6201953aae403b23cd3ca1bc3b3a837e235817c702e47"
    assert digest(
        [
            item.to_dict()
            for item in gates[
                "NO_NEIGHBORHOOD_DEGENERATION"
            ].policy.degeneration_rules
        ]
    ) == "1280b1f872e36cdafcd65c7e20effe2c3447bb267e0ec999be3e2bd1f5b20521"
    assert dataset.dataset_manifest_id == (
        "c008c-dataset-manifest-v1-"
        "5ae72c0d36c37be670c9a7c1e3f2c6e048ef9e92277eaf02e458b6a7ca6f817a"
    )
    assert plan.experiment_plan_id == (
        "c008c-experiment-plan-v1-"
        "619005d8808d6664a5b36d7968635f78fc75f32cd23b0e7cb6169c34c4d70b68"
    )
    assert protected.protected_source_manifest_id == (
        "c008c-protected-source-manifest-v1-"
        "cea251f4dad8d2c4a015ecc9f3c1a6d881af6971ccab382c1d486aad1fc04704"
    )


def test_evidence_file_sha256_goldens() -> None:
    expected = {
        "c008c_baseline_snapshot.json": (
            "9b141b4f7614bbd14c76f25c3f6271c7a1db913968d2f4072b8ca6980d9fb7cf"
        ),
        "c008c_dataset_manifest.json": (
            "612c0f89bea1f78900a85e41508635818132eea5ebf7b4e9598c5e7963956a0d"
        ),
        "c008c_experiment_plan.json": (
            "1e00ab471410f724611924d82fd2af2881e5b9a76cb1518e178212f189faa80f"
        ),
        "c008c_protected_source_manifest.json": (
            "4b8dba41d5250d530a981b4afedb989407765ac94b0ddc5561bb244760dd950b"
        ),
    }
    for name, value in expected.items():
        assert hashlib.sha256(
            (ROOT / "docs/validation/evidence" / name).read_bytes()
        ).hexdigest() == value
