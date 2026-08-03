from msa.validation.experiments.execution.rca.contracts import DifferenceKind
from msa.validation.experiments.execution.rca.payload_diff import payload_differences


def test_payload_diff_is_bounded_and_preserves_identity():
    total, stored = payload_differences(
        {"run_id": "a", "values": list(range(30))},
        {"run_id": "b", "values": list(reversed(range(30)))},
    )
    assert total > 20
    assert len(stored) == 20
    assert stored[0].path == "/run_id"


def test_payload_diff_distinguishes_order_and_type():
    _, ordered = payload_differences([1, 2], [2, 1])
    assert ordered[0].difference_kind is DifferenceKind.ORDER
    _, typed = payload_differences({"x": 1}, {"x": "1"})
    assert typed[0].difference_kind is DifferenceKind.TYPE
