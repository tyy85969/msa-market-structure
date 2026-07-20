"""ATR-seeded close-confirmation combination baseline for C-003B."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Any, Iterator, Mapping

from msa.data import CanonicalBar, LoadResult

from .atr_reversal import (
    AtrReversalDetector,
    AtrReversalDetectorConfig,
    _causal_prefix,
    _decimal_text,
    _normalize_processing_time,
    _prefix_load_result,
    _validate_stateful_input,
)
from .contracts import (
    SCHEMA_VERSION,
    SwingDetectionEvent,
    SwingDetectionResult,
    _require_exact_payload,
    _require_text,
)
from .errors import SwingConfigurationError, SwingDetectionError
from .structure_break import (
    BreakBasis,
    PendingReplacementPolicy,
    _build_break_report,
    _detect_structure_confirmations,
)


STRUCTURE_FAMILY = "atr-structure-confirmation-close-v1"
SOURCE_MODULE = "msa.research.swing.combined"


@dataclass(frozen=True, slots=True)
class AtrStructureBreakDetectorConfig:
    """Explicit immutable configuration for the ATR-seeded combination."""

    detector_id: str
    detector_version: str
    seed_atr_config: AtrReversalDetectorConfig
    break_buffer: Decimal
    break_basis: BreakBasis
    pending_replacement_policy: PendingReplacementPolicy
    policy_id: str
    strict: bool = True
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        _require_text("detector_id", self.detector_id)
        _require_text("detector_version", self.detector_version)
        _require_text("policy_id", self.policy_id)
        if self.schema_version != SCHEMA_VERSION or isinstance(
            self.schema_version, bool
        ):
            raise SwingConfigurationError(
                f"schema_version must be {SCHEMA_VERSION}"
            )
        if not isinstance(self.seed_atr_config, AtrReversalDetectorConfig):
            raise SwingConfigurationError(
                "seed_atr_config must be an AtrReversalDetectorConfig"
            )
        if not isinstance(self.break_buffer, Decimal):
            raise SwingConfigurationError("break_buffer must be an exact Decimal")
        if not self.break_buffer.is_finite() or self.break_buffer < 0:
            raise SwingConfigurationError("break_buffer must be finite and >= 0")
        if self.break_basis is not BreakBasis.CLOSE:
            raise SwingConfigurationError("only break_basis=CLOSE is supported")
        if (
            self.pending_replacement_policy
            is not PendingReplacementPolicy.LATEST_CONFIRMED
        ):
            raise SwingConfigurationError(
                "only pending_replacement_policy=LATEST_CONFIRMED is supported"
            )
        if not isinstance(self.strict, bool):
            raise SwingConfigurationError("strict must be a bool")
        if self.strict is not True:
            raise SwingConfigurationError(
                "AtrStructureBreakDetectorConfig.strict must be True; "
                "C-003B supports strict mode only"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "seed_atr_config": self.seed_atr_config.to_dict(),
            "break_buffer": str(self.break_buffer),
            "break_basis": self.break_basis.value,
            "pending_replacement_policy": self.pending_replacement_policy.value,
            "policy_id": self.policy_id,
            "strict": self.strict,
        }

    @classmethod
    def from_dict(
        cls, payload: Mapping[str, Any]
    ) -> AtrStructureBreakDetectorConfig:
        fields = {
            "detector_id",
            "detector_version",
            "seed_atr_config",
            "break_buffer",
            "break_basis",
            "pending_replacement_policy",
            "policy_id",
            "strict",
        }
        data = _require_exact_payload(payload, cls.__name__, fields)
        try:
            break_basis = BreakBasis(data["break_basis"])
        except (TypeError, ValueError) as exc:
            raise SwingConfigurationError("unknown break_basis") from exc
        try:
            replacement = PendingReplacementPolicy(
                data["pending_replacement_policy"]
            )
        except (TypeError, ValueError) as exc:
            raise SwingConfigurationError(
                "unknown pending_replacement_policy"
            ) from exc
        return cls(
            detector_id=data["detector_id"],
            detector_version=data["detector_version"],
            seed_atr_config=AtrReversalDetectorConfig.from_dict(
                data["seed_atr_config"]
            ),
            break_buffer=_decimal_text("break_buffer", data["break_buffer"]),
            break_basis=break_basis,
            pending_replacement_policy=replacement,
            policy_id=data["policy_id"],
            strict=data["strict"],
            schema_version=data["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class AtrStructureBreakDetector:
    """ATR-seeded close-confirmation combination baseline."""

    config: AtrStructureBreakDetectorConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, AtrStructureBreakDetectorConfig):
            raise SwingDetectionError(
                "config must be an AtrStructureBreakDetectorConfig"
            )

    @property
    def detector_id(self) -> str:
        return self.config.detector_id

    @property
    def detector_version(self) -> str:
        return self.config.detector_version

    def detect_batch(self, source: LoadResult) -> SwingDetectionResult:
        bars = _validate_stateful_input(source)
        prefix = _causal_prefix(bars, None)
        return self._detect(source, prefix, truncated=False)

    def detect_as_of(
        self, source: LoadResult, processing_time: datetime
    ) -> SwingDetectionResult:
        normalized = _normalize_processing_time(processing_time)
        bars = _validate_stateful_input(source)
        prefix = _causal_prefix(bars, normalized)
        return self._detect(source, prefix, truncated=len(prefix) < len(bars))

    def iter_events(self, source: LoadResult) -> Iterator[SwingDetectionEvent]:
        for candidate in self.detect_batch(source).candidates:
            if candidate.confirm_time is None:
                raise SwingDetectionError("confirmed batch candidate has no time")
            yield SwingDetectionEvent(candidate.confirm_time, candidate)

    def _detect(
        self,
        source: LoadResult,
        bars: tuple[CanonicalBar, ...],
        *,
        truncated: bool,
    ) -> SwingDetectionResult:
        prefix_source = _prefix_load_result(source, bars)
        seeds = AtrReversalDetector(self.config.seed_atr_config).detect_batch(
            prefix_source
        ).candidates
        outcome = _detect_structure_confirmations(
            bars=bars,
            seed_candidates=seeds,
            break_buffer=self.config.break_buffer,
            detector_id=self.detector_id,
            detector_version=self.detector_version,
            policy_id=self.config.policy_id,
            config_payload=self.config.to_dict(),
            structure_family=STRUCTURE_FAMILY,
            source_module=SOURCE_MODULE,
            candidate_prefix="swing-atr-structure-v1",
        )
        report = _build_break_report(
            source=source,
            bars=bars,
            outcome=outcome,
            detector_id=self.detector_id,
            detector_version=self.detector_version,
            policy_id=self.config.policy_id,
            seed_label="ATR turning-point",
            break_buffer=self.config.break_buffer,
            truncated=truncated,
        )
        return SwingDetectionResult(outcome.candidates, report)


__all__ = [
    "AtrStructureBreakDetector",
    "AtrStructureBreakDetectorConfig",
]
