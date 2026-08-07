import hashlib
import json
from pathlib import Path

from msa.validation.experiments import (
    ProtectedSourceManifest,
    build_c008c_synthetic_dataset,
    build_protected_source_manifest,
    core_experiment_baseline,
    default_c008c_experiment_plan,
)
from msa.validation.experiments.identity import digest
from msa.validation.remediation import (
    validate_historical_protected_source_transition,
)


ROOT = Path(__file__).resolve().parents[3]
HISTORICAL_PROTECTED_MANIFEST_PATH = (
    ROOT / "docs/validation/evidence/c008c_protected_source_manifest.json"
)
HISTORICAL_PROTECTED_MANIFEST_ID = (
    "c008c-protected-source-manifest-v1-"
    "f93cda3d0966ee1340addebe36e8c008591d94d19d966828471721a18fdf2356"
)
POST_H2_ADDED_PATH = (
    "src/python/msa/research/resonance/decimal_arithmetic.py"
)


def _historical_protected_manifest() -> ProtectedSourceManifest:
    return ProtectedSourceManifest.from_dict(
        json.loads(
            HISTORICAL_PROTECTED_MANIFEST_PATH.read_text(encoding="utf-8")
        )
    )


def test_c008c_authority_goldens() -> None:
    baseline = core_experiment_baseline()
    dataset = build_c008c_synthetic_dataset()
    plan = default_c008c_experiment_plan()
    current_protected = build_protected_source_manifest()
    historical_protected = _historical_protected_manifest()
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
        "38a038f7cb4f71bf65e7f2ec58e38766b75fa2427918b47f0224e22a3c84fe55"
    )
    assert digest(dataset.capacity_policy.to_dict()) == (
        "0c51d47b6af1697b6d2aec9794670b485f67713bfc92320ca7071804b82cfbc8"
    )
    assert digest(
        [item.gate_definition_id for item in plan.gate_definitions]
    ) == "20d76739fa7c3fb40e4679da30725126013acbf9754e5d13dd8c5b6d6604e83d"
    assert digest(plan.execution_scope_policy.to_dict()) == (
        "3a1e0bb3aa6fb92eff7c6683838cd19c2f58d40bff2dabb94290c1cf1c30bb4a"
    )
    assert digest(plan.baseline_replay_policy.to_dict()) == (
        "e62f0b7613184e6f7d189adacb771cec7e568d9d90a427d29f3faf64c242198b"
    )
    assert digest(plan.variant_replay_policy.to_dict()) == (
        "9655ef68dbb73b14e884b1e44f93659721c376bc0d75b5a3a685e1322a403184"
    )
    assert digest(plan.fixed_cutoff_policy.to_dict()) == (
        "58d32c64f784a957d7ab3a86ae62237002b94f6de995744409b52f216abc4504"
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
        "a5ccee417d80899d3af0d6d84168f29f6aef92712f4cddfc673ff4451520c548"
    )
    assert plan.experiment_plan_id == (
        "c008c-experiment-plan-v1-"
        "fb38f9cc47d2d4396fa9ad26b74c3e821d07fca6e926e40bc319e819bda611b5"
    )
    assert len(historical_protected.files) == 77
    assert (
        historical_protected.protected_source_manifest_id
        == HISTORICAL_PROTECTED_MANIFEST_ID
    )
    historical_paths = {
        item.relative_path for item in historical_protected.files
    }
    current_paths = {
        item.relative_path for item in current_protected.files
    }
    assert current_paths == historical_paths | {POST_H2_ADDED_PATH}
    assert len(current_paths) == len(historical_paths) + 1
    validate_historical_protected_source_transition(
        historical_protected, ROOT
    )


def test_evidence_file_sha256_goldens() -> None:
    expected = {
        "c008c_baseline_snapshot.json": (
            "9b141b4f7614bbd14c76f25c3f6271c7a1db913968d2f4072b8ca6980d9fb7cf"
        ),
        "c008c_dataset_manifest.json": (
            "76f3f4f5da8b92aa6c3306c33c593092d32aa5ef5160e493e7fc7234613fbd32"
        ),
        "c008c_experiment_plan.json": (
            "262f9f3bd9a38b7c28699026391ae45ff096efe916faf9c44c46cd9d8e12535c"
        ),
        "c008c_protected_source_manifest.json": (
            "a4651a946ddc3731d35953e01d2018874672504a48eba74e87819ffb47d649a7"
        ),
    }
    for name, value in expected.items():
        assert hashlib.sha256(
            (ROOT / "docs/validation/evidence" / name).read_bytes()
        ).hexdigest() == value
