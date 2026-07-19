"""Direct periodic-bar extreme candidate generator for C-004."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
import json
from typing import Iterator

from msa.data import CanonicalBar
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
from msa.research.swing import canonical_bar_key

from ._validation import (
    normalize_processing_time,
    validate_no_complete_after_incomplete,
    validate_source,
)
from .contracts import (
    LevelGenerationEvent,
    LevelGenerationInput,
    LevelGenerationReport,
    LevelGenerationResult,
    PeriodicExtremeConfig,
)
from .errors import LevelGenerationError, LevelInputError


SOURCE_MODULE = "msa.research.levels.periodic"


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise LevelGenerationError("unable to build canonical JSON identity") from exc


@dataclass(frozen=True, slots=True)
class PeriodicExtremeGenerator:
    """Emit exact high/low points from already-built periodic bars."""

    config: PeriodicExtremeConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, PeriodicExtremeConfig):
            raise LevelGenerationError("config must be a PeriodicExtremeConfig")

    @property
    def generator_id(self) -> str:
        return self.config.generator_id

    @property
    def generator_version(self) -> str:
        return self.config.generator_version

    def generate_batch(self, data: LevelGenerationInput) -> LevelGenerationResult:
        bars = self._validate(data)
        visible = tuple(bar for bar in bars if bar.is_complete)
        return self._generate(data, bars, visible, processing_time=None)

    def generate_as_of(
        self, data: LevelGenerationInput, processing_time: datetime
    ) -> LevelGenerationResult:
        normalized = normalize_processing_time(processing_time)
        bars = self._validate(data)
        visible = tuple(
            bar
            for bar in bars
            if bar.is_complete and bar.available_time <= normalized
        )
        return self._generate(data, bars, visible, processing_time=normalized)

    def iter_events(
        self, data: LevelGenerationInput
    ) -> Iterator[LevelGenerationEvent]:
        for candidate in self.generate_batch(data).candidates:
            if candidate.confirm_time is None:
                raise LevelGenerationError("confirmed candidate has no confirm_time")
            yield LevelGenerationEvent(candidate.confirm_time, candidate)

    def _validate(self, data: LevelGenerationInput) -> tuple[CanonicalBar, ...]:
        bars = validate_source(data)
        if data.seed_candidates:
            raise LevelInputError(
                "PeriodicExtremeGenerator requires seed_candidates to be empty"
            )
        if data.source.source_config.timeframe is not self.config.period_timeframe:
            raise LevelInputError(
                "source timeframe must equal config.period_timeframe"
            )
        validate_no_complete_after_incomplete(bars)
        return bars

    def _generate(
        self,
        data: LevelGenerationInput,
        bars: tuple[CanonicalBar, ...],
        visible: tuple[CanonicalBar, ...],
        *,
        processing_time: datetime | None,
    ) -> LevelGenerationResult:
        candidates: list[LevelCandidate] = []
        for bar in visible:
            if self.config.emit_high:
                candidates.append(self._candidate(bar, BoundarySide.UPPER))
            if self.config.emit_low:
                candidates.append(self._candidate(bar, BoundarySide.LOWER))
        ordered = tuple(
            sorted(candidates, key=lambda item: (item.confirm_time, item.candidate_id))
        )
        origins = tuple(item.origin_time for item in ordered)
        confirms = tuple(
            item.confirm_time for item in ordered if item.confirm_time is not None
        )
        ignored = sum(
            not bar.is_complete
            and (processing_time is None or bar.available_time <= processing_time)
            for bar in bars
        )
        warnings: list[str] = []
        if ignored:
            warnings.append(
                f"{ignored} incomplete periodic bar(s) ignored without candidate output"
            )
        gap_count = _gap_count(visible)
        if gap_count:
            warnings.append(
                f"{gap_count} source interval gap(s); no periodic bar was synthesized"
            )
        report = LevelGenerationReport(
            input_bar_count=len(bars),
            visible_bar_count=len(visible),
            seed_count=0,
            eligible_seed_count=0,
            periodic_high_count=sum(
                item.boundary_side is BoundarySide.UPPER for item in ordered
            ),
            periodic_low_count=sum(
                item.boundary_side is BoundarySide.LOWER for item in ordered
            ),
            reaction_candidate_count=0,
            ignored_incomplete_count=ignored,
            evaluated_touch_count=0,
            successful_reaction_count=0,
            rejected_reaction_attempt_count=0,
            gap_count=gap_count,
            earliest_origin_time=min(origins) if origins else None,
            latest_origin_time=max(origins) if origins else None,
            earliest_confirm_time=min(confirms) if confirms else None,
            latest_confirm_time=max(confirms) if confirms else None,
            generator_id=self.generator_id,
            generator_version=self.generator_version,
            policy_id=self.config.policy_id,
            assumptions=(
                "input bars are already loaded/resampled C-001 periodic bars",
                "the generator never aggregates or infers period boundaries",
                "origin_time=period bar timestamp (period start, not intraperiod extreme time)",
                "confirm_time=period bar available_time",
            ),
            warnings=tuple(warnings),
            errors=(),
        )
        return LevelGenerationResult(ordered, report)

    def _candidate(
        self, bar: CanonicalBar, side: BoundarySide
    ) -> LevelCandidate:
        price = bar.high if side is BoundarySide.UPPER else bar.low
        bar_key = canonical_bar_key(bar)
        identity = {
            "available_time": bar.available_time.isoformat(),
            "bar_key": bar_key,
            "boundary_policy": bar.boundary_policy,
            "boundary_side": side.value,
            "end_time": bar.end_time.isoformat(),
            "generator_id": self.generator_id,
            "generator_version": self.generator_version,
            "origin_time": bar.timestamp.isoformat(),
            "policy_id": self.config.policy_id,
            "price": str(price),
            "scale": self.config.scale.to_dict(),
            "schema_version": self.config.schema_version,
            "source": bar.source,
            "strict": self.config.strict,
            "symbol": bar.symbol,
            "timeframe": bar.timeframe.value,
        }
        digest = sha256(_canonical_json(identity).encode("utf-8")).hexdigest()
        candidate_id = f"periodic-extreme-v1-{digest}"
        source_object_id = f"periodic-bar-extreme-v1-{digest}"
        provenance = ProvenanceRef(
            source_module=SOURCE_MODULE,
            source_version=self.generator_version,
            source_object_id=source_object_id,
            policy_id=self.config.policy_id,
            parent_object_ids=(bar_key,),
            notes=(
                f"generator_id={self.generator_id}",
                f"generator_version={self.generator_version}",
                f"policy_id={self.config.policy_id}",
                f"source_timeframe={bar.timeframe.value}",
                f"boundary_policy={bar.boundary_policy}",
                f"boundary_side={side.value}",
                "origin_time denotes the periodic interval start",
                "no intraperiod extreme timestamp is inferred",
            ),
        )
        return LevelCandidate(
            candidate_id=candidate_id,
            symbol=bar.symbol,
            timeframe=bar.timeframe,
            scale=self.config.scale,
            price_range=PriceRange(price, price),
            source_type=StructureSourceType.PERIODIC_EXTREME,
            boundary_side=side,
            market_role=(
                MarketRole.RESISTANCE
                if side is BoundarySide.UPPER
                else MarketRole.SUPPORT
            ),
            confirmation_status=ConfirmationStatus.CONFIRMED,
            lifecycle_state=LifecycleState.CONFIRMED,
            origin_time=bar.timestamp,
            confirm_time=bar.available_time,
            touch_count=0,
            last_touch_time=None,
            last_touch_confirm_time=None,
            break_time=None,
            break_confirm_time=None,
            structure_family=(
                f"periodic-extreme-{self.config.period_timeframe.value.lower()}-v1"
            ),
            provenance=provenance,
        )


def _gap_count(bars: tuple[CanonicalBar, ...]) -> int:
    return sum(
        current.timestamp > previous.end_time
        for previous, current in zip(bars, bars[1:])
    )
