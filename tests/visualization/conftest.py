from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from msa.visualization import (
    ADVICE_LABEL,
    CORE_STATUS,
    OOS_LABEL,
    PREVIEW_LABEL,
    BoundaryTier,
    DisplayState,
    VisualActiveBox,
    VisualBoundary,
    VisualCandle,
    VisualLevel,
    VisualScene,
    VisualZone,
)


START = datetime(2026, 1, 1, tzinfo=timezone.utc)
AS_OF = START + timedelta(hours=1)


def scene_fixture(
    *,
    scenario: str = "SINGLE_TREND",
    include_zone: bool = True,
    include_box: bool = True,
) -> VisualScene:
    candle = VisualCandle(
        source_id="visual-candle-fixture",
        timestamp=START,
        end_time=AS_OF,
        available_time=AS_OF,
        open=Decimal("100"),
        high=Decimal("103"),
        low=Decimal("99"),
        close=Decimal("102"),
    )
    confirmed = VisualBoundary(
        visual_boundary_id="visual-boundary-confirmed",
        boundary_id="boundary-confirmed",
        subject_id="subject-confirmed",
        side="LOWER",
        tier=BoundaryTier.CONFIRMED,
        visual_level=VisualLevel.MAJOR,
        lifecycle_state="TESTED",
        display_state=DisplayState.ACTIVE,
        timeframe="H4",
        scale_id="primary",
        price_low=Decimal("99"),
        price_high=Decimal("100"),
        origin_time=START,
        confirm_time=START + timedelta(minutes=30),
        display_end_time=AS_OF,
        show_origin_extension=True,
        source_ids=("evidence-confirmed", "bundle-fixture"),
    )
    candidate = VisualBoundary(
        visual_boundary_id="visual-boundary-candidate",
        boundary_id="boundary-candidate",
        subject_id="subject-candidate",
        side="UPPER",
        tier=BoundaryTier.CANDIDATE,
        visual_level=VisualLevel.HIGH_TIMEFRAME,
        lifecycle_state="FRESH",
        display_state=DisplayState.ACTIVE,
        timeframe="H12",
        scale_id="macro",
        price_low=Decimal("102"),
        price_high=Decimal("103"),
        origin_time=START,
        confirm_time=START + timedelta(minutes=40),
        display_end_time=AS_OF,
        show_origin_extension=True,
        source_ids=("evidence-candidate", "bundle-fixture"),
    )
    zone = VisualZone(
        zone_key_id="zone-key-fixture",
        zone_snapshot_id="zone-snapshot-fixture",
        side="UPPER",
        resonance_class="MULTI_CONTEXT_RESONANCE",
        price_low=Decimal("102"),
        price_high=Decimal("103"),
        origin_time=START,
        confirm_time=START + timedelta(minutes=40),
        candidate_count=1,
        confirmed_count=1,
        source_ids=("zone-snapshot-fixture", "evidence-candidate"),
    )
    box = VisualActiveBox(
        box_id="box-fixture",
        status="ACTIVE",
        lower_low=Decimal("99"),
        lower_high=Decimal("100"),
        upper_low=Decimal("102"),
        upper_high=Decimal("103"),
        origin_time=START,
        confirm_time=START + timedelta(minutes=45),
        source_ids=("box-snapshot-fixture", "selection-frame-fixture"),
    )
    return VisualScene(
        scenario=scenario,
        seed=2,
        partition="VALIDATION",
        as_of_time=AS_OF,
        symbol="XAUUSD",
        reference_timeframe="H1",
        preview_label=PREVIEW_LABEL,
        oos_label=OOS_LABEL,
        advice_label=ADVICE_LABEL,
        core_status=CORE_STATUS,
        candles=(candle,),
        confirmed_boundaries=(confirmed,),
        candidate_boundaries=(candidate,),
        resonance_zones=(zone,) if include_zone else (),
        active_box=box if include_box else None,
        source_ids=("run-fixture", "bundle-fixture"),
    )


@pytest.fixture
def scene() -> VisualScene:
    return scene_fixture()


@pytest.fixture
def five_scenes(scene: VisualScene) -> tuple[VisualScene, ...]:
    names = ("SINGLE_TREND", "RANGE", "V_REVERSAL", "FALSE_BREAK", "GAP_SHOCK")
    return tuple(replace(scene, scenario=name) for name in names)
