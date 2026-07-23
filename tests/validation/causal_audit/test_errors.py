from copy import deepcopy
from datetime import datetime

import pytest

from msa.validation import (
    CausalAuditConfig,
    CausalAuditor,
    MSAValidationError,
    ValidationComparisonError,
    ValidationConfigurationError,
    ValidationInputError,
)

from .fixtures import valid_prefix_pair, valid_run


def test_error_hierarchy_is_validation_specific() -> None:
    assert issubclass(ValidationInputError, MSAValidationError)
    assert issubclass(ValidationComparisonError, MSAValidationError)


def test_invalid_config_fails_with_configuration_error() -> None:
    with pytest.raises(ValidationConfigurationError):
        CausalAuditConfig(strict=False)
    with pytest.raises(ValidationConfigurationError):
        CausalAuditConfig(max_facts=9)


def test_non_formal_entrypoint_arguments_fail_closed() -> None:
    value = CausalAuditor()
    with pytest.raises(ValidationInputError):
        value.audit_run(object())  # type: ignore[arg-type]
    with pytest.raises(ValidationInputError):
        value.compare_batch_replay(valid_run(), object())  # type: ignore[arg-type]


def test_naive_shared_asof_cutoff_uses_comparison_error() -> None:
    prefix, extended = valid_prefix_pair()
    with pytest.raises(ValidationComparisonError):
        CausalAuditor().compare_shared_asof(
            prefix, extended, datetime(2026, 7, 20)
        )


def test_severely_damaged_nested_object_returns_failed_report() -> None:
    run = deepcopy(valid_run())
    object.__setattr__(
        run.frame_bundles[0].resonance_frame,
        "evidence",
        (object(),),
    )
    report = CausalAuditor().audit_run(run)
    assert not report.passed
