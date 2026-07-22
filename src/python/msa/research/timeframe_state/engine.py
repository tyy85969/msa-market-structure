"""Deterministic causal state selection over C-006A lifecycle snapshots."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Iterator, Mapping

from msa.domain import (
    BoundaryRef,
    BoundarySide,
    Direction,
    LifecycleState,
    ProvenanceRef,
    TimeframeState,
)
from msa.research.lifecycle import (
    LifecycleEvent,
    LifecycleSnapshot,
    LifecycleSubjectState,
)

from .contracts import (
    CROSSED_PAIR_OLDER_SIDE,
    SCHEMA_VERSION,
    SEMANTIC_FIELDS,
    BoundarySelectionExplanation,
    BoundarySelectionKey,
    TimeframeSelectionPolicy,
    TimeframeStateConfig,
    TimeframeStateEvent,
    TimeframeStateEventType,
    TimeframeStateHistory,
    TimeframeStateInput,
    TimeframeStateReport,
    TimeframeStateSnapshot,
    _direction_transition,
    _exact_payload,
)
from .errors import (
    TimeframeStateEngineError,
    TimeframeStateInputError,
    TimeframeStateSerializationError,
)
from .identity import _event_id, _snapshot_id, _state_id


SOURCE_MODULE = "msa.research.timeframe_state.engine"


def _processing_time(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise TimeframeStateInputError("processing_time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise TimeframeStateInputError("processing_time must be timezone-aware")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class _SelectedBoundary:
    state: LifecycleSubjectState
    boundary: BoundaryRef
    key: BoundarySelectionKey


@dataclass(frozen=True, slots=True)
class _PairSelection:
    raw_upper: _SelectedBoundary | None
    raw_lower: _SelectedBoundary | None
    upper: _SelectedBoundary | None
    lower: _SelectedBoundary | None
    crossing: bool
    retained_boundary_id: str | None
    dropped_boundary_id: str | None
    dropped_reason: str | None


@dataclass(frozen=True, slots=True)
class _PairIdentity:
    subject_ids: tuple[str, str]
    state_ids: tuple[str, str]
    boundary_ids: tuple[str, str]
    midpoints: tuple[Decimal, Decimal]


@dataclass(frozen=True, slots=True)
class _SelectionFacts:
    relevant: tuple[LifecycleSubjectState, ...]
    candidate_eligible: tuple[_SelectedBoundary, ...]
    confirmed_eligible: tuple[_SelectedBoundary, ...]
    candidate_pair: _PairSelection
    confirmed_pair: _PairSelection
    keys: tuple[BoundarySelectionKey, ...]
    excluded_broken_ids: tuple[str, ...]
    excluded_retired_ids: tuple[str, ...]


def _selection_key(state: LifecycleSubjectState) -> BoundarySelectionKey:
    return BoundarySelectionKey(
        state_confirm_time=state.state_confirm_time,
        structural_confirm_time=state.structural_confirm_time,
        subject_id=state.subject_ref.object_id,
        lifecycle_state_id=state.state_id,
    )


def _selected(state: LifecycleSubjectState) -> _SelectedBoundary:
    return _SelectedBoundary(state, state.to_boundary_ref(), _selection_key(state))


def _winner(
    values: tuple[_SelectedBoundary, ...], side: BoundarySide
) -> _SelectedBoundary | None:
    matching = tuple(
        sorted(
            (item for item in values if item.boundary.boundary_side is side),
            key=lambda item: item.key.comparison_tuple,
            reverse=True,
        )
    )
    return None if not matching else matching[0]


def _resolve_pair(
    values: tuple[_SelectedBoundary, ...]
) -> _PairSelection:
    raw_upper = _winner(values, BoundarySide.UPPER)
    raw_lower = _winner(values, BoundarySide.LOWER)
    if raw_upper is None or raw_lower is None:
        return _PairSelection(
            raw_upper,
            raw_lower,
            raw_upper,
            raw_lower,
            False,
            None,
            None,
            None,
        )
    crossing = (
        raw_lower.boundary.price_range.high
        > raw_upper.boundary.price_range.low
    )
    if not crossing:
        return _PairSelection(
            raw_upper,
            raw_lower,
            raw_upper,
            raw_lower,
            False,
            None,
            None,
            None,
        )
    if raw_upper.key.comparison_tuple > raw_lower.key.comparison_tuple:
        retained, dropped = raw_upper, raw_lower
        upper, lower = raw_upper, None
    else:
        retained, dropped = raw_lower, raw_upper
        upper, lower = None, raw_lower
    return _PairSelection(
        raw_upper,
        raw_lower,
        upper,
        lower,
        True,
        retained.boundary.object_id,
        dropped.boundary.object_id,
        CROSSED_PAIR_OLDER_SIDE,
    )


def _pair_identity(pair: _PairSelection) -> _PairIdentity | None:
    if pair.upper is None or pair.lower is None:
        return None
    return _PairIdentity(
        subject_ids=(
            pair.upper.state.subject_ref.object_id,
            pair.lower.state.subject_ref.object_id,
        ),
        state_ids=(pair.upper.state.state_id, pair.lower.state.state_id),
        boundary_ids=(
            pair.upper.boundary.object_id,
            pair.lower.boundary.object_id,
        ),
        midpoints=(
            (
                pair.upper.boundary.price_range.low
                + pair.upper.boundary.price_range.high
            )
            / Decimal("2"),
            (
                pair.lower.boundary.price_range.low
                + pair.lower.boundary.price_range.high
            )
            / Decimal("2"),
        ),
    )


def _pair_values(
    pair: _PairIdentity | None,
) -> tuple[
    tuple[str, ...],
    tuple[str, ...],
    tuple[str, ...],
    tuple[Decimal, ...],
]:
    if pair is None:
        return (), (), (), ()
    return pair.subject_ids, pair.state_ids, pair.boundary_ids, pair.midpoints


def _direction(
    previous_direction: Direction,
    last_complete_pair: _PairIdentity | None,
    previous_current_pair: _PairIdentity | None,
    current_pair: _PairIdentity | None,
) -> tuple[Direction, Direction, bool, str]:
    last_values = _pair_values(last_complete_pair)
    previous_values = _pair_values(previous_current_pair)
    current_values = _pair_values(current_pair)
    return _direction_transition(
        previous_direction,
        last_values[0],
        last_values[3],
        previous_values[0],
        previous_values[3],
        current_values[0],
        current_values[3],
    )


def _semantic_values(
    direction: Direction,
    candidate_pair: _PairSelection,
    confirmed_pair: _PairSelection,
) -> dict[str, object]:
    return {
        "direction": direction,
        "candidate_upper_boundary": (
            None if candidate_pair.upper is None else candidate_pair.upper.boundary
        ),
        "candidate_lower_boundary": (
            None if candidate_pair.lower is None else candidate_pair.lower.boundary
        ),
        "confirmed_upper_boundary": (
            None if confirmed_pair.upper is None else confirmed_pair.upper.boundary
        ),
        "confirmed_lower_boundary": (
            None if confirmed_pair.lower is None else confirmed_pair.lower.boundary
        ),
        "forming_candidate_ids": (),
    }


def _semantic_from_state(state: TimeframeState) -> dict[str, object]:
    return {field_name: getattr(state, field_name) for field_name in SEMANTIC_FIELDS}


def _changed_fields(
    previous: TimeframeState | None, current: dict[str, object]
) -> tuple[str, ...]:
    if previous is None:
        return SEMANTIC_FIELDS
    prior = _semantic_from_state(previous)
    return tuple(
        field_name
        for field_name in SEMANTIC_FIELDS
        if prior[field_name] != current[field_name]
    )


def _event_type(
    previous: TimeframeState | None, changed: tuple[str, ...]
) -> TimeframeStateEventType:
    if previous is None:
        return TimeframeStateEventType.INITIALIZED
    direction_changed = "direction" in changed
    boundary_changed = any(
        field_name != "direction" for field_name in changed
    )
    if direction_changed and boundary_changed:
        return TimeframeStateEventType.STATE_CHANGED
    if direction_changed:
        return TimeframeStateEventType.DIRECTION_CHANGED
    return TimeframeStateEventType.SELECTION_CHANGED


def _raw_state_id(value: _SelectedBoundary | None) -> str | None:
    return None if value is None else value.state.state_id


def _raw_boundary_id(value: _SelectedBoundary | None) -> str | None:
    return None if value is None else value.boundary.object_id


def _selected_ids(
    candidate_pair: _PairSelection, confirmed_pair: _PairSelection
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    values = tuple(
        item
        for item in (
            candidate_pair.upper,
            candidate_pair.lower,
            confirmed_pair.upper,
            confirmed_pair.lower,
        )
        if item is not None
    )
    state_ids = tuple(sorted({item.state.state_id for item in values}))
    event_ids = tuple(sorted({item.state.event_ids[-1] for item in values}))
    return state_ids, event_ids


@dataclass(frozen=True, slots=True)
class TimeframeStateEngine:
    config: TimeframeStateConfig
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.config, TimeframeStateConfig):
            raise TimeframeStateEngineError("config must be a TimeframeStateConfig")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise TimeframeStateEngineError(
                f"TimeframeStateEngine.schema_version must be {SCHEMA_VERSION}"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "config": self.config.to_dict(),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> TimeframeStateEngine:
        data = _exact_payload(payload, cls.__name__, {"config"})
        try:
            return cls(
                config=TimeframeStateConfig.from_dict(data["config"]),
                schema_version=data["schema_version"],
            )
        except TimeframeStateSerializationError:
            raise
        except (TypeError, ValueError, TimeframeStateEngineError) as exc:
            raise TimeframeStateSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc

    def build_as_of(
        self, data: TimeframeStateInput, processing_time: datetime
    ) -> TimeframeStateSnapshot:
        as_of = _processing_time(processing_time)
        self._validate_input(data)
        source_snapshots = data.lifecycle_history.snapshots
        if as_of < source_snapshots[0].as_of_time:
            raise TimeframeStateInputError(
                "processing_time cannot precede the first LifecycleSnapshot"
            )
        prefix = tuple(item for item in source_snapshots if item.as_of_time <= as_of)
        snapshot = self._build_prefix(prefix)
        if snapshot.as_of_time == as_of:
            return snapshot
        return self._observe(snapshot, as_of)

    def build_batch(self, data: TimeframeStateInput) -> TimeframeStateHistory:
        self._validate_input(data)
        snapshots = tuple(
            self.build_as_of(data, item.as_of_time)
            for item in data.lifecycle_history.snapshots
        )
        return TimeframeStateHistory(
            events=snapshots[-1].events,
            snapshots=snapshots,
            final_snapshot=snapshots[-1],
            config_snapshot=self.config,
        )

    def iter_events(
        self, data: TimeframeStateInput
    ) -> Iterator[TimeframeStateEvent]:
        yield from self.build_batch(data).events

    def _validate_input(self, data: TimeframeStateInput) -> None:
        if not isinstance(data, TimeframeStateInput):
            raise TimeframeStateInputError(
                "timeframe-state processing requires TimeframeStateInput"
            )
        if not isinstance(data.lifecycle_history.snapshots, tuple) or not data.lifecycle_history.snapshots:
            raise TimeframeStateInputError("LifecycleHistory must not be empty")

    def _relevant_states(
        self, snapshot: LifecycleSnapshot
    ) -> tuple[LifecycleSubjectState, ...]:
        return tuple(
            sorted(
                (
                    state
                    for state in snapshot.states
                    if state.subject_ref.symbol == self.config.symbol
                    and state.subject_ref.timeframe is self.config.target_timeframe
                    and state.subject_ref.scale == self.config.target_scale
                ),
                key=lambda state: (
                    state.state_confirm_time,
                    state.structural_confirm_time,
                    state.subject_ref.object_id,
                    state.state_id,
                ),
                reverse=True,
            )
        )

    def _selection(self, snapshot: LifecycleSnapshot) -> _SelectionFacts:
        relevant = self._relevant_states(snapshot)
        candidate_states = {
            LifecycleState.FRESH,
            LifecycleState.TESTED,
            LifecycleState.WEAKENED,
            LifecycleState.FLIPPED,
        }
        confirmed_states = {
            LifecycleState.TESTED,
            LifecycleState.WEAKENED,
            LifecycleState.FLIPPED,
        }
        candidate = tuple(
            sorted(
                (_selected(item) for item in relevant if item.lifecycle_state in candidate_states),
                key=lambda item: item.key.comparison_tuple,
                reverse=True,
            )
        )
        confirmed = tuple(
            sorted(
                (_selected(item) for item in relevant if item.lifecycle_state in confirmed_states),
                key=lambda item: item.key.comparison_tuple,
                reverse=True,
            )
        )
        keys = tuple(
            sorted(
                (_selection_key(item) for item in relevant),
                key=lambda item: item.comparison_tuple,
                reverse=True,
            )
        )
        return _SelectionFacts(
            relevant=relevant,
            candidate_eligible=candidate,
            confirmed_eligible=confirmed,
            candidate_pair=_resolve_pair(candidate),
            confirmed_pair=_resolve_pair(confirmed),
            keys=keys,
            excluded_broken_ids=tuple(
                sorted(
                    item.subject_ref.object_id
                    for item in relevant
                    if item.lifecycle_state is LifecycleState.BROKEN
                )
            ),
            excluded_retired_ids=tuple(
                sorted(
                    item.subject_ref.object_id
                    for item in relevant
                    if item.lifecycle_state is LifecycleState.RETIRED
                )
            ),
        )

    def _source_event_ids(
        self,
        snapshot: LifecycleSnapshot,
        previous_snapshot: LifecycleSnapshot | None,
    ) -> tuple[str, ...]:
        previous_count = 0 if previous_snapshot is None else len(previous_snapshot.events)
        new_events = snapshot.events[previous_count:]
        state_by_subject = {
            item.subject_ref.object_id: item for item in snapshot.states
        }
        relevant_events: list[LifecycleEvent] = []
        for event in new_events:
            state = state_by_subject.get(event.subject_id)
            if state is None:
                continue
            subject = state.subject_ref
            if (
                subject.symbol == self.config.symbol
                and subject.timeframe is self.config.target_timeframe
                and subject.scale == self.config.target_scale
            ):
                relevant_events.append(event)
        return tuple(sorted(item.event_id for item in relevant_events))

    def _explanation(
        self,
        facts: _SelectionFacts,
        previous_pair: _PairIdentity | None,
        current_pair: _PairIdentity | None,
        previous_direction: Direction,
        raw_direction: Direction,
        final_direction: Direction,
        pair_position_changed: bool,
        rationale: str,
    ) -> BoundarySelectionExplanation:
        previous_values = _pair_values(previous_pair)
        current_values = _pair_values(current_pair)
        selected_state_ids, selected_event_ids = _selected_ids(
            facts.candidate_pair, facts.confirmed_pair
        )
        return BoundarySelectionExplanation(
            target_symbol=self.config.symbol,
            target_timeframe=self.config.target_timeframe,
            target_scale=self.config.target_scale,
            selection_policy=self.config.selection_policy,
            relevant_subject_ids=tuple(
                item.subject_ref.object_id for item in facts.relevant
            ),
            candidate_eligible_subject_ids=tuple(
                item.state.subject_ref.object_id
                for item in facts.candidate_eligible
            ),
            confirmed_eligible_subject_ids=tuple(
                item.state.subject_ref.object_id
                for item in facts.confirmed_eligible
            ),
            excluded_broken_ids=facts.excluded_broken_ids,
            excluded_retired_ids=facts.excluded_retired_ids,
            raw_candidate_upper_state_id=_raw_state_id(
                facts.candidate_pair.raw_upper
            ),
            raw_candidate_lower_state_id=_raw_state_id(
                facts.candidate_pair.raw_lower
            ),
            raw_confirmed_upper_state_id=_raw_state_id(
                facts.confirmed_pair.raw_upper
            ),
            raw_confirmed_lower_state_id=_raw_state_id(
                facts.confirmed_pair.raw_lower
            ),
            raw_candidate_upper_boundary_id=_raw_boundary_id(
                facts.candidate_pair.raw_upper
            ),
            raw_candidate_lower_boundary_id=_raw_boundary_id(
                facts.candidate_pair.raw_lower
            ),
            raw_confirmed_upper_boundary_id=_raw_boundary_id(
                facts.confirmed_pair.raw_upper
            ),
            raw_confirmed_lower_boundary_id=_raw_boundary_id(
                facts.confirmed_pair.raw_lower
            ),
            candidate_crossing_conflict=facts.candidate_pair.crossing,
            confirmed_crossing_conflict=facts.confirmed_pair.crossing,
            candidate_retained_boundary_id=(
                facts.candidate_pair.retained_boundary_id
            ),
            candidate_dropped_boundary_id=(
                facts.candidate_pair.dropped_boundary_id
            ),
            candidate_dropped_reason=facts.candidate_pair.dropped_reason,
            confirmed_retained_boundary_id=(
                facts.confirmed_pair.retained_boundary_id
            ),
            confirmed_dropped_boundary_id=(
                facts.confirmed_pair.dropped_boundary_id
            ),
            confirmed_dropped_reason=facts.confirmed_pair.dropped_reason,
            selected_candidate_upper_id=_raw_boundary_id(
                facts.candidate_pair.upper
            ),
            selected_candidate_lower_id=_raw_boundary_id(
                facts.candidate_pair.lower
            ),
            selected_confirmed_upper_id=_raw_boundary_id(
                facts.confirmed_pair.upper
            ),
            selected_confirmed_lower_id=_raw_boundary_id(
                facts.confirmed_pair.lower
            ),
            selected_lifecycle_state_ids=selected_state_ids,
            selected_lifecycle_event_ids=selected_event_ids,
            stable_comparison_keys=facts.keys,
            previous_complete_pair_subject_ids=previous_values[0],
            current_complete_pair_subject_ids=current_values[0],
            previous_complete_pair_state_ids=previous_values[1],
            current_complete_pair_state_ids=current_values[1],
            previous_complete_pair_boundary_ids=previous_values[2],
            current_complete_pair_boundary_ids=current_values[2],
            previous_pair_midpoints=previous_values[3],
            current_pair_midpoints=current_values[3],
            pair_position_changed=pair_position_changed,
            raw_direction=raw_direction,
            previous_direction=previous_direction,
            final_direction=final_direction,
            direction_rationale=rationale,
        )

    def _state_id(
        self,
        semantic: dict[str, object],
        origin_time: datetime,
        confirm_time: datetime,
    ) -> str:
        return _state_id(
            engine_id=self.config.engine_id,
            engine_version=self.config.engine_version,
            policy_id=self.config.policy_id,
            symbol=self.config.symbol,
            target_timeframe=self.config.target_timeframe.value,
            target_scale=self.config.target_scale.to_dict(),
            selection_policy=self.config.selection_policy.value,
            direction=semantic["direction"].value,  # type: ignore[union-attr]
            candidate_upper_boundary=self._boundary_payload(
                semantic["candidate_upper_boundary"]
            ),
            candidate_lower_boundary=self._boundary_payload(
                semantic["candidate_lower_boundary"]
            ),
            confirmed_upper_boundary=self._boundary_payload(
                semantic["confirmed_upper_boundary"]
            ),
            confirmed_lower_boundary=self._boundary_payload(
                semantic["confirmed_lower_boundary"]
            ),
            forming_candidate_ids=semantic["forming_candidate_ids"],  # type: ignore[arg-type]
            origin_time=origin_time,
            confirm_time=confirm_time,
            domain_schema_version=2,
            engine_schema_version=SCHEMA_VERSION,
        )

    @staticmethod
    def _boundary_payload(value: object) -> object:
        return None if value is None else value.to_dict()  # type: ignore[attr-defined]

    def _event_id(
        self,
        *,
        previous_state_id: str | None,
        current_state_id: str,
        event_type: TimeframeStateEventType,
        event_confirm_time: datetime,
        previous_direction: Direction | None,
        current_direction: Direction,
        changed_fields: tuple[str, ...],
        source_lifecycle_snapshot_id: str,
        source_lifecycle_event_ids: tuple[str, ...],
        prior_event_id: str | None,
    ) -> str:
        return _event_id(
            engine_id=self.config.engine_id,
            engine_version=self.config.engine_version,
            policy_id=self.config.policy_id,
            previous_state_id=previous_state_id,
            current_state_id=current_state_id,
            event_type=event_type.value,
            event_confirm_time=event_confirm_time,
            previous_direction=(
                None if previous_direction is None else previous_direction.value
            ),
            current_direction=current_direction.value,
            changed_fields=changed_fields,
            source_lifecycle_snapshot_id=source_lifecycle_snapshot_id,
            source_lifecycle_event_ids=source_lifecycle_event_ids,
            prior_event_id=prior_event_id,
            schema_version=SCHEMA_VERSION,
        )

    def _report(
        self,
        *,
        as_of_time: datetime,
        lifecycle_snapshot_count: int,
        facts: _SelectionFacts,
        direction: Direction,
        events: tuple[TimeframeStateEvent, ...],
    ) -> TimeframeStateReport:
        candidate_upper_count = sum(
            item.boundary.boundary_side is BoundarySide.UPPER
            for item in facts.candidate_eligible
        )
        confirmed_upper_count = sum(
            item.boundary.boundary_side is BoundarySide.UPPER
            for item in facts.confirmed_eligible
        )
        event_times = tuple(item.event_confirm_time for item in events)
        warnings = [
            "LATEST_CAUSAL is a local research baseline, not final boundary ranking",
            "crossed raw pairs retain only the newer side without fallback search",
        ]
        if not facts.relevant:
            warnings.append("zero relevant lifecycle subjects in the target context")
        return TimeframeStateReport(
            as_of_time=as_of_time,
            lifecycle_snapshot_count=lifecycle_snapshot_count,
            relevant_subject_count=len(facts.relevant),
            candidate_eligible_count=len(facts.candidate_eligible),
            confirmed_eligible_count=len(facts.confirmed_eligible),
            upper_candidate_count=candidate_upper_count,
            lower_candidate_count=len(facts.candidate_eligible) - candidate_upper_count,
            upper_confirmed_count=confirmed_upper_count,
            lower_confirmed_count=len(facts.confirmed_eligible) - confirmed_upper_count,
            excluded_broken_count=len(facts.excluded_broken_ids),
            excluded_retired_count=len(facts.excluded_retired_ids),
            candidate_pair_crossing_conflict=facts.candidate_pair.crossing,
            confirmed_pair_crossing_conflict=facts.confirmed_pair.crossing,
            selected_candidate_upper_id=_raw_boundary_id(facts.candidate_pair.upper),
            selected_candidate_lower_id=_raw_boundary_id(facts.candidate_pair.lower),
            selected_confirmed_upper_id=_raw_boundary_id(facts.confirmed_pair.upper),
            selected_confirmed_lower_id=_raw_boundary_id(facts.confirmed_pair.lower),
            complete_candidate_pair=(
                facts.candidate_pair.upper is not None
                and facts.candidate_pair.lower is not None
            ),
            complete_confirmed_pair=(
                facts.confirmed_pair.upper is not None
                and facts.confirmed_pair.lower is not None
            ),
            direction=direction,
            state_event_count=len(events),
            earliest_state_event_time=min(event_times),
            latest_state_event_time=max(event_times),
            engine_id=self.config.engine_id,
            engine_version=self.config.engine_version,
            policy_id=self.config.policy_id,
            assumptions=(
                "only LifecycleSnapshot prefixes at or before AsOfTime are consumed",
                "Candidate eligibility is FRESH TESTED WEAKENED or FLIPPED",
                "Confirmed eligibility is TESTED WEAKENED or FLIPPED",
                "Direction uses only complete Confirmed Pairs and exact Decimal midpoints",
                "forming_candidate_ids remain empty in C-006B",
            ),
            warnings=tuple(warnings),
            errors=(),
        )

    def _build_prefix(
        self, source_snapshots: tuple[LifecycleSnapshot, ...]
    ) -> TimeframeStateSnapshot:
        previous_source: LifecycleSnapshot | None = None
        previous_snapshot: TimeframeStateSnapshot | None = None
        last_complete_pair: _PairIdentity | None = None
        previous_current_pair: _PairIdentity | None = None
        events: list[TimeframeStateEvent] = []
        for index, source_snapshot in enumerate(source_snapshots, start=1):
            facts = self._selection(source_snapshot)
            current_pair = _pair_identity(facts.confirmed_pair)
            previous_direction = (
                Direction.UNKNOWN
                if previous_snapshot is None
                else previous_snapshot.state.direction
            )
            final_direction, raw_direction, pair_changed, rationale = _direction(
                previous_direction,
                last_complete_pair,
                previous_current_pair,
                current_pair,
            )
            explanation = self._explanation(
                facts,
                last_complete_pair,
                current_pair,
                previous_direction,
                raw_direction,
                final_direction,
                pair_changed,
                rationale,
            )
            semantic = _semantic_values(
                final_direction, facts.candidate_pair, facts.confirmed_pair
            )
            previous_state = (
                None if previous_snapshot is None else previous_snapshot.state
            )
            changed = _changed_fields(previous_state, semantic)
            source_event_ids = self._source_event_ids(
                source_snapshot, previous_source
            )
            if changed:
                event_time = source_snapshot.as_of_time
                state_id = self._state_id(semantic, event_time, event_time)
                kind = _event_type(previous_state, changed)
                prior_event_id = None if not events else events[-1].event_id
                event_id = self._event_id(
                    previous_state_id=(
                        None if previous_state is None else previous_state.state_id
                    ),
                    current_state_id=state_id,
                    event_type=kind,
                    event_confirm_time=event_time,
                    previous_direction=(
                        None if previous_state is None else previous_state.direction
                    ),
                    current_direction=final_direction,
                    changed_fields=changed,
                    source_lifecycle_snapshot_id=source_snapshot.snapshot_id,
                    source_lifecycle_event_ids=source_event_ids,
                    prior_event_id=prior_event_id,
                )
                event_parents = (
                    source_snapshot.snapshot_id,
                    *source_event_ids,
                    *(() if prior_event_id is None else (prior_event_id,)),
                )
                event_provenance = ProvenanceRef(
                    source_module=SOURCE_MODULE,
                    source_version=self.config.engine_version,
                    source_object_id=event_id,
                    policy_id=self.config.policy_id,
                    parent_object_ids=event_parents,
                    notes=(
                        f"event_type={kind.value}",
                        f"engine_id={self.config.engine_id}",
                    ),
                )
                selected_state_ids, selected_lifecycle_event_ids = _selected_ids(
                    facts.candidate_pair, facts.confirmed_pair
                )
                state_provenance = ProvenanceRef(
                    source_module=SOURCE_MODULE,
                    source_version=self.config.engine_version,
                    source_object_id=state_id,
                    policy_id=self.config.policy_id,
                    parent_object_ids=(
                        source_snapshot.snapshot_id,
                        *selected_state_ids,
                        *selected_lifecycle_event_ids,
                        event_id,
                    ),
                    notes=(
                        f"engine_id={self.config.engine_id}",
                        f"direction={final_direction.value}",
                    ),
                )
                state = TimeframeState(
                    state_id=state_id,
                    state_version=self.config.engine_version,
                    symbol=self.config.symbol,
                    timeframe=self.config.target_timeframe,
                    scale=self.config.target_scale,
                    direction=final_direction,
                    origin_time=event_time,
                    confirm_time=event_time,
                    as_of_time=event_time,
                    candidate_upper_boundary=semantic[
                        "candidate_upper_boundary"
                    ],
                    candidate_lower_boundary=semantic[
                        "candidate_lower_boundary"
                    ],
                    confirmed_upper_boundary=semantic[
                        "confirmed_upper_boundary"
                    ],
                    confirmed_lower_boundary=semantic[
                        "confirmed_lower_boundary"
                    ],
                    forming_candidate_ids=(),
                    provenance=state_provenance,
                )
                event = TimeframeStateEvent(
                    event_id=event_id,
                    previous_state_id=(
                        None if previous_state is None else previous_state.state_id
                    ),
                    current_state_id=state_id,
                    event_type=kind,
                    event_confirm_time=event_time,
                    first_seen_time=event_time,
                    previous_direction=(
                        None if previous_state is None else previous_state.direction
                    ),
                    current_direction=final_direction,
                    changed_fields=changed,
                    candidate_upper_id=_raw_boundary_id(facts.candidate_pair.upper),
                    candidate_lower_id=_raw_boundary_id(facts.candidate_pair.lower),
                    confirmed_upper_id=_raw_boundary_id(facts.confirmed_pair.upper),
                    confirmed_lower_id=_raw_boundary_id(facts.confirmed_pair.lower),
                    source_lifecycle_snapshot_id=source_snapshot.snapshot_id,
                    source_lifecycle_event_ids=source_event_ids,
                    prior_event_id=prior_event_id,
                    provenance=event_provenance,
                )
                events.append(event)
            else:
                if previous_state is None:
                    raise TimeframeStateEngineError(
                        "first LifecycleSnapshot must initialize timeframe state"
                    )
                state = replace(previous_state, as_of_time=source_snapshot.as_of_time)
            event_tuple = tuple(events)
            report = self._report(
                as_of_time=source_snapshot.as_of_time,
                lifecycle_snapshot_count=index,
                facts=facts,
                direction=state.direction,
                events=event_tuple,
            )
            snapshot_id = self._snapshot_id(
                source_snapshot.snapshot_id,
                source_snapshot.as_of_time,
                state,
                explanation,
                event_tuple,
                report,
            )
            previous_snapshot = TimeframeStateSnapshot(
                snapshot_id=snapshot_id,
                as_of_time=source_snapshot.as_of_time,
                source_lifecycle_snapshot_id=source_snapshot.snapshot_id,
                state=state,
                explanation=explanation,
                events=event_tuple,
                report=report,
                config_snapshot=self.config,
            )
            if current_pair is not None:
                last_complete_pair = current_pair
            previous_current_pair = current_pair
            previous_source = source_snapshot
        if previous_snapshot is None:
            raise TimeframeStateEngineError(
                "timeframe-state prefix must contain a LifecycleSnapshot"
            )
        return previous_snapshot

    def _snapshot_id(
        self,
        source_lifecycle_snapshot_id: str,
        as_of_time: datetime,
        state: TimeframeState,
        explanation: BoundarySelectionExplanation,
        events: tuple[TimeframeStateEvent, ...],
        report: TimeframeStateReport,
    ) -> str:
        return _snapshot_id(
            config=self.config.to_dict(),
            source_lifecycle_snapshot_id=source_lifecycle_snapshot_id,
            as_of_time=as_of_time,
            state=state.to_dict(),
            explanation=explanation.to_dict(),
            events=tuple(item.to_dict() for item in events),
            report=report.to_dict(),
            schema_version=SCHEMA_VERSION,
        )

    def _observe(
        self, snapshot: TimeframeStateSnapshot, as_of_time: datetime
    ) -> TimeframeStateSnapshot:
        state = replace(snapshot.state, as_of_time=as_of_time)
        report = replace(snapshot.report, as_of_time=as_of_time)
        snapshot_id = self._snapshot_id(
            snapshot.source_lifecycle_snapshot_id,
            as_of_time,
            state,
            snapshot.explanation,
            snapshot.events,
            report,
        )
        return TimeframeStateSnapshot(
            snapshot_id=snapshot_id,
            as_of_time=as_of_time,
            source_lifecycle_snapshot_id=snapshot.source_lifecycle_snapshot_id,
            state=state,
            explanation=snapshot.explanation,
            events=snapshot.events,
            report=report,
            config_snapshot=self.config,
        )
