from copy import deepcopy
from pathlib import Path

import pytest

from msa.validation.experiments import (
    ExperimentEvidenceError,
    ExperimentValidationError,
    build_c008c_synthetic_dataset,
    build_protected_source_manifest,
    core_experiment_baseline,
    default_c008c_experiment_plan,
    write_c008c_authority_evidence,
)


def _contract_attack(number: int) -> None:
    if number <= 7:
        value = core_experiment_baseline()
        payload = deepcopy(value.to_dict())
        if number == 1:
            payload["execution_base_commit"] = "0" * 40
        elif number == 2:
            payload["core_reference_commit"] = "1" * 40
        elif number == 3:
            payload["core_profile_id"] = "forged-profile"
        elif number == 4:
            payload["core_config_payload_digest"] = "0" * 64
        elif number == 5:
            payload["metric_config_snapshot"]["atr_period"] = 15
        elif number == 6:
            payload["metric_definition_ids"].reverse()
        else:
            payload["metric_formula_ids"].pop()
    elif number <= 16:
        value = build_c008c_synthetic_dataset()
        payload = deepcopy(value.to_dict())
        cases = payload["cases"]
        if number == 8:
            cases[1] = deepcopy(cases[0])
        elif number == 9:
            cases[1]["source_input_payload_digest"] = cases[0][
                "source_input_payload_digest"
            ]
        elif number == 10:
            cases[0]["partition"] = "OOS"
        elif number == 11:
            del cases[:4]
        elif number == 12:
            payload["cases"] = [
                item for item in cases if item["partition"] != "OOS"
            ]
        elif number == 13:
            cases[0]["seed"] = 0.0
        elif number == 14:
            cases[4]["partition"] = "VALIDATION"
        elif number == 15:
            cases[0]["source_input"]["reference_price_data"][
                "source_config"
            ]["canonical_symbol"] = "FORGED"
        else:
            cases.reverse()
    elif number <= 28:
        value = default_c008c_experiment_plan()
        payload = deepcopy(value.to_dict())
        variants = payload["variants"]
        if number == 17:
            payload["variants"] = [
                item
                for item in variants
                if item["experiment_kind"] != "BASELINE"
            ]
        elif number == 18:
            variants.append(deepcopy(variants[0]))
        elif number == 19:
            payload["axes"][1]["axis_id"] = payload["axes"][0]["axis_id"]
        elif number == 20:
            variants[2]["variant_id"] = variants[1]["variant_id"]
        elif number == 21:
            variants[1]["changed_field_paths"].append(
                "metric_config.atr_period"
            )
        elif number == 22:
            payload["axes"][0]["values"].pop()
        elif number == 23:
            variants.pop(1)
        elif number == 24:
            payload["outcome"] = "forged"
        elif number == 25:
            payload["increment_steps"].reverse()
        elif number == 26:
            payload["increment_steps"][-1][
                "core_config_snapshot"
            ] = deepcopy(
                payload["increment_steps"][0]["core_config_snapshot"]
            )
        elif number == 27:
            payload["ablations"][4][
                "support_status"
            ] = "SUPPORTED_BY_PUBLIC_CONFIG"
        else:
            payload["gate_definitions"][0]["pass_rule"] = "changed later"
    else:
        value = build_protected_source_manifest()
        payload = deepcopy(value.to_dict())
        files = payload["files"]
        if number == 29:
            files.pop()
        elif number == 30:
            added = deepcopy(files[-1])
            added["relative_path"] = "src/python/msa/reference/extra.py"
            files.append(added)
        elif number == 31:
            files[0]["sha256"] = "0" * 64
        elif number == 32:
            files[0]["byte_size"] += 1
        elif number == 33:
            payload["execution_base_commit"] = "2" * 40
        elif number == 34:
            files[0]["relative_path"] = "C:/host/injection.py"
        else:
            files[0]["relative_path"] = files[0][
                "relative_path"
            ].replace("/", "\\")
    with pytest.raises(ExperimentValidationError):
        type(value).from_dict(payload)


@pytest.mark.parametrize("number", range(1, 36))
def test_thirty_five_contract_attacks_fail_closed(number: int) -> None:
    _contract_attack(number)


@pytest.mark.parametrize(
    ("number", "target", "missing"),
    [
        (36, "c008c_baseline_snapshot.json", True),
        (37, "c008c_dataset_manifest.json", False),
        (38, "c008c_experiment_plan.json", False),
        (39, "c008c_protected_source_manifest.json", False),
        (40, "c008c_baseline_snapshot.json", False),
    ],
)
def test_five_evidence_attacks_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
    number: int,
    target: str,
    missing: bool,
) -> None:
    original = Path.read_bytes

    def attacked(path: Path) -> bytes:
        if path.name == target and path.parent.name == "evidence":
            if missing:
                raise OSError("deliberately missing")
            return original(path) + f"attack-{number}".encode()
        return original(path)

    monkeypatch.setattr(Path, "read_bytes", attacked)
    with pytest.raises(ExperimentEvidenceError):
        write_c008c_authority_evidence(check=True)
