import json
from pathlib import Path

from msa.reference import core_alpha_v1_config, core_alpha_v1_profile
from tests.research.msa_core.fixtures import config


ROOT = Path(__file__).resolve().parents[2]
JSON_PATH = ROOT / "docs" / "reference" / "core_alpha_v1_config.json"


def test_authorized_fixture_factory_and_profile_payloads_are_exact() -> None:
    authorized = config().to_dict()
    assert authorized == core_alpha_v1_config().to_dict()
    assert authorized == core_alpha_v1_profile().core_config.to_dict()


def test_reviewable_json_is_the_exact_authorized_payload() -> None:
    authorized = config().to_dict()
    text = JSON_PATH.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert json.loads(text) == authorized
    assert (
        json.dumps(
            authorized,
            ensure_ascii=False,
            sort_keys=True,
            indent=2,
        )
        + "\n"
        == text
    )


def test_production_reference_package_does_not_import_tests() -> None:
    package = ROOT / "src" / "python" / "msa" / "reference"
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(package.glob("*.py"))
    )
    assert "from tests" not in source
    assert "import tests" not in source
