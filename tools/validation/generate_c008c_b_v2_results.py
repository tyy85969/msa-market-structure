"""Generate, fully check, or check existing append-only C-008C-B-v2 Evidence."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/python"))

from msa.validation.experiments.execution import (  # noqa: E402
    b_v2_evidence_sha256,
    check_existing_c008c_b_v2_evidence,
    write_c008c_b_v2_evidence,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--check-existing",
        action="store_true",
        help=(
            "validate committed B-v2 Evidence without Core, Replay, or "
            "fixed-cutoff execution"
        ),
    )
    modes.add_argument(
        "--check",
        action="store_true",
        help=(
            "fully re-execute B-v2 and byte-check committed B-v2 Evidence"
        ),
    )
    args = parser.parse_args(argv)
    if args.check_existing:
        paths = check_existing_c008c_b_v2_evidence(ROOT)
        action = "checked existing"
    else:
        paths = write_c008c_b_v2_evidence(ROOT, check=args.check)
        action = "fully checked" if args.check else "wrote"
    for path in paths:
        print(
            f"{action}: {path.as_posix()} "
            f"sha256={b_v2_evidence_sha256(path)}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
