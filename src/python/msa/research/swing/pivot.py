"""Causal confirmed Fractal/Pivot baseline for C-003A research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from typing import Iterator, Sequence

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

from .contracts import (
    PivotDetectorConfig,
    SwingDetectionEvent,
    SwingDetectionReport,
    SwingDetectionResult,
    TiePolicy,
)
from .errors import SwingDetectionError, SwingInputError


STRUCTURE_FAMILY = "confirmed-pivot-strict-v1"
SOURCE_MODULE = "msa.research.swing.pivot"
BAR_KEY_FORMAT_NOTE = (
    "canonical_bar_key=bar:v1:<canonical-json of symbol,timeframe,timestamp,source>"
)


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
        raise SwingDetectionError("unable to build canonical JSON identity") from exc


def canonical_bar_key(bar: CanonicalBar) -> str:
    """Return the documented finite stable reference for one canonical bar."""

    if not isinstance(bar, CanonicalBar):
        raise SwingDetectionError("canonical_bar_key requires a CanonicalBar")
    payload = {
        "source": bar.source,
        "symbol": bar.symbol,
        "timeframe": bar.timeframe.value,
        "timestamp": bar.timestamp.isoformat(),
    }
    return f"bar:v1:{_canonical_json(payload)}"


def _normalize_processing_time(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise SwingInputError("processing_time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise SwingInputError("processing_time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _validate_public_input(
    source: LoadResult,
    *,
    processing_time: datetime | None,
) -> tuple[CanonicalBar, ...]:
    if not isinstance(source, LoadResult):
        raise SwingInputError(
            "Swing detection requires a C-001 LoadResult public input"
        )
    if source.quality_report.has_errors:
        raise SwingInputError(
            "LoadResult.quality_report contains errors and is not eligible"
        )
    bars = source.bars
    if not isinstance(bars, tuple) or any(
        not isinstance(bar, CanonicalBar) for bar in bars
    ):
        raise SwingInputError("LoadResult.bars must be a CanonicalBar tuple")
    if source.accepted_row_count != len(bars):
        raise SwingInputError("LoadResult counts do not match canonical bars")

    config = source.source_config
    report = source.quality_report
    if report.source != config.source or report.timeframe is not config.timeframe:
        raise SwingInputError(
            "C-001 quality report identity does not match source configuration"
        )

    seen: set[tuple[str, object, datetime]] = set()
    previous: CanonicalBar | None = None
    for bar in bars:
        if bar.symbol != config.canonical_symbol:
            raise SwingInputError("mixed symbol or symbol/config mismatch")
        if bar.timeframe is not config.timeframe:
            raise SwingInputError("mixed timeframe or timeframe/config mismatch")
        if bar.source != config.source:
            raise SwingInputError("mixed source or source/config mismatch")
        if not _valid_ohlc(bar):
            raise SwingInputError("invalid OHLC entered Swing detection")
        key = (bar.symbol, bar.timeframe, bar.timestamp)
        if key in seen:
            raise SwingInputError("duplicate canonical bar key")
        seen.add(key)
        if previous is not None:
            if bar.timestamp < previous.timestamp:
                raise SwingInputError("canonical bars are out of order")
            if bar.timestamp == previous.timestamp:
                raise SwingInputError("duplicate canonical bar timestamp")
            if bar.timestamp < previous.end_time:
                raise SwingInputError("canonical bar intervals overlap")
        previous = bar

        participates = processing_time is None or bar.available_time <= processing_time
        if participates and not bar.is_complete:
            raise SwingInputError(
                "incomplete source bar cannot enter confirmed Pivot detection"
            )
    return bars


def _valid_ohlc(bar: CanonicalBar) -> bool:
    values = (bar.open, bar.high, bar.low, bar.close)
    return (
        all(isinstance(item, Decimal) and item.is_finite() for item in values)
        and bar.high >= bar.low
        and bar.high >= bar.open
        and bar.high >= bar.close
        and bar.low <= bar.open
        and bar.low <= bar.close
    )


@dataclass(frozen=True, slots=True)
class PivotDetector:
    """Deterministic strict Pivot baseline; not a selected production model."""

    config: PivotDetectorConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, PivotDetectorConfig):
            raise SwingDetectionError("config must be a PivotDetectorConfig")

    @property
    def detector_id(self) -> str:
        return self.config.detector_id

    @property
    def detector_version(self) -> str:
        return self.config.detector_version

    def detect_batch(self, source: LoadResult) -> SwingDetectionResult:
        bars = _validate_public_input(source, processing_time=None)
        if any(not bar.is_complete for bar in bars):
            raise SwingInputError(
                "incomplete source bar cannot enter confirmed Pivot detection"
            )
        visible = tuple(True for _ in bars)
        return self._detect(source, bars, visible)

    def detect_as_of(
        self, source: LoadResult, processing_time: datetime
    ) -> SwingDetectionResult:
        normalized = _normalize_processing_time(processing_time)
        bars = _validate_public_input(source, processing_time=normalized)
        visible = tuple(
            bar.is_complete and bar.available_time <= normalized for bar in bars
        )
        return self._detect(source, bars, visible)

    def iter_events(self, source: LoadResult) -> Iterator[SwingDetectionEvent]:
        for candidate in self.detect_batch(source).candidates:
            if candidate.confirm_time is None:
                raise SwingDetectionError("confirmed batch candidate has no time")
            yield SwingDetectionEvent(candidate.confirm_time, candidate)

    def _detect(
        self,
        source: LoadResult,
        bars: tuple[CanonicalBar, ...],
        visible: tuple[bool, ...],
    ) -> SwingDetectionResult:
        left = self.config.left_bars
        right = self.config.right_bars
        candidates: list[LevelCandidate] = []
        evaluated = 0
        rejected = 0
        leading = 0
        trailing = 0

        for index, center in enumerate(bars):
            if not visible[index]:
                continue
            left_start = index - left
            right_end = index + right
            if left_start < 0 or not all(visible[left_start:index]):
                leading += 1
                continue
            if right_end >= len(bars) or not all(
                visible[index + 1 : right_end + 1]
            ):
                trailing += 1
                continue

            window = bars[left_start : right_end + 1]
            evaluated += 1
            other_bars = window[:left] + window[left + 1 :]
            is_high = self._is_high(center, other_bars)
            is_low = self._is_low(center, other_bars)
            if not is_high and not is_low:
                rejected += 1
            if is_high:
                candidates.append(
                    self._candidate(center, window, BoundarySide.UPPER)
                )
            if is_low:
                candidates.append(
                    self._candidate(center, window, BoundarySide.LOWER)
                )

        ordered = tuple(
            sorted(
                candidates,
                key=lambda item: (item.confirm_time, item.candidate_id),
            )
        )
        visible_count = sum(visible)
        gap_count = self._visible_gap_count(source, bars, visible)
        origins = tuple(item.origin_time for item in ordered)
        confirms = tuple(
            item.confirm_time for item in ordered if item.confirm_time is not None
        )
        warnings: list[str] = []
        if gap_count:
            warnings.append(
                f"{gap_count} source interval gap(s); windows count actual bars only"
            )
        if leading:
            warnings.append(f"{leading} visible bar(s) lack complete left context")
        if trailing:
            warnings.append(f"{trailing} visible bar(s) remain trailing/forming")
        report = SwingDetectionReport(
            input_bar_count=visible_count,
            evaluated_center_count=evaluated,
            confirmed_high_count=sum(
                item.boundary_side is BoundarySide.UPPER for item in ordered
            ),
            confirmed_low_count=sum(
                item.boundary_side is BoundarySide.LOWER for item in ordered
            ),
            leading_incomplete_count=leading,
            trailing_incomplete_count=trailing,
            gap_count=gap_count,
            rejected_window_count=rejected,
            earliest_origin_time=min(origins) if origins else None,
            latest_origin_time=max(origins) if origins else None,
            earliest_confirm_time=min(confirms) if confirms else None,
            latest_confirm_time=max(confirms) if confirms else None,
            detector_id=self.detector_id,
            detector_version=self.detector_version,
            policy_id=self.config.policy_id,
            assumptions=(
                "left_bars/right_bars count actual canonical-bar sequence members",
                "confirm_time=max(window member available_time)",
                "STRICT uses strict inequality and rejects equal extrema",
                "as-of uses fixed membership from a prevalidated LoadResult",
            ),
            warnings=tuple(warnings),
            errors=(),
        )
        return SwingDetectionResult(ordered, report)

    def _is_high(
        self, center: CanonicalBar, others: Sequence[CanonicalBar]
    ) -> bool:
        if self.config.tie_policy is not TiePolicy.STRICT:
            raise SwingDetectionError("unsupported tie policy reached detection")
        return all(center.high > item.high for item in others)

    def _is_low(
        self, center: CanonicalBar, others: Sequence[CanonicalBar]
    ) -> bool:
        if self.config.tie_policy is not TiePolicy.STRICT:
            raise SwingDetectionError("unsupported tie policy reached detection")
        return all(center.low < item.low for item in others)

    def _candidate(
        self,
        center: CanonicalBar,
        window: Sequence[CanonicalBar],
        side: BoundarySide,
    ) -> LevelCandidate:
        if not window:
            raise SwingDetectionError("cannot generate identity for an empty window")
        price = center.high if side is BoundarySide.UPPER else center.low
        confirm_time = max(item.available_time for item in window)
        window_refs = tuple(canonical_bar_key(item) for item in window)
        window_facts = tuple(
            {
                "available_time": item.available_time.isoformat(),
                "bar_key": reference,
                "high": str(item.high),
                "low": str(item.low),
            }
            for item, reference in zip(window, window_refs)
        )
        candidate_id = self._candidate_id(
            center,
            price,
            side,
            confirm_time,
            window_facts,
        )
        source_object_id = self._source_object_id(window_facts, side)
        provenance = ProvenanceRef(
            source_module=SOURCE_MODULE,
            source_version=self.detector_version,
            source_object_id=source_object_id,
            policy_id=self.config.policy_id,
            parent_object_ids=window_refs,
            notes=(
                BAR_KEY_FORMAT_NOTE,
                f"detector_id={self.detector_id}",
                f"detector_version={self.detector_version}",
                f"policy_id={self.config.policy_id}",
                f"tie_policy={self.config.tie_policy.value}",
                f"source_timeframe={center.timeframe.value}",
                f"window=left:{self.config.left_bars},right:{self.config.right_bars}",
                f"boundary_side={side.value}",
            ),
        )
        return LevelCandidate(
            candidate_id=candidate_id,
            symbol=center.symbol,
            timeframe=center.timeframe,
            scale=self.config.scale,
            price_range=PriceRange(price, price),
            source_type=StructureSourceType.SWING,
            boundary_side=side,
            market_role=(
                MarketRole.RESISTANCE
                if side is BoundarySide.UPPER
                else MarketRole.SUPPORT
            ),
            confirmation_status=ConfirmationStatus.CONFIRMED,
            lifecycle_state=LifecycleState.CONFIRMED,
            origin_time=center.timestamp,
            confirm_time=confirm_time,
            touch_count=0,
            last_touch_time=None,
            last_touch_confirm_time=None,
            break_time=None,
            break_confirm_time=None,
            structure_family=STRUCTURE_FAMILY,
            provenance=provenance,
        )

    def _candidate_id(
        self,
        center: CanonicalBar,
        price: Decimal,
        side: BoundarySide,
        confirm_time: datetime,
        window_facts: tuple[dict[str, str], ...],
    ) -> str:
        identity = {
            "boundary_side": side.value,
            "confirm_time": confirm_time.isoformat(),
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "left_bars": self.config.left_bars,
            "origin_time": center.timestamp.isoformat(),
            "policy_id": self.config.policy_id,
            "price": str(price),
            "right_bars": self.config.right_bars,
            "scale": self.config.scale.to_dict(),
            "schema_version": self.config.schema_version,
            "strict": self.config.strict,
            "source": center.source,
            "symbol": center.symbol,
            "tie_policy": self.config.tie_policy.value,
            "timeframe": center.timeframe.value,
            "window_facts": list(window_facts),
        }
        digest = sha256(_canonical_json(identity).encode("utf-8")).hexdigest()
        if not digest:
            raise SwingDetectionError("unable to generate deterministic candidate ID")
        return f"swing-pivot-v1-{digest}"

    def _source_object_id(
        self,
        window_facts: tuple[dict[str, str], ...],
        side: BoundarySide,
    ) -> str:
        identity = {
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "policy_id": self.config.policy_id,
            "side": side.value,
            "tie_policy": self.config.tie_policy.value,
            "window_facts": list(window_facts),
        }
        digest = sha256(_canonical_json(identity).encode("utf-8")).hexdigest()
        if not digest:
            raise SwingDetectionError("unable to generate stable source object ID")
        return f"pivot-window-v1-{digest}"

    @staticmethod
    def _visible_gap_count(
        source: LoadResult,
        bars: tuple[CanonicalBar, ...],
        visible: tuple[bool, ...],
    ) -> int:
        if all(visible):
            return source.quality_report.gap_count
        return sum(
            visible[index - 1]
            and visible[index]
            and bars[index].timestamp > bars[index - 1].end_time
            for index in range(1, len(bars))
        )
