from __future__ import annotations

from pathlib import Path

import generate_c008c_c_results as cli


def _must_not_execute(*args: object, **kwargs: object) -> object:
    raise AssertionError("outcome-free CLI mode entered formal execution")


def test_preflight_mode_cannot_execute_outcome(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "run_c008c_c_locked_oos", _must_not_execute)
    monkeypatch.setattr(
        cli,
        "validate_c008c_c_preflight",
        lambda root: {
            "execution_contract_id": "contract-id",
            "seed": 3,
            "oos_pair_count": 130,
        },
    )
    assert cli.main(["--preflight"]) == 0
    assert "OOS formal execution count=0" in capsys.readouterr().out


def test_check_existing_mode_cannot_execute_outcome(monkeypatch, capsys) -> None:
    monkeypatch.setattr(cli, "run_c008c_c_locked_oos", _must_not_execute)
    monkeypatch.setattr(
        cli,
        "check_existing_c008c_c_evidence",
        lambda root: (
            (Path("contract"), Path("attempt"), Path("report")),
            {"final_decision": "BLOCKED", "freeze_eligible": False},
        ),
    )
    monkeypatch.setattr(cli, "evidence_sha256", lambda path: "0" * 64)
    assert cli.main(["--check-existing"]) == 0
    output = capsys.readouterr().out
    assert "checked existing" in output
    assert "decision=BLOCKED freeze_eligible=False" in output
