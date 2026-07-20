"""Close-confirmed structure baseline seeded by causal Pivot candidates."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum
from hashlib import sha256
from typing import Any, Iterator, Mapping, Sequence

from msa.data import CanonicalBar, LoadResult
from msa.domain import (
    BoundarySide,
    ConfirmationStatus,
    LevelCandidate,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
    StructureSourceType,
)

from .atr_reversal import (
    _causal_prefix,
    _decimal_text,
    _normalize_processing_time,
    _prefix_available_times,
    _prefix_load_result,
    _validate_stateful_input,
)
from .contracts import (
    SCHEMA_VERSION,
    PivotDetectorConfig,
    SwingDetectionEvent,
    SwingDetectionReport,
    SwingDetectionResult,
    _require_exact_payload,
    _require_text,
)
from .errors import SwingConfigurationError, SwingDetectionError
from .pivot import PivotDetector, _canonical_json, canonical_bar_key


STRUCTURE_FAMILY = "pivot-structure-confirmation-close-v1"
SOURCE_MODULE = "msa.research.swing.structure_break"


class BreakBasis(str, Enum):
    """Supported bar field for structure confirmation."""

    CLOSE = "CLOSE"


class PendingReplacementPolicy(str, Enum):
    """Supported unresolved-seed replacement policy."""

    LATEST_CONFIRMED = "LATEST_CONFIRMED"


@dataclass(frozen=True, slots=True)
class StructureBreakDetectorConfig:
    """Explicit immutable configuration for Pivot-seeded close confirmation."""

    detector_id: str
    detector_version: str
    seed_pivot_config: PivotDetectorConfig
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
        if not isinstance(self.seed_pivot_config, PivotDetectorConfig):
            raise SwingConfigurationError(
                "seed_pivot_config must be a PivotDetectorConfig"
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
                "StructureBreakDetectorConfig.strict must be True; "
                "C-003B supports strict mode only"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "seed_pivot_config": self.seed_pivot_config.to_dict(),
            "break_buffer": str(self.break_buffer),
            "break_basis": self.break_basis.value,
            "pending_replacement_policy": self.pending_replacement_policy.value,
            "policy_id": self.policy_id,
            "strict": self.strict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> StructureBreakDetectorConfig:
        fields = {
            "detector_id",
            "detector_version",
            "seed_pivot_config",
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
            seed_pivot_config=PivotDetectorConfig.from_dict(
                data["seed_pivot_config"]
            ),
            break_buffer=_decimal_text("break_buffer", data["break_buffer"]),
            break_basis=break_basis,
            pending_replacement_policy=replacement,
            policy_id=data["policy_id"],
            strict=data["strict"],
            schema_version=data["schema_version"],
        )


@dataclass(frozen=True, slots=True)
class _SeedFact:
    candidate: LevelCandidate
    last_window_index: int
    effective_time: datetime

    @property
    def rank(self) -> tuple[datetime, datetime, str]:
        if self.candidate.confirm_time is None:
            raise SwingDetectionError("confirmed seed has no confirm_time")
        return (
            self.effective_time,
            self.candidate.confirm_time,
            self.candidate.candidate_id,
        )


@dataclass(frozen=True, slots=True)
class _BreakOutcome:
    candidates: tuple[LevelCandidate, ...]
    evaluated_count: int
    rejected_count: int
    unresolved_count: int


def _validate_seed(candidate: LevelCandidate) -> None:
    if candidate.source_type is not StructureSourceType.SWING:
        raise SwingDetectionError("seed candidate must use source_type=SWING")
    if (
        candidate.confirmation_status is not ConfirmationStatus.CONFIRMED
        or candidate.confirm_time is None
    ):
        raise SwingDetectionError("seed candidate must already be confirmed")
    valid_mapping = (
        candidate.boundary_side is BoundarySide.UPPER
        and candidate.market_role is MarketRole.RESISTANCE
    ) or (
        candidate.boundary_side is BoundarySide.LOWER
        and candidate.market_role is MarketRole.SUPPORT
    )
    if not valid_mapping:
        raise SwingDetectionError("seed side/market-role mapping is unsupported")


def _seed_facts(
    candidates: Sequence[LevelCandidate],
    bars: Sequence[CanonicalBar],
    prefix_times: Sequence[datetime],
) -> tuple[_SeedFact, ...]:
    index_by_key = {
        canonical_bar_key(bar): index for index, bar in enumerate(bars)
    }
    facts: list[_SeedFact] = []
    for candidate in candidates:
        _validate_seed(candidate)
        member_indexes = tuple(
            index_by_key[parent]
            for parent in candidate.provenance.parent_object_ids
            if parent in index_by_key
        )
        if not member_indexes:
            raise SwingDetectionError(
                "seed provenance must reference its finite source-bar window"
            )
        last_index = max(member_indexes)
        if candidate.confirm_time is None:
            raise SwingDetectionError("confirmed seed has no confirm_time")
        effective_time = max(candidate.confirm_time, prefix_times[last_index])
        facts.append(_SeedFact(candidate, last_index, effective_time))
    return tuple(
        sorted(
            facts,
            key=lambda item: (
                item.last_window_index,
                item.rank,
            ),
        )
    )


def _latest_reference(
    known: Sequence[_SeedFact], pending: _SeedFact
) -> _SeedFact | None:
    eligible = tuple(
        item
        for item in known
        if item.candidate.origin_time < pending.candidate.origin_time
    )
    return max(eligible, key=lambda item: item.rank) if eligible else None


def _detect_structure_confirmations(
    *,
    bars: tuple[CanonicalBar, ...],
    seed_candidates: Sequence[LevelCandidate],
    break_buffer: Decimal,
    detector_id: str,
    detector_version: str,
    policy_id: str,
    config_payload: Mapping[str, object],
    structure_family: str,
    source_module: str,
    candidate_prefix: str,
) -> _BreakOutcome:
    prefix_times = _prefix_available_times(bars)
    facts = _seed_facts(seed_candidates, bars, prefix_times)
    known: dict[BoundarySide, list[_SeedFact]] = {
        BoundarySide.UPPER: [],
        BoundarySide.LOWER: [],
    }
    pending: dict[BoundarySide, _SeedFact | None] = {
        BoundarySide.UPPER: None,
        BoundarySide.LOWER: None,
    }
    cursor = 0
    candidates: list[LevelCandidate] = []
    evaluated = 0
    rejected = 0

    for index, bar in enumerate(bars):
        while cursor < len(facts) and facts[cursor].last_window_index < index:
            fact = facts[cursor]
            side = fact.candidate.boundary_side
            known[side].append(fact)
            current = pending[side]
            if current is None or fact.rank > current.rank:
                pending[side] = fact
            cursor += 1

        for side in (BoundarySide.UPPER, BoundarySide.LOWER):
            pending_fact = pending[side]
            if pending_fact is None:
                continue
            opposing = (
                BoundarySide.LOWER
                if side is BoundarySide.UPPER
                else BoundarySide.UPPER
            )
            reference = _latest_reference(known[opposing], pending_fact)
            if reference is None:
                continue
            if (
                index <= pending_fact.last_window_index
                or index <= reference.last_window_index
            ):
                continue
            evaluated += 1
            if side is BoundarySide.UPPER:
                threshold = (
                    reference.candidate.price_range.low - break_buffer
                )
                broken = bar.close <= threshold
            else:
                threshold = (
                    reference.candidate.price_range.high + break_buffer
                )
                broken = bar.close >= threshold
            if not broken:
                rejected += 1
                continue
            candidates.append(
                _structure_candidate(
                    pending=pending_fact.candidate,
                    reference=reference.candidate,
                    break_bar=bar,
                    prefix_time=prefix_times[index],
                    break_buffer=break_buffer,
                    detector_id=detector_id,
                    detector_version=detector_version,
                    policy_id=policy_id,
                    config_payload=config_payload,
                    structure_family=structure_family,
                    source_module=source_module,
                    candidate_prefix=candidate_prefix,
                )
            )
            pending[side] = None

    ordered = tuple(
        sorted(
            candidates,
            key=lambda item: (item.confirm_time, item.candidate_id),
        )
    )
    unresolved = sum(item is not None for item in pending.values())
    return _BreakOutcome(ordered, evaluated, rejected, unresolved)


def _structure_candidate(
    *,
    pending: LevelCandidate,
    reference: LevelCandidate,
    break_bar: CanonicalBar,
    prefix_time: datetime,
    break_buffer: Decimal,
    detector_id: str,
    detector_version: str,
    policy_id: str,
    config_payload: Mapping[str, object],
    structure_family: str,
    source_module: str,
    candidate_prefix: str,
) -> LevelCandidate:
    if pending.confirm_time is None or reference.confirm_time is None:
        raise SwingDetectionError("structure seeds must have confirm_time")
    confirm_time = max(
        pending.confirm_time,
        reference.confirm_time,
        prefix_time,
    )
    break_key = canonical_bar_key(break_bar)
    price = pending.price_range.low
    if pending.price_range.low != pending.price_range.high:
        raise SwingDetectionError("Swing seed price range must be a singleton")
    identity = {
        "boundary_side": pending.boundary_side.value,
        "break_bar_key": break_key,
        "break_buffer": str(break_buffer),
        "break_close": str(break_bar.close),
        "config": dict(config_payload),
        "confirm_time": confirm_time.isoformat(),
        "detector_id": detector_id,
        "detector_version": detector_version,
        "origin_time": pending.origin_time.isoformat(),
        "pending_seed_id": pending.candidate_id,
        "policy_id": policy_id,
        "price": str(price),
        "reference_seed_id": reference.candidate_id,
        "schema_version": SCHEMA_VERSION,
    }
    digest = sha256(_canonical_json(identity).encode("utf-8")).hexdigest()
    source_digest = sha256(
        _canonical_json(
            {"identity": identity, "source_module": source_module}
        ).encode("utf-8")
    ).hexdigest()
    provenance = ProvenanceRef(
        source_module=source_module,
        source_version=detector_version,
        source_object_id=f"structure-confirmation-v1-{source_digest}",
        policy_id=policy_id,
        parent_object_ids=(
            pending.candidate_id,
            reference.candidate_id,
            break_key,
        ),
        notes=(
            f"detector_id={detector_id}",
            f"detector_version={detector_version}",
            f"policy_id={policy_id}",
            "break_basis=CLOSE",
            "pending_replacement_policy=LATEST_CONFIRMED",
            f"pending_seed_id={pending.candidate_id}",
            f"reference_seed_id={reference.candidate_id}",
            f"break_bar_key={break_key}",
            f"break_close={break_bar.close}",
            f"break_buffer={break_buffer}",
        ),
    )
    return LevelCandidate(
        candidate_id=f"{candidate_prefix}-{digest}",
        symbol=pending.symbol,
        timeframe=pending.timeframe,
        scale=pending.scale,
        price_range=PriceRange(price, price),
        source_type=StructureSourceType.SWING,
        boundary_side=pending.boundary_side,
        market_role=pending.market_role,
        confirmation_status=ConfirmationStatus.CONFIRMED,
        lifecycle_state=LifecycleState.CONFIRMED,
        origin_time=pending.origin_time,
        confirm_time=confirm_time,
        touch_count=0,
        last_touch_time=None,
        last_touch_confirm_time=None,
        break_time=None,
        break_confirm_time=None,
        structure_family=structure_family,
        provenance=provenance,
    )


def _build_break_report(
    *,
    source: LoadResult,
    bars: tuple[CanonicalBar, ...],
    outcome: _BreakOutcome,
    detector_id: str,
    detector_version: str,
    policy_id: str,
    seed_label: str,
    break_buffer: Decimal,
    truncated: bool,
) -> SwingDetectionReport:
    warnings: list[str] = []
    if outcome.unresolved_count:
        warnings.append(
            f"{outcome.unresolved_count} pending seed(s) remain unresolved"
        )
    if truncated:
        warnings.append(
            "causal prefix truncated at the first incomplete or unavailable bar"
        )
    gap_count = _prefix_load_result(source, bars).quality_report.gap_count
    if gap_count:
        warnings.append(f"{gap_count} source interval gap(s); no bars filled")
    origins = tuple(item.origin_time for item in outcome.candidates)
    confirms = tuple(
        item.confirm_time
        for item in outcome.candidates
        if item.confirm_time is not None
    )
    return SwingDetectionReport(
        input_bar_count=len(bars),
        evaluated_center_count=outcome.evaluated_count,
        confirmed_high_count=sum(
            item.boundary_side is BoundarySide.UPPER
            for item in outcome.candidates
        ),
        confirmed_low_count=sum(
            item.boundary_side is BoundarySide.LOWER
            for item in outcome.candidates
        ),
        leading_incomplete_count=0,
        trailing_incomplete_count=outcome.unresolved_count,
        gap_count=gap_count,
        rejected_window_count=outcome.rejected_count,
        earliest_origin_time=min(origins) if origins else None,
        latest_origin_time=max(origins) if origins else None,
        earliest_confirm_time=min(confirms) if confirms else None,
        latest_confirm_time=max(confirms) if confirms else None,
        detector_id=detector_id,
        detector_version=detector_version,
        policy_id=policy_id,
        assumptions=(
            f"confirmed {seed_label} candidates are immutable seeds",
            "only close values can confirm the opposing-structure threshold",
            f"break_buffer={break_buffer}",
            "pending seeds use LATEST_CONFIRMED replacement",
            "reference origin_time must precede pending seed origin_time",
            "break bar follows both seed confirmation windows",
            "confirm_time=max(seed, reference, break-prefix availability)",
            "as-of stops at the first incomplete or unavailable source bar",
        ),
        warnings=tuple(warnings),
        errors=(),
    )


@dataclass(frozen=True, slots=True)
class StructureBreakDetector:
    """Pivot-seeded close-confirmation baseline."""

    config: StructureBreakDetectorConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, StructureBreakDetectorConfig):
            raise SwingDetectionError(
                "config must be a StructureBreakDetectorConfig"
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
        seeds = PivotDetector(self.config.seed_pivot_config).detect_batch(
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
            candidate_prefix="swing-pivot-structure-v1",
        )
        report = _build_break_report(
            source=source,
            bars=bars,
            outcome=outcome,
            detector_id=self.detector_id,
            detector_version=self.detector_version,
            policy_id=self.config.policy_id,
            seed_label="Pivot",
            break_buffer=self.config.break_buffer,
            truncated=truncated,
        )
        return SwingDetectionResult(outcome.candidates, report)


__all__ = [
    "BreakBasis",
    "PendingReplacementPolicy",
    "StructureBreakDetector",
    "StructureBreakDetectorConfig",
]
