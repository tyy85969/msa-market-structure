from msa.validation.experiments import (
    GateSeverity,
    default_c008c_gate_registry,
)


def test_gate_registry_freezes_definitions_not_results() -> None:
    gates = default_c008c_gate_registry()
    assert len(gates) == 27
    assert len({item.code for item in gates}) == 27
    assert all(item.severity is GateSeverity.HARD for item in gates)
    for gate in gates:
        payload = gate.to_dict()
        assert "result" not in payload
        assert "passed" not in payload
        assert type(gate).from_dict(payload) == gate
