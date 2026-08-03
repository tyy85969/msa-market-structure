"""Generate once or verify existing bounded C-008C-B RCA evidence."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/python"))

from msa.validation.experiments.execution.rca import (
    check_existing_c008c_b_rca_evidence,
    write_c008c_b_rca_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-existing", action="store_true")
    args = parser.parse_args()
    paths = (
        check_existing_c008c_b_rca_evidence(ROOT)
        if args.check_existing
        else write_c008c_b_rca_evidence(ROOT)
    )
    for path in paths:
        print(f"{'checked existing' if args.check_existing else 'wrote'}: {path.as_posix()} sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
