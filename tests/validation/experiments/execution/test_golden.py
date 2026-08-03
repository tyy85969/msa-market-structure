from msa.validation.experiments.execution import (
    build_c008c_b_execution_manifest,
)


def test_execution_manifest_golden_identity() -> None:
    manifest = build_c008c_b_execution_manifest()
    assert manifest.execution_manifest_id == (
        "c008c-b-execution-manifest-v1-"
        "c113e9b5be160fd293a533a3f3eb115e606870b814b50a8029bb0f99788d1836"
    )
