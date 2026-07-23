from msa.validation import default_metric_registry
from msa.validation.identity import digest

from .fixtures import (
    auditor,
    valid_prefix_pair,
    valid_run,
    valid_shared_asof_pair,
)
from .mutations import MUTATIONS, mutation_report
from .scenarios import all_descriptors


def test_report_ids_and_complete_digests_are_frozen() -> None:
    value = auditor()
    run = valid_run()
    single = value.audit_run(run)
    batch = value.compare_batch_replay(run, valid_run())
    prefix_run, extended_run = valid_prefix_pair()
    prefix = value.compare_prefix(prefix_run, extended_run)
    baseline, extended, cutoff = valid_shared_asof_pair()
    shared = value.compare_shared_asof(baseline, extended, cutoff)
    assert single.audit_report_id == (
        "causal-audit-report-v1-"
        "d89aad2947511fac190984eee5f01be2a3738cb32a9013ac278fbd72ba9fd277"
    )
    assert batch.audit_report_id == (
        "causal-audit-report-v1-"
        "1276c40fd84a197af63652408bddb9c751a06b7802f9b25abac4399aaf391b24"
    )
    assert prefix.audit_report_id == (
        "causal-audit-report-v1-"
        "32a40f3a4d99c81b5ff3860934f09ca35fbaf60fab2b5b98190a31ab15ed76d8"
    )
    assert shared.audit_report_id == (
        "causal-audit-report-v1-"
        "e5e64bbcc148947f4974d7ac3500f085ab3783303045cad3287b80e31bde1c92"
    )
    assert digest(single.to_dict()) == (
        "1207b1a51ba7043d42eda8491e7375dd65d29687b47dede74ef5a885910022d2"
    )
    assert digest(mutation_report("future_evidence", value).to_dict()) == (
        "ce455ffcdfb1383d9a31585b8c40923610e5048a2f67f9c2df7effbf2dd426df"
    )


def test_metric_and_scenario_definition_ids_are_frozen() -> None:
    assert tuple(
        item.metric_definition_id for item in default_metric_registry()
    ) == (
        "validation-metric-v1-041cef6a9c1e36e6f422a68a7ab24ef0738dbe2580cfb93079347dfc5641d1cb",
        "validation-metric-v1-de286cb387c6f96dd8ead648a20737aa43f67b4f3ca5cfca178467e16c88ead5",
        "validation-metric-v1-7111abfe8e81c05f07953430eb2bcbf89c335575ff936bcc569977dee27a521d",
        "validation-metric-v1-dff05913c77d2271475ecbd42159a9a12c033a9e770bb3545b5c8cc67ca0b028",
        "validation-metric-v1-594dacf0bb6fdf5227cb94e985728b9f97f6faf59b917a90d39604f9b9fa0074",
        "validation-metric-v1-caf03a1fd9db71d70c1cd724808973aa798c35b7734a49bf877d02e8cc7a0ab2",
        "validation-metric-v1-588b5c4a83daad40cb12dc1f6dfb95dde8a5b9d79e45c218bb99a24ac95a4931",
        "validation-metric-v1-5c4879d52e4923e0e5215ba21ca9a58eec4c05181f1dedf765f5f1be3fbc5e8c",
        "validation-metric-v1-66c5334e47b97eeb6c4f2711e26aff03aa85d566611cc2e4b14943f2773372f4",
        "validation-metric-v1-35ce7b3a308f7335453d3eafda6c40fd6b4fe7e20e0333f076a0af856dbbe1ce",
    )
    assert tuple(
        item.scenario_descriptor_id for item in all_descriptors()
    ) == (
        "synthetic-scenario-v1-73808867d4f880c3c219e6a02a1088b95c3296c4b76f6d452c458219cdbf0517",
        "synthetic-scenario-v1-311a7c8eae414a105a34ab4d63c3afe142e4580f649c8094665194398998fa11",
        "synthetic-scenario-v1-efc797d5ffb29fb2bfbf04b694466b3a158f0de580f22764af34ee658de4b01d",
        "synthetic-scenario-v1-ec9588b75c11fea97e9d04eae2234754e588660e1b6246d8883ef613242173e0",
        "synthetic-scenario-v1-ad44a9ec8f6df22479f5f94a13b4b73acccdd78bac7edf1ba14b0642cf921637",
    )


def test_mutation_finding_code_sequences_are_repeatable() -> None:
    value = auditor()
    first = {
        name: tuple(item.code for item in mutation_report(name, value).findings)
        for name, _ in MUTATIONS
    }
    second = {
        name: tuple(item.code for item in mutation_report(name, value).findings)
        for name, _ in MUTATIONS
    }
    assert first == second


def test_repeated_report_payloads_are_identical() -> None:
    value = auditor()
    run = valid_run()
    assert value.audit_run(run).to_dict() == value.audit_run(run).to_dict()
