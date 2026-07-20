"""Seed-specific historical-reaction baseline for C-004."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
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
    causal_prefix,
    normalize_processing_time,
    prefix_available_times,
    validate_source,
)
from .contracts import (
    HistoricalReactionConfig,
    LevelGenerationEvent,
    LevelGenerationInput,
    LevelGenerationReport,
    LevelGenerationResult,
)
from .errors import LevelGenerationError, LevelInputError


SOURCE_MODULE = "msa.research.levels.reaction"
STRUCTURE_FAMILY = "historical-reaction-baseline-v1"


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
class _Attempt:
    touch_index: int
    touch_bar: CanonicalBar


@dataclass(frozen=True, slots=True)
class _ReactionEvidence:
    touch_index: int
    confirmation_index: int
    touch_bar: CanonicalBar
    confirmation_bar: CanonicalBar
    confirm_time: datetime

    def identity(self) -> dict[str, object]:
        return {
            "confirmation_bar_key": canonical_bar_key(self.confirmation_bar),
            "confirmation_index": self.confirmation_index,
            "confirm_time": self.confirm_time.isoformat(),
            "touch_bar_key": canonical_bar_key(self.touch_bar),
            "touch_index": self.touch_index,
            "touch_time": self.touch_bar.timestamp.isoformat(),
        }


@dataclass(frozen=True, slots=True)
class _SeedEvaluation:
    candidate: LevelCandidate | None
    evaluated_touch_count: int
    successful_reaction_count: int
    rejected_attempt_count: int


@dataclass(frozen=True, slots=True)
class HistoricalReactionGenerator:
    """Confirm a bounded zone after repeated causal close-away reactions."""

    config: HistoricalReactionConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, HistoricalReactionConfig):
            raise LevelGenerationError("config must be a HistoricalReactionConfig")

    @property
    def generator_id(self) -> str:
        return self.config.generator_id

    @property
    def generator_version(self) -> str:
        return self.config.generator_version

    def generate_batch(self, data: LevelGenerationInput) -> LevelGenerationResult:
        bars, seeds = self._validate(data)
        prefix = causal_prefix(bars, None)
        return self._generate(data, bars, prefix, seeds, processing_time=None)

    def generate_as_of(
        self, data: LevelGenerationInput, processing_time: datetime
    ) -> LevelGenerationResult:
        normalized = normalize_processing_time(processing_time)
        bars, seeds = self._validate(data)
        prefix = causal_prefix(bars, normalized)
        visible_seeds = tuple(
            seed
            for seed in seeds
            if seed.confirm_time is not None and seed.confirm_time <= normalized
        )
        return self._generate(
            data, bars, prefix, visible_seeds, processing_time=normalized
        )

    def iter_events(
        self, data: LevelGenerationInput
    ) -> Iterator[LevelGenerationEvent]:
        for candidate in self.generate_batch(data).candidates:
            if candidate.confirm_time is None:
                raise LevelGenerationError("confirmed candidate has no confirm_time")
            yield LevelGenerationEvent(candidate.confirm_time, candidate)

    def _validate(
        self, data: LevelGenerationInput
    ) -> tuple[tuple[CanonicalBar, ...], tuple[LevelCandidate, ...]]:
        bars = validate_source(data)
        seeds = data.seed_candidates
        if not seeds:
            raise LevelInputError(
                "HistoricalReactionGenerator requires non-empty seed_candidates"
            )
        identifiers: set[str] = set()
        ordering: list[tuple[datetime, str]] = []
        source_symbol = data.source.source_config.canonical_symbol
        source_timeframe = data.source.source_config.timeframe
        for seed in seeds:
            if seed.candidate_id in identifiers:
                raise LevelInputError("seed candidate IDs must be unique")
            identifiers.add(seed.candidate_id)
            if seed.source_type is not StructureSourceType.SWING:
                raise LevelInputError("historical-reaction seeds must be SWING")
            if (
                seed.confirmation_status is not ConfirmationStatus.CONFIRMED
                or seed.confirm_time is None
            ):
                raise LevelInputError("historical-reaction seeds must be CONFIRMED")
            if seed.price_range.low != seed.price_range.high:
                raise LevelInputError("historical-reaction seed must be a point price")
            if seed.symbol != source_symbol:
                raise LevelInputError("seed symbol must match source symbol")
            if seed.timeframe is not source_timeframe:
                raise LevelInputError("seed timeframe must match source timeframe")
            if seed.boundary_side is BoundarySide.UPPER:
                if seed.market_role is not MarketRole.RESISTANCE:
                    raise LevelInputError("UPPER seed must have RESISTANCE role")
            elif seed.boundary_side is BoundarySide.LOWER:
                if seed.market_role is not MarketRole.SUPPORT:
                    raise LevelInputError("LOWER seed must have SUPPORT role")
            else:
                raise LevelInputError("seed boundary_side must be UPPER or LOWER")
            zone_low = seed.price_range.low - self.config.touch_tolerance
            if zone_low < 0:
                raise LevelInputError(
                    "reaction zone lower bound must not be negative; clipping is forbidden"
                )
            PriceRange(zone_low, seed.price_range.high + self.config.touch_tolerance)
            ordering.append((seed.confirm_time, seed.candidate_id))
        if ordering != sorted(ordering):
            raise LevelInputError(
                "seed_candidates must be ordered by (confirm_time, candidate_id)"
            )
        return bars, seeds

    def _generate(
        self,
        data: LevelGenerationInput,
        all_bars: tuple[CanonicalBar, ...],
        prefix: tuple[CanonicalBar, ...],
        seeds: tuple[LevelCandidate, ...],
        *,
        processing_time: datetime | None,
    ) -> LevelGenerationResult:
        prefix_times = prefix_available_times(prefix)
        candidates: list[LevelCandidate] = []
        evaluated_touches = 0
        successful_reactions = 0
        rejected_attempts = 0
        for seed in seeds:
            evaluation = self._evaluate_seed(seed, prefix, prefix_times)
            evaluated_touches += evaluation.evaluated_touch_count
            successful_reactions += evaluation.successful_reaction_count
            rejected_attempts += evaluation.rejected_attempt_count
            if evaluation.candidate is not None:
                candidates.append(evaluation.candidate)
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
            for bar in all_bars
        )
        gap_count = _gap_count(prefix)
        warnings: list[str] = []
        if len(prefix) < len(all_bars):
            warnings.append(
                "causal prefix stopped at the first unavailable or incomplete bar"
            )
        if ignored:
            warnings.append(f"{ignored} incomplete source bar(s) blocked the prefix")
        if gap_count:
            warnings.append(
                f"{gap_count} source interval gap(s); separation counts actual bars only"
            )
        report = LevelGenerationReport(
            input_bar_count=len(all_bars),
            visible_bar_count=len(prefix),
            seed_count=len(data.seed_candidates),
            eligible_seed_count=len(seeds),
            periodic_high_count=0,
            periodic_low_count=0,
            reaction_candidate_count=len(ordered),
            ignored_incomplete_count=ignored,
            evaluated_touch_count=evaluated_touches,
            successful_reaction_count=successful_reactions,
            rejected_reaction_attempt_count=rejected_attempts,
            gap_count=gap_count,
            earliest_origin_time=min(origins) if origins else None,
            latest_origin_time=max(origins) if origins else None,
            earliest_confirm_time=min(confirms) if confirms else None,
            latest_confirm_time=max(confirms) if confirms else None,
            generator_id=self.generator_id,
            generator_version=self.generator_version,
            policy_id=self.config.policy_id,
            assumptions=(
                "each confirmed SWING seed is evaluated independently",
                "touch and separation count actual canonical bars without filling gaps",
                "touch bars cannot confirm their own rejection",
                "penetration wins over close-away when both occur on one confirmation bar",
                "the first unavailable or incomplete bar blocks every later bar",
                "candidate evidence freezes at the first min_reactions confirmation",
            ),
            warnings=tuple(warnings),
            errors=(),
        )
        return LevelGenerationResult(ordered, report)

    def _evaluate_seed(
        self,
        seed: LevelCandidate,
        bars: tuple[CanonicalBar, ...],
        prefix_times: tuple[datetime, ...],
    ) -> _SeedEvaluation:
        if seed.confirm_time is None:
            raise LevelGenerationError("validated seed unexpectedly has no confirm_time")
        price = seed.price_range.low
        zone = PriceRange(
            price - self.config.touch_tolerance,
            price + self.config.touch_tolerance,
        )
        active: _Attempt | None = None
        successes: list[_ReactionEvidence] = []
        evaluated_touches = 0
        rejected_attempts = 0
        last_success_touch_index: int | None = None

        for index, bar in enumerate(bars):
            eligible = (
                bar.timestamp > seed.origin_time
                and bar.available_time > seed.confirm_time
                and bar.is_complete
            )
            if active is not None:
                distance = index - active.touch_index
                if distance < 1:
                    continue
                if distance > self.config.confirmation_horizon_bars:
                    rejected_attempts += 1
                    active = None
                    continue
                if not eligible:
                    if distance == self.config.confirmation_horizon_bars:
                        rejected_attempts += 1
                        active = None
                    continue
                if _penetrates(
                    bar,
                    zone,
                    seed.boundary_side,
                    self.config.max_penetration,
                ):
                    rejected_attempts += 1
                    active = None
                    continue
                if _confirms_rejection(
                    bar,
                    zone,
                    seed.boundary_side,
                    self.config.min_reaction_distance,
                ):
                    confirm_time = max(seed.confirm_time, prefix_times[index])
                    evidence = _ReactionEvidence(
                        touch_index=active.touch_index,
                        confirmation_index=index,
                        touch_bar=active.touch_bar,
                        confirmation_bar=bar,
                        confirm_time=confirm_time,
                    )
                    successes.append(evidence)
                    last_success_touch_index = active.touch_index
                    active = None
                    if len(successes) == self.config.min_reactions:
                        candidate = self._candidate(seed, zone, tuple(successes))
                        return _SeedEvaluation(
                            candidate,
                            evaluated_touches,
                            len(successes),
                            rejected_attempts,
                        )
                    continue
                if distance == self.config.confirmation_horizon_bars:
                    rejected_attempts += 1
                    active = None
                continue

            if not eligible or not _touches(bar, zone):
                continue
            if (
                last_success_touch_index is not None
                and index - last_success_touch_index
                < self.config.min_separation_bars
            ):
                continue
            active = _Attempt(index, bar)
            evaluated_touches += 1
        return _SeedEvaluation(
            None,
            evaluated_touches,
            len(successes),
            rejected_attempts,
        )

    def _candidate(
        self,
        seed: LevelCandidate,
        zone: PriceRange,
        reactions: tuple[_ReactionEvidence, ...],
    ) -> LevelCandidate:
        if len(reactions) != self.config.min_reactions:
            raise LevelGenerationError("candidate evidence must equal min_reactions")
        final = reactions[-1]
        evidence = tuple(item.identity() for item in reactions)
        config_summary = {
            "confirmation_horizon_bars": self.config.confirmation_horizon_bars,
            "max_penetration": str(self.config.max_penetration),
            "min_reaction_distance": str(self.config.min_reaction_distance),
            "min_reactions": self.config.min_reactions,
            "min_separation_bars": self.config.min_separation_bars,
            "touch_tolerance": str(self.config.touch_tolerance),
        }
        identity = {
            "boundary_side": seed.boundary_side.value,
            "config": config_summary,
            "confirm_time": final.confirm_time.isoformat(),
            "generator_id": self.generator_id,
            "generator_version": self.generator_version,
            "market_role": seed.market_role.value,
            "policy_id": self.config.policy_id,
            "reactions": list(evidence),
            "scale": self.config.scale.to_dict(),
            "schema_version": self.config.schema_version,
            "seed_candidate_id": seed.candidate_id,
            "seed_origin_time": seed.origin_time.isoformat(),
            "seed_price": str(seed.price_range.low),
            "strict": self.config.strict,
            "symbol": seed.symbol,
            "timeframe": seed.timeframe.value,
            "zone": zone.to_dict(),
        }
        digest = sha256(_canonical_json(identity).encode("utf-8")).hexdigest()
        candidate_id = f"historical-reaction-v1-{digest}"
        seed_provenance_ref = (
            "provenance:v1:"
            f"{seed.provenance.source_module}:"
            f"{seed.provenance.source_version}:"
            f"{seed.provenance.source_object_id}"
        )
        parent_ids = [seed.candidate_id, seed_provenance_ref]
        for item in reactions:
            parent_ids.extend(
                (
                    canonical_bar_key(item.touch_bar),
                    canonical_bar_key(item.confirmation_bar),
                )
            )
        notes = [
            f"generator_id={self.generator_id}",
            f"generator_version={self.generator_version}",
            f"policy_id={self.config.policy_id}",
            f"seed_candidate_id={seed.candidate_id}",
            f"seed_provenance_ref={seed_provenance_ref}",
            f"config={_canonical_json(config_summary)}",
        ]
        notes.extend(
            f"reaction[{index}]={_canonical_json(item.identity())}"
            for index, item in enumerate(reactions)
        )
        provenance = ProvenanceRef(
            source_module=SOURCE_MODULE,
            source_version=self.generator_version,
            source_object_id=f"historical-reaction-evidence-v1-{digest}",
            policy_id=self.config.policy_id,
            parent_object_ids=tuple(dict.fromkeys(parent_ids)),
            notes=tuple(notes),
        )
        return LevelCandidate(
            candidate_id=candidate_id,
            symbol=seed.symbol,
            timeframe=seed.timeframe,
            scale=self.config.scale,
            price_range=zone,
            source_type=StructureSourceType.HISTORICAL_REACTION,
            boundary_side=seed.boundary_side,
            market_role=seed.market_role,
            confirmation_status=ConfirmationStatus.CONFIRMED,
            lifecycle_state=LifecycleState.CONFIRMED,
            origin_time=seed.origin_time,
            confirm_time=final.confirm_time,
            touch_count=self.config.min_reactions,
            last_touch_time=final.touch_bar.timestamp,
            last_touch_confirm_time=final.confirm_time,
            break_time=None,
            break_confirm_time=None,
            structure_family=STRUCTURE_FAMILY,
            provenance=provenance,
        )


def _touches(bar: CanonicalBar, zone: PriceRange) -> bool:
    return bar.high >= zone.low and bar.low <= zone.high


def _penetrates(
    bar: CanonicalBar,
    zone: PriceRange,
    side: BoundarySide,
    max_penetration: Decimal,
) -> bool:
    if side is BoundarySide.UPPER:
        return bar.high > zone.high + max_penetration
    return bar.low < zone.low - max_penetration


def _confirms_rejection(
    bar: CanonicalBar,
    zone: PriceRange,
    side: BoundarySide,
    distance: Decimal,
) -> bool:
    if side is BoundarySide.UPPER:
        return bar.close <= zone.low - distance
    return bar.close >= zone.high + distance


def _gap_count(bars: tuple[CanonicalBar, ...]) -> int:
    return sum(
        current.timestamp > previous.end_time
        for previous, current in zip(bars, bars[1:])
    )
