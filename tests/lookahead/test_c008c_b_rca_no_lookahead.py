from pathlib import Path

from msa.validation.experiments.execution.rca.manifest import build_c008c_b_rca_manifest


ROOT = Path(__file__).resolve().parents[2]


def test_rca_schedule_excludes_oos_and_seed_3():
    manifest = build_c008c_b_rca_manifest(ROOT)
    assert all(x.seed != 3 and x.partition != "OOS" for x in manifest.diagnostic_pairs)
    assert len(manifest.diagnostic_pairs) == 40


def test_rca_source_has_no_trading_or_selection_language():
    base = ROOT / "src/python/msa/validation/experiments/execution/rca"
    text = "\n".join(path.read_text(encoding="utf-8") for path in base.glob("*.py")).lower()
    for forbidden in ("profit", "winner", "recommendation_score", "take_profit", "stop_loss"):
        assert forbidden not in text
