from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PINE = ROOT / "src" / "pine" / "msa_v1.pine"


def test_pine_candidate_has_indicator_and_causal_mtf_contract() -> None:
    source = PINE.read_text(encoding="utf-8")
    assert source.startswith("//@version=6")
    assert "indicator(" in source
    assert "strategy." not in source
    assert "lookahead = barmerge.lookahead_on" in source
    assert "gaps = barmerge.gaps_on" in source
    assert "ta.pivothigh(high, pivotLeft, pivotRight)[1]" in source
    assert "OriginTime" in source and "ConfirmTime" in source and "AsOfTime" in source


def test_pine_candidate_has_bounded_objects_and_array_guards() -> None:
    source = PINE.read_text(encoding="utf-8")
    assert "maxStructures" in source and "maxZones" in source and "maxBoxes" in source
    assert "array.size(structures) > 0" in source
    assert "array.size(historicalZones) >= maxZones" in source
    assert "array.size(frozenBoxes) >= maxBoxes" in source
    assert "TODO" not in source
