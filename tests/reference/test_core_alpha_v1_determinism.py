import os
import subprocess
import sys
from decimal import ROUND_DOWN, getcontext
from pathlib import Path

from msa.reference import core_alpha_v1_profile


ROOT = Path(__file__).resolve().parents[2]


def test_global_decimal_context_and_working_directory_do_not_change_payload(
    tmp_path: Path,
    monkeypatch,
) -> None:
    baseline = core_alpha_v1_profile().to_dict()
    context = getcontext()
    old_precision = context.prec
    old_rounding = context.rounding
    try:
        context.prec = 6
        context.rounding = ROUND_DOWN
        monkeypatch.chdir(tmp_path)
        assert core_alpha_v1_profile().to_dict() == baseline
    finally:
        context.prec = old_precision
        context.rounding = old_rounding


def test_python_hash_seed_does_not_change_payload() -> None:
    code = (
        "from msa.reference import core_alpha_v1_profile;"
        "from msa.reference.identity import canonical_json;"
        "print(canonical_json(core_alpha_v1_profile().to_dict()))"
    )
    outputs = []
    for seed in ("1", "8675309"):
        environment = os.environ.copy()
        environment["PYTHONHASHSEED"] = seed
        environment["PYTHONPATH"] = str(ROOT / "src" / "python")
        outputs.append(
            subprocess.check_output(
                [sys.executable, "-B", "-c", code],
                cwd=ROOT,
                env=environment,
                text=True,
            )
        )
    assert outputs[0] == outputs[1]


def test_repeated_factories_have_identical_complete_payloads() -> None:
    assert core_alpha_v1_profile().to_dict() == (
        core_alpha_v1_profile().to_dict()
    )
