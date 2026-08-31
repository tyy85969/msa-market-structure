"""Formal append-only C-008C-C locked synthetic OOS architecture."""

from .architecture import (
    ATTEMPT_PATH,
    CONTRACT_PATH,
    FAILED_POST_FIX_ATTEMPT_PATH,
    FAILED_POST_FIX_CONTRACT_PATH,
    FAILED_POST_EXPOSURE_ATTEMPT_PATH,
    FAILED_POST_EXPOSURE_CONTRACT_PATH,
    LEGACY_ATTEMPT_PATH,
    LEGACY_CONTRACT_PATH,
    REPORT_PATH,
    check_existing_c008c_c_evidence,
    prepare_c008c_c_execution_contract,
    run_c008c_c_locked_oos,
    validate_c008c_c_preflight,
)
from .contracts import (
    C008CCCaseResult,
    C008CCContractError,
    C008CCFixedCutoffComparison,
    C008CCMetricDelta,
    C008CCMetricDeltaSummary,
    C008CCPartition,
    C008CCReplayComparison,
)

__all__ = [
    "ATTEMPT_PATH",
    "C008CCCaseResult",
    "C008CCContractError",
    "C008CCFixedCutoffComparison",
    "C008CCMetricDelta",
    "C008CCMetricDeltaSummary",
    "C008CCPartition",
    "C008CCReplayComparison",
    "CONTRACT_PATH",
    "FAILED_POST_FIX_ATTEMPT_PATH",
    "FAILED_POST_FIX_CONTRACT_PATH",
    "FAILED_POST_EXPOSURE_ATTEMPT_PATH",
    "FAILED_POST_EXPOSURE_CONTRACT_PATH",
    "LEGACY_ATTEMPT_PATH",
    "LEGACY_CONTRACT_PATH",
    "REPORT_PATH",
    "check_existing_c008c_c_evidence",
    "prepare_c008c_c_execution_contract",
    "run_c008c_c_locked_oos",
    "validate_c008c_c_preflight",
]
