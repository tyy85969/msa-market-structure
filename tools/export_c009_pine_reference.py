"""Print the deterministic C-009 Pine reference fixture as canonical JSON."""

from __future__ import annotations

import json

from msa.migration import build_c009_pine_reference
from tests.research.msa_core.fixtures import pipeline, source_input


def main() -> None:
    value = build_c009_pine_reference(pipeline().run(source_input()))
    print(json.dumps(value, indent=2, sort_keys=True) + "\n", end="")


if __name__ == "__main__":
    main()
