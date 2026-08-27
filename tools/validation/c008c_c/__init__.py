"""Formal append-only C-008C-C locked synthetic OOS architecture."""

from .architecture import (
    ATTEMPT_PATH,
    CONTRACT_PATH,
    LEGACY_ATTEMPT_PATH,
    LEGACY_CONTRACT_PATH,
    REPORT_PATH,
    check_existing_c008c_c_evidence,
    prepare_c008c_c_execution_contract,
    run_c008c_c_locked_oos,
    validate_c008c_c_preflight,
)
from .contracts import C008CCCaseResult, C008CCContractError, C008CCPartition

__all__ = [
    "ATTEMPT_PATH",
    "C008CCCaseResult",
    "C008CCContractError",
    "C008CCPartition",
    "CONTRACT_PATH",
    "LEGACY_ATTEMPT_PATH",
    "LEGACY_CONTRACT_PATH",
    "REPORT_PATH",
    "check_existing_c008c_c_evidence",
    "prepare_c008c_c_execution_contract",
    "run_c008c_c_locked_oos",
    "validate_c008c_c_preflight",
]
