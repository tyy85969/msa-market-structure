from decimal import ROUND_CEILING, localcontext

from msa.validation.experiments.execution import (
    build_c008c_b_execution_manifest,
)


def test_manifest_identity_is_decimal_context_independent() -> None:
    expected = build_c008c_b_execution_manifest().to_dict()
    with localcontext() as context:
        context.prec = 6
        context.rounding = ROUND_CEILING
        actual = build_c008c_b_execution_manifest().to_dict()
    assert actual == expected
