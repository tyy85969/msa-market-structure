"""Deterministic causal lifecycle state machine over canonical bar prefixes."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Any, Iterator, Mapping

from msa.data import CanonicalBar, LoadResult
from msa.domain import (
    BoundaryRef,
    BoundarySide,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
)
from msa.research.swing import canonical_bar_key

from .contracts import (
    SCHEMA_VERSION,
    LifecycleConfig,
    LifecycleEvent,
    LifecycleEventType,
    LifecycleHistory,
    LifecycleInput,
    LifecycleReport,
    LifecycleSnapshot,
    LifecycleSubjectState,
    RetirementReason,
    _exact_payload,
)
from .errors import (
    LifecycleEngineError,
    LifecycleInputError,
    LifecycleSerializationError,
)


SOURCE_MODULE = "msa.research.lifecycle.engine"


def _canonical_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True,
                          separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise LifecycleEngineError("unable to build canonical lifecycle JSON") from exc


def _digest(value: object) -> str:
    return sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _processing_time(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise LifecycleInputError("processing_time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise LifecycleInputError("processing_time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _opposite(side: BoundarySide, role: MarketRole) -> tuple[BoundarySide, MarketRole]:
    if side is BoundarySide.UPPER and role is MarketRole.RESISTANCE:
        return BoundarySide.LOWER, MarketRole.SUPPORT
    if side is BoundarySide.LOWER and role is MarketRole.SUPPORT:
        return BoundarySide.UPPER, MarketRole.RESISTANCE
    raise LifecycleEngineError("cannot flip an invalid side/role mapping")


@dataclass(slots=True)
class _WorkingState:
    subject: BoundaryRef
    lifecycle_state: LifecycleState
    effective_side: BoundarySide
    effective_role: MarketRole
    state_confirm_time: datetime
    test_count: int = 0
    last_test_time: datetime | None = None
    last_test_confirm_time: datetime | None = None
    last_test_bar_key: str | None = None
    last_test_index: int | None = None
    break_time: datetime | None = None
    break_confirm_time: datetime | None = None
    break_bar_key: str | None = None
    break_close: Decimal | None = None
    break_threshold: Decimal | None = None
    break_index: int | None = None
    flip_touch_time: datetime | None = None
    flip_touch_confirm_time: datetime | None = None
    flip_touch_bar_key: str | None = None
    flip_touch_index: int | None = None
    flipped_time: datetime | None = None
    flipped_confirm_time: datetime | None = None
    flip_confirmation_close: Decimal | None = None
    flip_confirmation_threshold: Decimal | None = None
    retired_time: datetime | None = None
    retired_confirm_time: datetime | None = None
    retirement_reason: RetirementReason | None = None
    events: list[LifecycleEvent] | None = None

    def __post_init__(self) -> None:
        if self.events is None:
            self.events = []


_EVENT_ORDER = {
    LifecycleEventType.ACTIVATED: "00",
    LifecycleEventType.TEST: "10",
    LifecycleEventType.WEAKENED: "11",
    LifecycleEventType.BROKEN: "20",
    LifecycleEventType.FLIP_TOUCH: "30",
    LifecycleEventType.FLIPPED: "40",
    LifecycleEventType.RETIRED: "50",
}


@dataclass(frozen=True, slots=True)
class LifecycleEngine:
    config: LifecycleConfig
    schema_version: int = SCHEMA_VERSION

    def __post_init__(self) -> None:
        if not isinstance(self.config, LifecycleConfig):
            raise LifecycleEngineError("config must be a LifecycleConfig")
        if isinstance(self.schema_version, bool) or self.schema_version != SCHEMA_VERSION:
            raise LifecycleEngineError(
                f"LifecycleEngine.schema_version must be {SCHEMA_VERSION}"
            )

    def to_dict(self) -> dict[str, object]:
        return {"schema_version": self.schema_version, "config": self.config.to_dict()}

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> LifecycleEngine:
        data = _exact_payload(payload, cls.__name__, {"config"})
        try:
            return cls(LifecycleConfig.from_dict(data["config"]), data["schema_version"])
        except LifecycleSerializationError:
            raise
        except (TypeError, ValueError, LifecycleEngineError) as exc:
            raise LifecycleSerializationError(
                f"invalid serialized {cls.__name__}: {exc}"
            ) from exc

    def build_as_of(self, data: LifecycleInput, processing_time: datetime) -> LifecycleSnapshot:
        as_of = _processing_time(processing_time)
        self._validate_input(data)
        bars, truncated = self._causal_prefix(data.source.bars, as_of)
        prefix_times: list[datetime] = []
        running: datetime | None = None
        for bar in bars:
            running = bar.available_time if running is None else max(running, bar.available_time)
            prefix_times.append(running)

        visible_subjects = tuple(sorted(
            (item for item in data.subjects if item.confirm_time <= as_of),
            key=lambda item: item.object_id,
        ))
        working: dict[str, _WorkingState] = {}
        for subject in visible_subjects:
            state = _WorkingState(subject, LifecycleState.FRESH,
                                  subject.boundary_side, subject.market_role,
                                  subject.confirm_time)
            self._emit(
                state, LifecycleEventType.ACTIVATED,
                LifecycleState.CONFIRMED, LifecycleState.FRESH,
                subject.confirm_time, subject.confirm_time,
                None, None,
                ("activation requires no price bar",), None,
            )
            working[subject.object_id] = state

        for index, bar in enumerate(bars):
            confirm_time = prefix_times[index]
            for subject_id in sorted(working):
                state = working[subject_id]
                if state.lifecycle_state in {LifecycleState.FLIPPED, LifecycleState.RETIRED}:
                    continue
                if bar.timestamp < state.subject.confirm_time:
                    continue
                if state.lifecycle_state is LifecycleState.BROKEN:
                    self._process_broken(state, bar, index, confirm_time)
                else:
                    self._process_active(state, bar, index, confirm_time)

        states = tuple(self._freeze_state(item, as_of) for item in working.values())
        events = tuple(sorted(
            (event for state in working.values() for event in state.events or []),
            key=lambda item: (item.event_confirm_time, item.subject_id, item.event_id),
        ))
        report = self._report(data, states, events, bars, truncated)
        identity = {
            "config": self.config.to_dict(), "as_of_time": as_of.isoformat(),
            "states": [item.to_dict() for item in states],
            "events": [item.to_dict() for item in events],
            "report": report.to_dict(), "schema_version": SCHEMA_VERSION,
        }
        return LifecycleSnapshot(
            snapshot_id=f"lifecycle-snapshot-v1-{_digest(identity)}",
            as_of_time=as_of, states=states, events=events,
            report=report, config_snapshot=self.config,
        )

    def build_batch(self, data: LifecycleInput) -> LifecycleHistory:
        self._validate_input(data)
        schedule = tuple(sorted(
            {item.confirm_time for item in data.subjects}
            | {bar.available_time for bar in data.source.bars}
        ))
        return self._history_for_schedule(data, schedule)

    def iter_events(self, data: LifecycleInput) -> Iterator[LifecycleEvent]:
        yield from self.build_batch(data).events

    def _history_for_schedule(
        self, data: LifecycleInput, schedule: tuple[datetime, ...]
    ) -> LifecycleHistory:
        if not schedule:
            raise LifecycleEngineError("lifecycle history schedule must not be empty")
        snapshots = tuple(self.build_as_of(data, time) for time in schedule)
        final = snapshots[-1]
        return LifecycleHistory(final.events, snapshots, final)

    def _validate_input(self, data: LifecycleInput) -> None:
        if not isinstance(data, LifecycleInput):
            raise LifecycleInputError("lifecycle processing requires LifecycleInput")
        source = data.source
        if source.source_config.strict is not True:
            raise LifecycleInputError("source must use C-001 strict=True validation")
        if source.quality_report.has_errors:
            raise LifecycleInputError("source quality_report contains errors")
        if any((source.quality_report.duplicate_count,
                source.quality_report.conflicting_duplicate_count,
                source.quality_report.out_of_order_count,
                source.quality_report.overlap_count)):
            raise LifecycleInputError("source quality report contains sequence defects")
        if source.source_config.timeframe is not self.config.observation_timeframe:
            raise LifecycleInputError("source timeframe does not match observation_timeframe")
        if source.quality_report.timeframe is not self.config.observation_timeframe:
            raise LifecycleInputError("quality-report timeframe does not match config")
        if not source.bars:
            raise LifecycleInputError("source bars must not be empty")
        first = source.bars[0]
        if source.source_config.canonical_symbol != first.symbol:
            raise LifecycleInputError("source canonical symbol does not match bars")
        if source.source_config.source != first.source:
            raise LifecycleInputError("source_config source does not match bars")
        if source.quality_report.source != first.source:
            raise LifecycleInputError("source quality-report identity is inconsistent")
        seen: set[datetime] = set()
        for index, bar in enumerate(source.bars):
            if not isinstance(bar, CanonicalBar):
                raise LifecycleInputError("source bars must be CanonicalBar values")
            if (
                bar.symbol != first.symbol
                or bar.timeframe is not first.timeframe
                or bar.source != first.source
                or bar.source_timezone != first.source_timezone
                or bar.volume_type is not first.volume_type
                or bar.boundary_policy != first.boundary_policy
            ):
                raise LifecycleInputError("source bars must have one canonical identity")
            if bar.timeframe is not self.config.observation_timeframe:
                raise LifecycleInputError("bar timeframe does not match observation_timeframe")
            if bar.timestamp in seen:
                raise LifecycleInputError("source contains duplicate timestamps")
            seen.add(bar.timestamp)
            if index:
                previous = source.bars[index - 1]
                if bar.timestamp <= previous.timestamp:
                    raise LifecycleInputError("source timestamps must be strictly ascending")
                if bar.timestamp < previous.end_time:
                    raise LifecycleInputError("source intervals overlap")
        for subject in data.subjects:
            if subject.symbol != first.symbol:
                raise LifecycleInputError("subject symbol must match source symbol")
            test_low = subject.price_range.low - self.config.test_tolerance
            flip_low = subject.price_range.low - self.config.flip_tolerance
            try:
                PriceRange(test_low, subject.price_range.high + self.config.test_tolerance)
                PriceRange(flip_low, subject.price_range.high + self.config.flip_tolerance)
            except ValueError as exc:
                raise LifecycleInputError("configuration creates an invalid price zone") from exc
            if test_low < 0 or flip_low < 0:
                raise LifecycleInputError("configuration creates a negative price-zone bound")

    @staticmethod
    def _causal_prefix(
        bars: tuple[CanonicalBar, ...], processing_time: datetime
    ) -> tuple[tuple[CanonicalBar, ...], bool]:
        visible: list[CanonicalBar] = []
        for bar in bars:
            if not bar.is_complete or bar.available_time > processing_time:
                break
            visible.append(bar)
        return tuple(visible), len(visible) != len(bars)

    def _emit(
        self,
        state: _WorkingState,
        event_type: LifecycleEventType,
        from_state: LifecycleState,
        to_state: LifecycleState,
        origin_time: datetime,
        confirm_time: datetime,
        bar: CanonicalBar | None,
        source_price: Decimal | None,
        evidence: tuple[str, ...],
        retirement_reason: RetirementReason | None,
    ) -> LifecycleEvent:
        prior = () if not state.events else (state.events[-1].event_id,)
        bar_key = None if bar is None else canonical_bar_key(bar)
        effective_side = state.effective_side
        effective_role = state.effective_role
        if to_state is LifecycleState.FLIPPED:
            effective_side, effective_role = _opposite(
                state.subject.boundary_side, state.subject.market_role
            )
        identity = {
            "engine": self.config.to_dict(), "subject": state.subject.to_dict(),
            "event_type": event_type.value, "from_state": from_state.value,
            "to_state": to_state.value, "event_origin_time": origin_time.isoformat(),
            "event_confirm_time": confirm_time.isoformat(), "source_bar_key": bar_key,
            "source_price": None if source_price is None else str(source_price),
            "test_count": state.test_count,
            "effective_boundary_side": effective_side.value,
            "effective_market_role": effective_role.value,
            "retirement_reason": None if retirement_reason is None else retirement_reason.value,
            "evidence": list(evidence), "prior_event_ids": list(prior),
            "schema_version": SCHEMA_VERSION,
        }
        digest = _digest(identity)
        origin_key = origin_time.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S.%fZ")
        event_id = (
            f"lifecycle-event-v1-{origin_key}-{_EVENT_ORDER[event_type]}-{digest}"
        )
        parents = (state.subject.object_id,) + prior
        provenance = ProvenanceRef(
            source_module=SOURCE_MODULE, source_version=self.config.engine_version,
            source_object_id=event_id, policy_id=self.config.policy_id,
            parent_object_ids=parents,
            notes=(f"event_type={event_type.value}", f"engine_id={self.config.engine_id}"),
        )
        event = LifecycleEvent(
            event_id=event_id, subject_id=state.subject.object_id,
            event_type=event_type, from_state=from_state, to_state=to_state,
            event_origin_time=origin_time, event_confirm_time=confirm_time,
            first_seen_time=confirm_time, source_bar_key=bar_key,
            source_price=source_price, test_count=state.test_count,
            effective_boundary_side=effective_side,
            effective_market_role=effective_role,
            retirement_reason=retirement_reason, evidence=evidence,
            prior_event_ids=prior, provenance=provenance,
        )
        state.events.append(event)  # type: ignore[union-attr]
        state.lifecycle_state = to_state
        state.state_confirm_time = confirm_time
        state.effective_side = effective_side
        state.effective_role = effective_role
        return event

    def _zones(self, subject: BoundaryRef) -> tuple[PriceRange, PriceRange]:
        return (
            PriceRange(subject.price_range.low - self.config.test_tolerance,
                       subject.price_range.high + self.config.test_tolerance),
            PriceRange(subject.price_range.low - self.config.flip_tolerance,
                       subject.price_range.high + self.config.flip_tolerance),
        )

    def _break_threshold(self, subject: BoundaryRef) -> Decimal:
        if subject.boundary_side is BoundarySide.UPPER:
            return subject.price_range.high + self.config.break_buffer
        return subject.price_range.low - self.config.break_buffer

    def _is_break(self, subject: BoundaryRef, bar: CanonicalBar) -> bool:
        threshold = self._break_threshold(subject)
        return bar.close >= threshold if subject.boundary_side is BoundarySide.UPPER else bar.close <= threshold

    def _process_active(
        self, state: _WorkingState, bar: CanonicalBar, index: int, confirm_time: datetime
    ) -> None:
        prior = state.lifecycle_state
        if self._is_break(state.subject, bar):
            threshold = self._break_threshold(state.subject)
            state.break_time = bar.timestamp
            state.break_confirm_time = confirm_time
            state.break_bar_key = canonical_bar_key(bar)
            state.break_close = bar.close
            state.break_threshold = threshold
            state.break_index = index
            self._emit(state, LifecycleEventType.BROKEN, prior, LifecycleState.BROKEN,
                       bar.timestamp, confirm_time, bar, bar.close,
                       (f"close={bar.close}", f"break_threshold={threshold}",
                        f"prior_state={prior.value}"), None)
            return
        test_zone, _ = self._zones(state.subject)
        touches = bar.high >= test_zone.low and bar.low <= test_zone.high
        separated = state.last_test_index is None or (
            index - state.last_test_index >= self.config.minimum_test_separation_bars
        )
        if not touches or not separated:
            return
        state.test_count += 1
        state.last_test_time = bar.timestamp
        state.last_test_confirm_time = confirm_time
        state.last_test_bar_key = canonical_bar_key(bar)
        state.last_test_index = index
        if prior is LifecycleState.FRESH:
            event_type, target = LifecycleEventType.TEST, LifecycleState.TESTED
        elif prior is LifecycleState.TESTED and state.test_count >= self.config.weakening_test_count:
            event_type, target = LifecycleEventType.WEAKENED, LifecycleState.WEAKENED
        else:
            event_type, target = LifecycleEventType.TEST, prior
        self._emit(state, event_type, prior, target, bar.timestamp, confirm_time,
                   bar, bar.close,
                   (f"test_zone_low={test_zone.low}", f"test_zone_high={test_zone.high}",
                    f"test_count={state.test_count}"), None)

    def _failed_break(self, state: _WorkingState, bar: CanonicalBar) -> tuple[bool, Decimal]:
        subject = state.subject
        if subject.boundary_side is BoundarySide.UPPER:
            threshold = subject.price_range.low - self.config.failed_break_retirement_buffer
            return bar.close <= threshold, threshold
        threshold = subject.price_range.high + self.config.failed_break_retirement_buffer
        return bar.close >= threshold, threshold

    def _flip_confirmation(self, state: _WorkingState, bar: CanonicalBar, zone: PriceRange) -> tuple[bool, Decimal]:
        if state.subject.boundary_side is BoundarySide.UPPER:
            threshold = zone.high + self.config.flip_confirmation_distance
            return bar.close >= threshold, threshold
        threshold = zone.low - self.config.flip_confirmation_distance
        return bar.close <= threshold, threshold

    def _retire(
        self, state: _WorkingState, bar: CanonicalBar, confirm_time: datetime,
        reason: RetirementReason, evidence: tuple[str, ...],
    ) -> None:
        state.retired_time = bar.timestamp
        state.retired_confirm_time = confirm_time
        state.retirement_reason = reason
        self._emit(state, LifecycleEventType.RETIRED, LifecycleState.BROKEN,
                   LifecycleState.RETIRED, bar.timestamp, confirm_time,
                   bar, bar.close, evidence, reason)

    def _process_broken(
        self, state: _WorkingState, bar: CanonicalBar, index: int, confirm_time: datetime
    ) -> None:
        if state.break_index is None or index <= state.break_index:
            return
        distance = index - state.break_index
        if distance > self.config.flip_horizon_bars:
            raise LifecycleEngineError("BROKEN state survived beyond its flip horizon")
        failed, failed_threshold = self._failed_break(state, bar)
        if failed:
            self._retire(state, bar, confirm_time, RetirementReason.FAILED_BREAK,
                         (f"close={bar.close}", f"failed_break_threshold={failed_threshold}"))
            return
        _, flip_zone = self._zones(state.subject)
        if state.flip_touch_index is None:
            touches = bar.high >= flip_zone.low and bar.low <= flip_zone.high
            if touches:
                state.flip_touch_time = bar.timestamp
                state.flip_touch_confirm_time = confirm_time
                state.flip_touch_bar_key = canonical_bar_key(bar)
                state.flip_touch_index = index
                self._emit(state, LifecycleEventType.FLIP_TOUCH,
                           LifecycleState.BROKEN, LifecycleState.BROKEN,
                           bar.timestamp, confirm_time, bar, bar.close,
                           (f"flip_zone_low={flip_zone.low}", f"flip_zone_high={flip_zone.high}"), None)
                if distance == self.config.flip_horizon_bars:
                    self._retire(state, bar, confirm_time,
                                 RetirementReason.FLIP_HORIZON_EXPIRED,
                                 (f"break_index={state.break_index}",
                                  f"horizon_bars={self.config.flip_horizon_bars}"))
                return
        elif index > state.flip_touch_index:
            confirmed, threshold = self._flip_confirmation(state, bar, flip_zone)
            if confirmed:
                state.flipped_time = bar.timestamp
                state.flipped_confirm_time = confirm_time
                state.flip_confirmation_close = bar.close
                state.flip_confirmation_threshold = threshold
                self._emit(state, LifecycleEventType.FLIPPED,
                           LifecycleState.BROKEN, LifecycleState.FLIPPED,
                           bar.timestamp, confirm_time, bar, bar.close,
                           (f"close={bar.close}", f"flip_confirmation_threshold={threshold}"), None)
                return
        if distance == self.config.flip_horizon_bars:
            self._retire(state, bar, confirm_time,
                         RetirementReason.FLIP_HORIZON_EXPIRED,
                         (f"break_index={state.break_index}",
                          f"horizon_bars={self.config.flip_horizon_bars}"))

    def _freeze_state(self, state: _WorkingState, as_of: datetime) -> LifecycleSubjectState:
        event_ids = tuple(item.event_id for item in state.events or [])
        facts = {
            "subject": state.subject.to_dict(), "lifecycle_state": state.lifecycle_state.value,
            "effective_side": state.effective_side.value, "effective_role": state.effective_role.value,
            "state_confirm_time": state.state_confirm_time.isoformat(),
            "test_count": state.test_count,
            "last_test_time": None if state.last_test_time is None else state.last_test_time.isoformat(),
            "last_test_confirm_time": None if state.last_test_confirm_time is None else state.last_test_confirm_time.isoformat(),
            "last_test_bar_key": state.last_test_bar_key,
            "break_time": None if state.break_time is None else state.break_time.isoformat(),
            "break_confirm_time": None if state.break_confirm_time is None else state.break_confirm_time.isoformat(),
            "break_bar_key": state.break_bar_key,
            "break_close": None if state.break_close is None else str(state.break_close),
            "break_threshold": None if state.break_threshold is None else str(state.break_threshold),
            "flip_touch_time": None if state.flip_touch_time is None else state.flip_touch_time.isoformat(),
            "flip_touch_confirm_time": None if state.flip_touch_confirm_time is None else state.flip_touch_confirm_time.isoformat(),
            "flip_touch_bar_key": state.flip_touch_bar_key,
            "flipped_time": None if state.flipped_time is None else state.flipped_time.isoformat(),
            "flipped_confirm_time": None if state.flipped_confirm_time is None else state.flipped_confirm_time.isoformat(),
            "flip_confirmation_close": None if state.flip_confirmation_close is None else str(state.flip_confirmation_close),
            "flip_confirmation_threshold": None if state.flip_confirmation_threshold is None else str(state.flip_confirmation_threshold),
            "retired_time": None if state.retired_time is None else state.retired_time.isoformat(),
            "retired_confirm_time": None if state.retired_confirm_time is None else state.retired_confirm_time.isoformat(),
            "retirement_reason": None if state.retirement_reason is None else state.retirement_reason.value,
            "event_ids": list(event_ids), "config": self.config.to_dict(),
            "schema_version": SCHEMA_VERSION,
        }
        state_id = f"lifecycle-state-v1-{_digest(facts)}"
        latest = event_ids[-1]
        provenance = ProvenanceRef(
            source_module=SOURCE_MODULE, source_version=self.config.engine_version,
            source_object_id=state_id, policy_id=self.config.policy_id,
            parent_object_ids=(state.subject.object_id, latest),
            notes=(f"engine_id={self.config.engine_id}",
                   f"lifecycle_state={state.lifecycle_state.value}"),
        )
        return LifecycleSubjectState(
            state_id=state_id, subject_ref=state.subject,
            lifecycle_state=state.lifecycle_state,
            effective_boundary_side=state.effective_side,
            effective_market_role=state.effective_role,
            structural_origin_time=state.subject.origin_time,
            structural_confirm_time=state.subject.confirm_time,
            state_confirm_time=state.state_confirm_time, as_of_time=as_of,
            test_count=state.test_count, last_test_time=state.last_test_time,
            last_test_confirm_time=state.last_test_confirm_time,
            last_test_bar_key=state.last_test_bar_key,
            break_time=state.break_time, break_confirm_time=state.break_confirm_time,
            break_bar_key=state.break_bar_key, break_close=state.break_close,
            break_threshold=state.break_threshold,
            flip_touch_time=state.flip_touch_time,
            flip_touch_confirm_time=state.flip_touch_confirm_time,
            flip_touch_bar_key=state.flip_touch_bar_key,
            flipped_time=state.flipped_time, flipped_confirm_time=state.flipped_confirm_time,
            flip_confirmation_close=state.flip_confirmation_close,
            flip_confirmation_threshold=state.flip_confirmation_threshold,
            retired_time=state.retired_time, retired_confirm_time=state.retired_confirm_time,
            retirement_reason=state.retirement_reason, event_ids=event_ids,
            provenance=provenance,
        )

    def _report(
        self, data: LifecycleInput, states: tuple[LifecycleSubjectState, ...],
        events: tuple[LifecycleEvent, ...], bars: tuple[CanonicalBar, ...], truncated: bool,
    ) -> LifecycleReport:
        counts = {item: sum(state.lifecycle_state is item for state in states) for item in (
            LifecycleState.FRESH, LifecycleState.TESTED, LifecycleState.WEAKENED,
            LifecycleState.BROKEN, LifecycleState.FLIPPED, LifecycleState.RETIRED)}
        event_times = tuple(item.event_confirm_time for item in events)
        gaps = sum(current.timestamp > previous.end_time for previous, current in zip(bars, bars[1:]))
        warnings = ["C-006A lifecycle thresholds are research baseline parameters"]
        if truncated:
            warnings.append("causal prefix stopped at the first unavailable or incomplete bar")
        if gaps:
            warnings.append("actual-bar separation crosses reported source gaps without synthesis")
        return LifecycleReport(
            input_subject_count=len(data.subjects), visible_subject_count=len(states),
            fresh_count=counts[LifecycleState.FRESH], tested_count=counts[LifecycleState.TESTED],
            weakened_count=counts[LifecycleState.WEAKENED], broken_count=counts[LifecycleState.BROKEN],
            flipped_count=counts[LifecycleState.FLIPPED], retired_count=counts[LifecycleState.RETIRED],
            test_event_count=sum(item.event_type is LifecycleEventType.TEST for item in events),
            break_event_count=sum(item.event_type is LifecycleEventType.BROKEN for item in events),
            flip_touch_event_count=sum(item.event_type is LifecycleEventType.FLIP_TOUCH for item in events),
            flip_event_count=sum(item.event_type is LifecycleEventType.FLIPPED for item in events),
            retirement_event_count=sum(item.event_type is LifecycleEventType.RETIRED for item in events),
            processed_bar_count=len(bars), causal_prefix_truncated=truncated,
            gap_count=gaps, earliest_event_confirm_time=min(event_times) if event_times else None,
            latest_event_confirm_time=max(event_times) if event_times else None,
            engine_id=self.config.engine_id, engine_version=self.config.engine_version,
            policy_id=self.config.policy_id,
            assumptions=(
                "subjects enter only at structural ConfirmTime",
                "monitoring uses complete bars whose timestamp is not before subject ConfirmTime",
                "break is checked before test on each bar",
                "bar event ConfirmTime is the cumulative prefix maximum availability",
                "flip touch and flip confirmation require distinct actual bars",
            ),
            warnings=tuple(warnings), errors=(),
        )
