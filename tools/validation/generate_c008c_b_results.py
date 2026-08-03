"""Generate, fully re-execute, or check existing C-008C-B evidence."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/python"))

from msa.validation.experiments.execution import (
    check_existing_c008c_b_evidence,
    write_c008c_b_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--check",
        action="store_true",
        help=(
            "fully re-execute the frozen B scope and byte-check committed "
            "evidence without modifying it (expensive)"
        ),
    )
    modes.add_argument(
        "--check-existing",
        action="store_true",
        help=(
            "strictly validate existing evidence contracts, identities, "
            "authority, schedules, OOS quarantine, derived consistency, and "
            "canonical bytes without re-executing B-stage outcomes"
        ),
    )
    args = parser.parse_args()
    if args.check_existing:
        paths = check_existing_c008c_b_evidence(ROOT)
        for path in paths:
            sha256 = hashlib.sha256(path.read_bytes()).hexdigest()
            print(f"checked existing: {path.as_posix()} sha256={sha256}")
        return 0
    paths = write_c008c_b_evidence(ROOT, check=args.check)
    action = "fully checked" if args.check else "wrote"
    for path in paths:
        print(f"{action}: {path.as_posix()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
