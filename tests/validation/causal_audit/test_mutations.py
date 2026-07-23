import pytest

from .fixtures import auditor
from .mutations import MUTATIONS, mutation_report


@pytest.mark.parametrize(("name", "expected_code"), MUTATIONS)
def test_every_mutation_fails_with_expected_formal_code(
    name, expected_code
) -> None:
    report = mutation_report(name, auditor())
    assert not report.passed
    assert expected_code in {item.code for item in report.findings}
