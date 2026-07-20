"""Causal Decimal ATR turning-point baseline for C-003B research."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from enum import Enum
from hashlib import sha256
from typing import Any, Iterator, Mapping, Sequence

from msa.data import CanonicalBar, LoadResult, validate_bar_sequence
from msa.domain import (
    BoundarySide,
    ConfirmationStatus,
    LevelCandidate,
    LifecycleState,
    MarketRole,
    PriceRange,
    ProvenanceRef,
    ScaleDescriptor,
    StructureSourceType,
)

from .contracts import (
    SCHEMA_VERSION,
    SwingDetectionEvent,
    SwingDetectionReport,
    SwingDetectionResult,
    _require_exact_payload,
    _require_text,
)
from .errors import SwingConfigurationError, SwingDetectionError, SwingInputError
from .pivot import _canonical_json, _valid_ohlc, canonical_bar_key


STRUCTURE_FAMILY = "atr-turning-point-sma-v1"
SOURCE_MODULE = "msa.research.swing.atr_reversal"
SAME_BAR_POLICY = "check-pre-bar-extreme-before-current-extreme-update"


class _Trend(str, Enum):
    UNKNOWN = "UNKNOWN"
    UP = "UP"
    DOWN = "DOWN"


def _decimal_text(field_name: str, value: object) -> Decimal:
    if not isinstance(value, str):
        raise SwingConfigurationError(f"{field_name} must be a Decimal string")
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise SwingConfigurationError(
            f"{field_name} must be a Decimal string"
        ) from exc
    if not parsed.is_finite():
        raise SwingConfigurationError(f"{field_name} must be finite")
    return parsed


@dataclass(frozen=True, slots=True)
class AtrReversalDetectorConfig:
    """Explicit immutable configuration for the SMA-ATR turning baseline."""

    detector_id: str
    detector_version: str
    atr_period: int
    reversal_multiplier: Decimal
    scale: ScaleDescriptor
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
        if (
            isinstance(self.atr_period, bool)
            or not isinstance(self.atr_period, int)
            or self.atr_period < 1
        ):
            raise SwingConfigurationError("atr_period must be >= 1")
        if not isinstance(self.reversal_multiplier, Decimal):
            raise SwingConfigurationError(
                "reversal_multiplier must be an exact Decimal"
            )
        if (
            not self.reversal_multiplier.is_finite()
            or self.reversal_multiplier <= 0
        ):
            raise SwingConfigurationError(
                "reversal_multiplier must be finite and > 0"
            )
        if not isinstance(self.scale, ScaleDescriptor):
            raise SwingConfigurationError(
                "scale must be an explicit ScaleDescriptor supplied by the caller"
            )
        if not isinstance(self.strict, bool):
            raise SwingConfigurationError("strict must be a bool")
        if self.strict is not True:
            raise SwingConfigurationError(
                "AtrReversalDetectorConfig.strict must be True; "
                "C-003B supports strict mode only"
            )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "atr_period": self.atr_period,
            "reversal_multiplier": str(self.reversal_multiplier),
            "scale": self.scale.to_dict(),
            "policy_id": self.policy_id,
            "strict": self.strict,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AtrReversalDetectorConfig:
        fields = {
            "detector_id",
            "detector_version",
            "atr_period",
            "reversal_multiplier",
            "scale",
            "policy_id",
            "strict",
        }
        data = _require_exact_payload(payload, cls.__name__, fields)
        try:
            scale = ScaleDescriptor.from_dict(data["scale"])
        except (TypeError, ValueError) as exc:
            raise SwingConfigurationError("invalid scale payload") from exc
        return cls(
            detector_id=data["detector_id"],
            detector_version=data["detector_version"],
            atr_period=data["atr_period"],
            reversal_multiplier=_decimal_text(
                "reversal_multiplier", data["reversal_multiplier"]
            ),
            scale=scale,
            policy_id=data["policy_id"],
            strict=data["strict"],
            schema_version=data["schema_version"],
        )


def _normalize_processing_time(value: object) -> datetime:
    if not isinstance(value, datetime):
        raise SwingInputError("processing_time must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise SwingInputError("processing_time must be timezone-aware")
    return value.astimezone(timezone.utc)


def _validate_stateful_input(source: LoadResult) -> tuple[CanonicalBar, ...]:
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
    return bars


def _causal_prefix(
    bars: Sequence[CanonicalBar], processing_time: datetime | None
) -> tuple[CanonicalBar, ...]:
    if processing_time is None:
        if any(not bar.is_complete for bar in bars):
            raise SwingInputError(
                "incomplete source bar cannot enter confirmed state detection"
            )
        return tuple(bars)

    prefix: list[CanonicalBar] = []
    for bar in bars:
        if not bar.is_complete or bar.available_time > processing_time:
            break
        prefix.append(bar)
    return tuple(prefix)


def _prefix_load_result(
    source: LoadResult, bars: tuple[CanonicalBar, ...]
) -> LoadResult:
    report = validate_bar_sequence(
        bars,
        source=source.source_config.source,
        timeframe=source.source_config.timeframe,
        assumptions=source.source_config.assumptions(),
    )
    return LoadResult(
        bars=bars,
        quality_report=report,
        source_config=source.source_config,
        loaded_row_count=len(bars),
        accepted_row_count=len(bars),
        rejected_row_count=0,
    )


def _prefix_available_times(
    bars: Sequence[CanonicalBar],
) -> tuple[datetime, ...]:
    result: list[datetime] = []
    maximum: datetime | None = None
    for bar in bars:
        maximum = (
            bar.available_time
            if maximum is None
            else max(maximum, bar.available_time)
        )
        result.append(maximum)
    return tuple(result)


def _true_ranges(bars: Sequence[CanonicalBar]) -> tuple[Decimal, ...]:
    values: list[Decimal] = []
    for index, bar in enumerate(bars):
        if index == 0:
            values.append(bar.high - bar.low)
            continue
        previous_close = bars[index - 1].close
        values.append(
            max(
                bar.high - bar.low,
                abs(bar.high - previous_close),
                abs(bar.low - previous_close),
            )
        )
    return tuple(values)


def _atr_values(
    true_ranges: Sequence[Decimal], period: int
) -> tuple[Decimal | None, ...]:
    result: list[Decimal | None] = []
    divisor = Decimal(period)
    for index in range(len(true_ranges)):
        if index + 1 < period:
            result.append(None)
            continue
        window = true_ranges[index - period + 1 : index + 1]
        result.append(sum(window, Decimal(0)) / divisor)
    return tuple(result)


@dataclass(frozen=True, slots=True)
class AtrReversalDetector:
    """Deterministic state-machine baseline; not a selected production model."""

    config: AtrReversalDetectorConfig

    def __post_init__(self) -> None:
        if not isinstance(self.config, AtrReversalDetectorConfig):
            raise SwingDetectionError(
                "config must be an AtrReversalDetectorConfig"
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
        true_ranges = _true_ranges(bars)
        atr_values = _atr_values(true_ranges, self.config.atr_period)
        prefix_times = _prefix_available_times(bars)
        trend = _Trend.UNKNOWN
        anchor_close: Decimal | None = None
        extreme_price: Decimal | None = None
        extreme_bar: CanonicalBar | None = None
        candidates: list[LevelCandidate] = []
        evaluated = 0
        rejected = 0

        for index, (bar, atr) in enumerate(zip(bars, atr_values)):
            if atr is None:
                continue
            evaluated += 1
            if anchor_close is None:
                anchor_close = bar.close
                continue
            if trend is _Trend.UNKNOWN:
                if bar.close > anchor_close:
                    trend = _Trend.UP
                    extreme_price = bar.high
                    extreme_bar = bar
                elif bar.close < anchor_close:
                    trend = _Trend.DOWN
                    extreme_price = bar.low
                    extreme_bar = bar
                continue

            if extreme_price is None or extreme_bar is None:
                raise SwingDetectionError("trend state has no pre-bar extreme")
            threshold = self.config.reversal_multiplier * atr
            if trend is _Trend.UP:
                if bar.low <= extreme_price - threshold:
                    candidates.append(
                        self._candidate(
                            bars,
                            true_ranges,
                            index,
                            extreme_bar,
                            extreme_price,
                            BoundarySide.UPPER,
                            atr,
                            prefix_times[index],
                        )
                    )
                    trend = _Trend.DOWN
                    extreme_price = bar.low
                    extreme_bar = bar
                else:
                    rejected += 1
                    if bar.high > extreme_price:
                        extreme_price = bar.high
                        extreme_bar = bar
            else:
                if bar.high >= extreme_price + threshold:
                    candidates.append(
                        self._candidate(
                            bars,
                            true_ranges,
                            index,
                            extreme_bar,
                            extreme_price,
                            BoundarySide.LOWER,
                            atr,
                            prefix_times[index],
                        )
                    )
                    trend = _Trend.UP
                    extreme_price = bar.high
                    extreme_bar = bar
                else:
                    rejected += 1
                    if bar.low < extreme_price:
                        extreme_price = bar.low
                        extreme_bar = bar

        ordered = tuple(
            sorted(
                candidates,
                key=lambda item: (item.confirm_time, item.candidate_id),
            )
        )
        warnings: list[str] = []
        warmup = min(len(bars), max(0, self.config.atr_period - 1))
        if warmup:
            warnings.append(f"{warmup} bar(s) consumed by SMA ATR warm-up")
        if bars and anchor_close is not None and trend is _Trend.UNKNOWN:
            warnings.append("direction remains UNKNOWN after anchor initialization")
        if trend is not _Trend.UNKNOWN:
            warnings.append("final directional extreme remains unresolved")
        if truncated:
            warnings.append(
                "causal prefix truncated at the first incomplete or unavailable bar"
            )
        gap_count = _prefix_load_result(source, bars).quality_report.gap_count
        if gap_count:
            warnings.append(f"{gap_count} source interval gap(s); no bars filled")
        origins = tuple(item.origin_time for item in ordered)
        confirms = tuple(
            item.confirm_time for item in ordered if item.confirm_time is not None
        )
        report = SwingDetectionReport(
            input_bar_count=len(bars),
            evaluated_center_count=evaluated,
            confirmed_high_count=sum(
                item.boundary_side is BoundarySide.UPPER for item in ordered
            ),
            confirmed_low_count=sum(
                item.boundary_side is BoundarySide.LOWER for item in ordered
            ),
            leading_incomplete_count=warmup,
            trailing_incomplete_count=int(trend is not _Trend.UNKNOWN),
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
                "true range uses the prior close and exact Decimal arithmetic",
                "ATR is the configured-period simple moving average",
                "UNKNOWN anchors at the first available ATR bar close",
                f"same-bar policy: {SAME_BAR_POLICY}",
                "confirm_time=prefix maximum available_time at reversal bar",
                "as-of stops at the first incomplete or unavailable source bar",
            ),
            warnings=tuple(warnings),
            errors=(),
        )
        return SwingDetectionResult(ordered, report)

    def _candidate(
        self,
        bars: Sequence[CanonicalBar],
        true_ranges: Sequence[Decimal],
        confirmation_index: int,
        origin_bar: CanonicalBar,
        price: Decimal,
        side: BoundarySide,
        atr: Decimal,
        confirm_time: datetime,
    ) -> LevelCandidate:
        start = confirmation_index - self.config.atr_period + 1
        atr_window = tuple(
            {
                "bar_key": canonical_bar_key(bars[index]),
                "true_range": str(true_ranges[index]),
            }
            for index in range(start, confirmation_index + 1)
        )
        origin_key = canonical_bar_key(origin_bar)
        confirmation_key = canonical_bar_key(bars[confirmation_index])
        identity = {
            "atr_period": self.config.atr_period,
            "atr_value": str(atr),
            "atr_window": list(atr_window),
            "boundary_side": side.value,
            "confirm_time": confirm_time.isoformat(),
            "confirmation_bar_key": confirmation_key,
            "detector_id": self.detector_id,
            "detector_version": self.detector_version,
            "origin_bar_key": origin_key,
            "origin_time": origin_bar.timestamp.isoformat(),
            "policy_id": self.config.policy_id,
            "price": str(price),
            "reversal_multiplier": str(self.config.reversal_multiplier),
            "same_bar_policy": SAME_BAR_POLICY,
            "scale": self.config.scale.to_dict(),
            "schema_version": self.config.schema_version,
            "strict": self.config.strict,
            "symbol": origin_bar.symbol,
            "timeframe": origin_bar.timeframe.value,
        }
        digest = sha256(_canonical_json(identity).encode("utf-8")).hexdigest()
        candidate_id = f"swing-atr-v1-{digest}"
        source_digest = sha256(
            _canonical_json(
                {
                    "candidate_identity": identity,
                    "source_module": SOURCE_MODULE,
                }
            ).encode("utf-8")
        ).hexdigest()
        parent_ids = tuple(
            sorted(
                {
                    origin_key,
                    confirmation_key,
                    *(item["bar_key"] for item in atr_window),
                }
            )
        )
        provenance = ProvenanceRef(
            source_module=SOURCE_MODULE,
            source_version=self.detector_version,
            source_object_id=f"atr-turn-v1-{source_digest}",
            policy_id=self.config.policy_id,
            parent_object_ids=parent_ids,
            notes=(
                f"detector_id={self.detector_id}",
                f"detector_version={self.detector_version}",
                f"policy_id={self.config.policy_id}",
                f"atr_period={self.config.atr_period}",
                f"reversal_multiplier={self.config.reversal_multiplier}",
                f"atr_value={atr}",
                f"same_bar_policy={SAME_BAR_POLICY}",
                f"confirmation_bar_key={confirmation_key}",
            ),
        )
        return LevelCandidate(
            candidate_id=candidate_id,
            symbol=origin_bar.symbol,
            timeframe=origin_bar.timeframe,
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
            origin_time=origin_bar.timestamp,
            confirm_time=confirm_time,
            touch_count=0,
            last_touch_time=None,
            last_touch_confirm_time=None,
            break_time=None,
            break_confirm_time=None,
            structure_family=STRUCTURE_FAMILY,
            provenance=provenance,
        )


__all__ = ["AtrReversalDetector", "AtrReversalDetectorConfig"]
