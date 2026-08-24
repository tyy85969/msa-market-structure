"""Prepare, preflight, execute, or outcome-free check C-008C-C Evidence."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/python"))
sys.path.insert(0, str(ROOT / "tools/validation"))

from c008c_c import (  # noqa: E402
    check_existing_c008c_c_evidence,
    prepare_c008c_c_execution_contract,
    run_c008c_c_locked_oos,
    validate_c008c_c_preflight,
)
from c008c_c.architecture import evidence_sha256  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--prepare-contract",
        action="store_true",
        help="write only the outcome-free execution contract",
    )
    modes.add_argument(
        "--preflight",
        action="store_true",
        help="validate committed architecture without entering seed-3 Core",
    )
    modes.add_argument(
        "--check-existing",
        action="store_true",
        help="validate existing canonical outcome without executing Core",
    )
    args = parser.parse_args(argv)
    if args.prepare_contract:
        path = prepare_c008c_c_execution_contract(ROOT)
        print(f"prepared: {path.as_posix()} sha256={evidence_sha256(path)}")
        return 0
    if args.preflight:
        contract = validate_c008c_c_preflight(ROOT)
        print(
            "preflight passed: "
            f"contract={contract['execution_contract_id']} "
            f"seed={contract['seed']} pairs={contract['oos_pair_count']}"
        )
        print("OOS formal execution count=0")
        return 0
    if args.check_existing:
        paths, report = check_existing_c008c_c_evidence(ROOT)
        for path in paths:
            print(
                f"checked existing: {path.as_posix()} "
                f"sha256={evidence_sha256(path)}"
            )
        print(
            f"decision={report['final_decision']} "
            f"freeze_eligible={report['freeze_eligible']}"
        )
        return 0
    attempt, report_path, report, elapsed = run_c008c_c_locked_oos(ROOT)
    print(f"wrote: {attempt.as_posix()} sha256={evidence_sha256(attempt)}")
    print(
        f"wrote: {report_path.as_posix()} "
        f"sha256={evidence_sha256(report_path)}"
    )
    print(f"run_report_id={report['run_report_id']}")
    print(
        f"decision={report['final_decision']} "
        f"freeze_eligible={report['freeze_eligible']}"
    )
    print(f"elapsed_seconds={elapsed:.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
