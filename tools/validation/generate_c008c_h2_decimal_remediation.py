"""Generate or verify bounded C-008C-H2 Decimal remediation evidence."""

from __future__ import annotations

import argparse
import hashlib
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/python"))

from msa.validation.remediation import (  # noqa: E402
    check_existing_decimal_remediation_evidence,
    write_decimal_remediation_evidence,
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-existing", action="store_true")
    args = parser.parse_args()
    path = (
        check_existing_decimal_remediation_evidence(ROOT)
        if args.check_existing
        else write_decimal_remediation_evidence(ROOT)
    )
    action = "checked existing" if args.check_existing else "wrote"
    print(
        f"{action}: {path.as_posix()} "
        f"sha256={hashlib.sha256(path.read_bytes()).hexdigest()}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
