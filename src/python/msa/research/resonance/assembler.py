"""Causal multi-context resonance-frame assembly without scoring or ranking."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Mapping

from msa.data import CanonicalBar, Timeframe
from msa.domain import (
    BoundarySide,
    Direction,
    LifecycleState,
    ProvenanceRef,
)
from msa.research.lifecycle import LifecycleSnapshot, LifecycleSubjectState
from msa.research.timeframe_state import (
    TimeframeStateHistory,
    TimeframeStateSnapshot,
)

from .contracts import (
    SCHEMA_VERSION,
    ReferencePriceSnapshot,
    ResonanceContext,
    ResonanceContextState,
    ResonanceEvidence,
    ResonanceEvidenceTier,
    ResonanceFrame,
    ResonanceFrameConfig,
    ResonanceFrameHistory,
    ResonanceFrameInput,
    ResonanceFrameReport,
    _context_key,
    _evidence_key,
    _exact_payload,
)
from .errors import (
    ResonanceFrameConfigurationError,
    ResonanceFrameEngineError,
    ResonanceFrameInputError,
    ResonanceFrameSerializationError,
)
from .identity import _evidence_id, _frame_id, _reference_id


_EFFECTIVE_STATES = {
    LifecycleState.FRESH,
    LifecycleState.TESTED,
    LifecycleState.WEAKENED,
    LifecycleState.FLIPPED,
}


def _processing_time(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise ResonanceFrameInputError("processing_time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise ResonanceFrameInputError("processing_time must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class ResonanceFrameAssembler:
    config: ResonanceFrameConfig
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise ResonanceFrameConfigurationError(
                f"ResonanceFrameAssembler.schema_version must be {SCHEMA_VERSION}"
            )
        if not isinstance(self.config, ResonanceFrameConfig):
            raise ResonanceFrameConfigurationError(
                "ResonanceFrameAssembler.config must be a ResonanceFrameConfig"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "config": self.config.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ResonanceFrameAssembler:
        data = _exact_payload(payload, cls.__name__, {"config"})
        try:
            return cls(
                config=ResonanceFrameConfig.from_dict(data["config"]),
                schema_version=data["schema_version"],
            )
        except ResonanceFrameSerializationError:
            raise
        except (TypeError, ValueError) as exc:
            raise ResonanceFrameSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc

    def build_as_of(
        self, data: ResonanceFrameInput, processing_time: datetime
    ) -> ResonanceFrame:
        self._validate_input(data)
        as_of = _processing_time(processing_time)
        lifecycle = self._lifecycle_snapshot(data, as_of)
        histories = self._histories_by_context(data)
        context_states, timeframe_snapshots = self._context_states(
            histories, lifecycle
        )
        reference_bar = self._reference_bar(data, as_of)
        reference = self._reference_snapshot(reference_bar)
        evidence, broken, retired = self._evidence(
            lifecycle, context_states
        )
        report = self._report(
            as_of, context_states, evidence, broken, retired, reference
        )
        frame_id = _frame_id(
            config=self.config.to_dict(),
            as_of_time=as_of.isoformat(),
            source_lifecycle_snapshot_id=lifecycle.snapshot_id,
            source_lifecycle_snapshot_time=lifecycle.as_of_time.isoformat(),
            reference_price_id=reference.reference_id,
            context_state_ids=tuple(
                item.timeframe_state_id for item in context_states
            ),
            evidence_ids=tuple(item.evidence_id for item in evidence),
            excluded_broken_subject_ids=broken,
            excluded_retired_subject_ids=retired,
            schema_version=SCHEMA_VERSION,
        )
        parents = tuple(sorted({
            lifecycle.snapshot_id,
            reference.reference_id,
            *(item.snapshot_id for item in timeframe_snapshots),
            *(item.lifecycle_state_id for item in evidence),
        }))
        provenance = ProvenanceRef(
            source_module="msa.research.resonance.assembler",
            source_version=self.config.engine_version,
            source_object_id=frame_id,
            policy_id=self.config.policy_id,
            parent_object_ids=parents,
            notes=(
                f"engine_id={self.config.engine_id}",
                "complete lifecycle evidence universe",
                "no score, ranking, or ActiveBox",
            ),
        )
        return ResonanceFrame(
            frame_id=frame_id,
            as_of_time=as_of,
            source_lifecycle_snapshot_id=lifecycle.snapshot_id,
            source_lifecycle_snapshot_time=lifecycle.as_of_time,
            reference_price=reference,
            context_states=context_states,
            evidence=evidence,
            excluded_broken_subject_ids=broken,
            excluded_retired_subject_ids=retired,
            report=report,
            config_snapshot=self.config,
            provenance=provenance,
        )

    def build_batch(self, data: ResonanceFrameInput) -> ResonanceFrameHistory:
        self._validate_input(data)
        schedule = self.default_schedule(data)
        frames = tuple(self.build_as_of(data, item) for item in schedule)
        return ResonanceFrameHistory(
            frames=frames,
            final_frame=frames[-1],
            config_snapshot=self.config,
        )

    def default_schedule(self, data: ResonanceFrameInput) -> tuple[datetime, ...]:
        self._validate_input(data)
        lifecycle_times = {
            item.as_of_time for item in data.lifecycle_history.snapshots
        }
        price_times = {
            item.available_time for item in data.reference_price_data.bars
        }
        start = max(min(lifecycle_times), min(price_times))
        schedule = tuple(sorted(
            item for item in lifecycle_times | price_times if item >= start
        ))
        if not schedule:
            raise ResonanceFrameInputError("no common causal frame time exists")
        return schedule

    def _validate_input(self, data: ResonanceFrameInput) -> None:
        if not isinstance(data, ResonanceFrameInput):
            raise ResonanceFrameInputError(
                "assembler requires ResonanceFrameInput"
            )
        histories = data.timeframe_state_histories
        if len(histories) != len(self.config.contexts):
            raise ResonanceFrameInputError(
                "TimeframeStateHistory count must equal configured context count"
            )
        seen: set[ResonanceContext] = set()
        for history in histories:
            cfg = history.config_snapshot
            context = ResonanceContext(cfg.target_timeframe, cfg.target_scale)
            if context in seen:
                raise ResonanceFrameInputError(
                    "duplicate TimeframeState context history"
                )
            seen.add(context)
            if context not in self.config.contexts:
                raise ResonanceFrameInputError(
                    "TimeframeStateHistory timeframe/scale does not match config"
                )
            if cfg.symbol != self.config.symbol:
                raise ResonanceFrameInputError(
                    "TimeframeStateHistory symbol does not match config"
                )
        if seen != set(self.config.contexts):
            raise ResonanceFrameInputError(
                "TimeframeState histories must exactly cover config contexts"
            )
        reference = data.reference_price_data
        if reference.quality_report.has_errors:
            raise ResonanceFrameInputError(
                "reference LoadResult must be error-free"
            )
        if not reference.bars:
            raise ResonanceFrameInputError(
                "reference LoadResult must contain at least one bar"
            )
        if (
            reference.source_config.canonical_symbol != self.config.symbol
            or reference.source_config.timeframe
            is not self.config.reference_price_timeframe
        ):
            raise ResonanceFrameInputError(
                "reference source config symbol/timeframe does not match config"
            )
        for bar in reference.bars:
            if (
                not isinstance(bar, CanonicalBar)
                or bar.symbol != self.config.symbol
                or bar.timeframe is not self.config.reference_price_timeframe
            ):
                raise ResonanceFrameInputError(
                    "reference bars must match configured symbol/timeframe"
                )
            if not bar.is_complete:
                raise ResonanceFrameInputError(
                    "reference bars must all be completed CanonicalBar values"
                )

    def _histories_by_context(
        self, data: ResonanceFrameInput
    ) -> dict[ResonanceContext, TimeframeStateHistory]:
        return {
            ResonanceContext(
                item.config_snapshot.target_timeframe,
                item.config_snapshot.target_scale,
            ): item
            for item in data.timeframe_state_histories
        }

    @staticmethod
    def _lifecycle_snapshot(
        data: ResonanceFrameInput, as_of: datetime
    ) -> LifecycleSnapshot:
        visible = tuple(
            item for item in data.lifecycle_history.snapshots
            if item.as_of_time <= as_of
        )
        if not visible:
            raise ResonanceFrameInputError(
                "processing_time precedes the first LifecycleSnapshot"
            )
        return max(visible, key=lambda item: item.as_of_time)

    def _context_states(
        self,
        histories: dict[ResonanceContext, TimeframeStateHistory],
        lifecycle: LifecycleSnapshot,
    ) -> tuple[
        tuple[ResonanceContextState, ...],
        tuple[TimeframeStateSnapshot, ...],
    ]:
        states: list[ResonanceContextState] = []
        snapshots: list[TimeframeStateSnapshot] = []
        for context in self.config.contexts:
            matches = tuple(
                item for item in histories[context].snapshots
                if item.as_of_time == lifecycle.as_of_time
                and item.source_lifecycle_snapshot_id == lifecycle.snapshot_id
            )
            if len(matches) != 1:
                raise ResonanceFrameInputError(
                    "each context requires exactly one snapshot aligned to the selected LifecycleSnapshot"
                )
            snapshot = matches[0]
            state = snapshot.state
            states.append(ResonanceContextState(
                context=context,
                timeframe_snapshot_id=snapshot.snapshot_id,
                timeframe_snapshot_as_of_time=snapshot.as_of_time,
                timeframe_state_id=state.state_id,
                direction=state.direction,
                state_confirm_time=state.confirm_time,
                state_origin_time=state.origin_time,
                source_lifecycle_snapshot_id=snapshot.source_lifecycle_snapshot_id,
            ))
            snapshots.append(snapshot)
        return tuple(states), tuple(snapshots)

    @staticmethod
    def _reference_bar(
        data: ResonanceFrameInput, as_of: datetime
    ) -> CanonicalBar:
        visible = tuple(
            item for item in data.reference_price_data.bars
            if item.available_time <= as_of
        )
        if not visible:
            raise ResonanceFrameInputError(
                "processing_time precedes the first available reference bar"
            )
        return max(
            visible,
            key=lambda item: (
                item.available_time, item.timestamp, item.end_time,
                item.source, str(item.close),
            ),
        )

    @staticmethod
    def _reference_snapshot(bar: CanonicalBar) -> ReferencePriceSnapshot:
        reference_id = _reference_id(bar.to_dict(), schema_version=SCHEMA_VERSION)
        return ReferencePriceSnapshot(
            reference_id=reference_id,
            symbol=bar.symbol,
            timeframe=bar.timeframe,
            price=bar.close,
            bar_timestamp=bar.timestamp,
            bar_end_time=bar.end_time,
            available_time=bar.available_time,
            source=bar.source,
            source_timezone=bar.source_timezone,
        )

    def _evidence(
        self,
        lifecycle: LifecycleSnapshot,
        context_states: tuple[ResonanceContextState, ...],
    ) -> tuple[tuple[ResonanceEvidence, ...], tuple[str, ...], tuple[str, ...]]:
        direction_by_context = {
            item.context: item.direction for item in context_states
        }
        configured = set(self.config.contexts)
        evidence: list[ResonanceEvidence] = []
        broken: list[str] = []
        retired: list[str] = []
        for state in lifecycle.states:
            subject = state.subject_ref
            context = ResonanceContext(subject.timeframe, subject.scale)
            if subject.symbol != self.config.symbol or context not in configured:
                continue
            if state.lifecycle_state is LifecycleState.BROKEN:
                broken.append(subject.object_id)
                continue
            if state.lifecycle_state is LifecycleState.RETIRED:
                retired.append(subject.object_id)
                continue
            if state.lifecycle_state not in _EFFECTIVE_STATES:
                continue
            evidence.append(
                self._evidence_from_state(
                    state, context, direction_by_context[context]
                )
            )
        ordered = tuple(sorted(evidence, key=_evidence_key))
        if len({item.subject_id for item in ordered}) != len(ordered):
            raise ResonanceFrameEngineError(
                "selected LifecycleSnapshot produced duplicate subject evidence"
            )
        if len({item.lifecycle_state_id for item in ordered}) != len(ordered):
            raise ResonanceFrameEngineError(
                "selected LifecycleSnapshot produced duplicate lifecycle-state evidence"
            )
        if len({item.evidence_id for item in ordered}) != len(ordered):
            raise ResonanceFrameEngineError(
                "selected LifecycleSnapshot produced duplicate evidence IDs"
            )
        return ordered, tuple(sorted(broken)), tuple(sorted(retired))

    def _evidence_from_state(
        self,
        state: LifecycleSubjectState,
        context: ResonanceContext,
        direction: Direction,
    ) -> ResonanceEvidence:
        boundary = state.to_boundary_ref()
        tier = (
            ResonanceEvidenceTier.CANDIDATE
            if state.lifecycle_state is LifecycleState.FRESH
            else ResonanceEvidenceTier.CONFIRMED
        )
        event_id = state.event_ids[-1]
        evidence_id = _evidence_id(
            subject_id=state.subject_ref.object_id,
            lifecycle_state_id=state.state_id,
            lifecycle_event_id=event_id,
            boundary=boundary.to_dict(),
            tier=tier.value,
            context=context.to_dict(),
            direction=direction.value,
            lifecycle_state=state.lifecycle_state.value,
            structural_confirm_time=state.structural_confirm_time.isoformat(),
            state_confirm_time=state.state_confirm_time.isoformat(),
            touch_count=state.test_count,
            source_types=tuple(item.value for item in boundary.source_types),
            structure_families=boundary.structure_families,
            schema_version=SCHEMA_VERSION,
        )
        provenance = ProvenanceRef(
            source_module="msa.research.resonance.assembler",
            source_version=self.config.engine_version,
            source_object_id=evidence_id,
            policy_id=self.config.policy_id,
            parent_object_ids=(
                state.subject_ref.object_id,
                state.state_id,
                event_id,
                boundary.object_id,
            ),
            notes=(
                f"engine_id={self.config.engine_id}",
                "one lifecycle state, one resonance evidence",
            ),
        )
        return ResonanceEvidence(
            evidence_id=evidence_id,
            subject_id=state.subject_ref.object_id,
            lifecycle_state_id=state.state_id,
            lifecycle_event_id=event_id,
            boundary=boundary,
            tier=tier,
            context=context,
            direction=direction,
            lifecycle_state=state.lifecycle_state,
            structural_confirm_time=state.structural_confirm_time,
            state_confirm_time=state.state_confirm_time,
            touch_count=state.test_count,
            source_types=boundary.source_types,
            structure_families=boundary.structure_families,
            provenance=provenance,
        )

    def _report(
        self,
        as_of: datetime,
        context_states: tuple[ResonanceContextState, ...],
        evidence: tuple[ResonanceEvidence, ...],
        broken: tuple[str, ...],
        retired: tuple[str, ...],
        reference: ReferencePriceSnapshot,
    ) -> ResonanceFrameReport:
        times = tuple(item.state_confirm_time for item in evidence)
        source_types = {item for value in evidence for item in value.source_types}
        families = {item for value in evidence for item in value.structure_families}
        return ResonanceFrameReport(
            as_of_time=as_of,
            context_count=len(context_states),
            evidence_count=len(evidence),
            candidate_evidence_count=sum(
                item.tier is ResonanceEvidenceTier.CANDIDATE for item in evidence
            ),
            confirmed_evidence_count=sum(
                item.tier is ResonanceEvidenceTier.CONFIRMED for item in evidence
            ),
            upper_evidence_count=sum(
                item.boundary.boundary_side is BoundarySide.UPPER
                for item in evidence
            ),
            lower_evidence_count=sum(
                item.boundary.boundary_side is BoundarySide.LOWER
                for item in evidence
            ),
            fresh_count=sum(
                item.lifecycle_state is LifecycleState.FRESH for item in evidence
            ),
            tested_count=sum(
                item.lifecycle_state is LifecycleState.TESTED for item in evidence
            ),
            weakened_count=sum(
                item.lifecycle_state is LifecycleState.WEAKENED for item in evidence
            ),
            flipped_count=sum(
                item.lifecycle_state is LifecycleState.FLIPPED for item in evidence
            ),
            excluded_broken_count=len(broken),
            excluded_retired_count=len(retired),
            distinct_source_type_count=len(source_types),
            distinct_structure_family_count=len(families),
            earliest_evidence_confirm_time=min(times) if times else None,
            latest_evidence_confirm_time=max(times) if times else None,
            reference_price=reference.price,
            reference_price_available_time=reference.available_time,
            reference_price_age_seconds=Decimal(
                str((as_of - reference.available_time).total_seconds())
            ),
            engine_id=self.config.engine_id,
            engine_version=self.config.engine_version,
            policy_id=self.config.policy_id,
            assumptions=(
                "LifecycleSnapshot states are the complete evidence universe",
                "TimeframeState supplies direction and exact lifecycle alignment only",
                "reference price is completed CanonicalBar.close visible by available_time",
                "C-007A performs no clustering, score, ranking, or ActiveBox selection",
            ),
            warnings=(),
            errors=(),
        )
