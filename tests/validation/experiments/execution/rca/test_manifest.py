from msa.validation.experiments.execution.rca.contracts import C008CBRCAManifest


def test_manifest_freezes_exact_bounded_schedule(rca_manifest):
    assert len(rca_manifest.diagnostic_pairs) == 40
    assert len(rca_manifest.cutoff_case_ids) == 15
    assert rca_manifest.same_context_runs_per_pair == 2
    assert rca_manifest.altered_decimal_runs_per_pair == 1
    assert all(item.seed != 3 and item.partition != "OOS" for item in rca_manifest.diagnostic_pairs)
    assert C008CBRCAManifest.from_dict(rca_manifest.to_dict()) == rca_manifest


def test_schedule_is_outcome_independent(rca_manifest):
    payload = rca_manifest.to_dict()
    text = str(payload).lower()
    assert "metric_value" not in text
    assert "winner" not in text and "best" not in text
    assert sum(x.selection_kind == "BASELINE_ALL_B" for x in rca_manifest.diagnostic_pairs) == 15
    assert sum(x.selection_kind == "VARIANT_FIRST_VALIDATION" for x in rca_manifest.diagnostic_pairs) == 25
