from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from msa.migration import build_c009_pine_reference
from tests.research.msa_core.fixtures import pipeline, source_input


ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "docs" / "validation" / "evidence" / "c009_pine_reference_v1.json"


def test_c009_reference_fixture_is_deterministic() -> None:
    generated = build_c009_pine_reference(pipeline().run(source_input()))
    assert json.loads(FIXTURE.read_text(encoding="utf-8")) == generated


def test_c009_fixture_preserves_origin_confirm_divergence() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    structures = [item for frame in value["frames"] for item in frame["structures"]]
    assert any(item["origin_time"] != item["confirm_time"] for item in structures)


def test_c009_fixture_never_exposes_confirmed_state_before_confirm_time() -> None:
    value = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for frame in value["frames"]:
        as_of = datetime.fromisoformat(frame["as_of_time"])
        for structure in frame["structures"]:
            confirm = datetime.fromisoformat(structure["confirm_time"])
            if structure["tier"] == "CONFIRMED":
                assert confirm <= as_of
            assert datetime.fromisoformat(structure["state_confirm_time"]) <= as_of
