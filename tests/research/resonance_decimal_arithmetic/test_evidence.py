from pathlib import Path

import pytest

from msa.validation.experiments import (
    ExperimentEvidenceError,
    write_c008c_authority_evidence,
)
from msa.validation.remediation import (
    REVIEWED_REMEDIATION_ID,
    check_existing_decimal_remediation_evidence,
)


ROOT = Path(__file__).resolve().parents[3]


def test_versioned_remediation_evidence_is_canonical_and_source_bound() -> None:
    path = check_existing_decimal_remediation_evidence(ROOT)
    assert path.name == "c008c_h2_decimal_remediation.json"
    assert REVIEWED_REMEDIATION_ID.startswith(
        "c008c-h2-decimal-remediation-v1-"
    )


def test_historical_v1_evidence_cannot_be_regenerated() -> None:
    with pytest.raises(
        ExperimentEvidenceError,
        match="cannot be regenerated after a versioned remediation",
    ):
        write_c008c_authority_evidence(ROOT, check=False)
