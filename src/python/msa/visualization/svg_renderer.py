"""Deterministic, dependency-free SVG renderer for visual scenes."""

from __future__ import annotations

import html
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal

from .contracts import (
    BoundaryTier,
    DisplayState,
    VisualLevel,
    VisualScene,
)
from .errors import VisualRenderError


WIDTH = 1280
HEIGHT = 720
PLOT_LEFT = 76.0
PLOT_TOP = 122.0
PLOT_RIGHT = 1010.0
PLOT_BOTTOM = 620.0


def _n(value: float) -> str:
    return f"{value:.2f}".rstrip("0").rstrip(".")


def _esc(value: object) -> str:
    return html.escape(str(value), quote=True)


def _style(boundary: object) -> tuple[str, str, str, str]:
    if boundary.display_state in (DisplayState.BROKEN, DisplayState.RETIRED):
        return "#7f8b9d", "1.2", "5 5", "0.36"
    if boundary.visual_level is VisualLevel.HIGH_TIMEFRAME:
        dash = "7 4" if boundary.tier is BoundaryTier.CANDIDATE else ""
        return "#42c6e8", "2.2", dash, "0.88"
    if boundary.tier is BoundaryTier.CANDIDATE:
        return "#69c58a", "1.8", "7 5", "0.82"
    return "#f2d34f", "2.4", "", "0.94"


def render_svg(scene: VisualScene) -> str:
    if not isinstance(scene, VisualScene):
        raise VisualRenderError("scene must be a VisualScene")

    prices = [value for candle in scene.candles for value in (candle.low, candle.high)]
    for boundary in scene.confirmed_boundaries + scene.candidate_boundaries:
        prices.extend((boundary.price_low, boundary.price_high))
    for zone in scene.resonance_zones:
        prices.extend((zone.price_low, zone.price_high))
    if scene.active_box is not None:
        prices.extend(
            (
                scene.active_box.lower_low,
                scene.active_box.lower_high,
                scene.active_box.upper_low,
                scene.active_box.upper_high,
            )
        )
    low, high = min(prices), max(prices)
    span = high - low
    padding = span * Decimal("0.06") if span else Decimal("1")
    low -= padding
    high += padding
    span = high - low

    time_start = min(candle.timestamp for candle in scene.candles)
    time_end = scene.as_of_time
    seconds = max((time_end - time_start).total_seconds(), 1.0)

    def x(moment: datetime) -> float:
        ratio = (moment - time_start).total_seconds() / seconds
        ratio = min(1.0, max(0.0, ratio))
        return PLOT_LEFT + ratio * (PLOT_RIGHT - PLOT_LEFT)

    def y(price: Decimal) -> float:
        ratio = float((high - price) / span)
        return PLOT_TOP + ratio * (PLOT_BOTTOM - PLOT_TOP)

    output = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
        f"<metadata>{html.escape(scene.canonical_json(), quote=False)}</metadata>",
        f'<title id="title">{_esc(scene.scenario)} — MSA Core visual preview</title>',
        f'<desc id="desc">{_esc(scene.preview_label)}. {_esc(scene.oos_label)}. {_esc(scene.advice_label)}.</desc>',
        "<style>text{font-family:Segoe UI,Arial,sans-serif}.muted{fill:#96a2b5}.small{font-size:12px}.label{font-size:13px}.heading{font-weight:650}</style>",
        '<rect width="1280" height="720" fill="#0b1220"/>',
        f'<rect x="{_n(PLOT_LEFT)}" y="{_n(PLOT_TOP)}" width="{_n(PLOT_RIGHT-PLOT_LEFT)}" height="{_n(PLOT_BOTTOM-PLOT_TOP)}" rx="5" fill="#101a2b" stroke="#25324a"/>',
        f'<text x="76" y="40" fill="#edf2f7" font-size="22" class="heading">{_esc(scene.scenario.replace("_", " "))}</text>',
        f'<text x="76" y="66" fill="#9eabc0" font-size="13">{_esc(scene.symbol)} · {_esc(scene.reference_timeframe)} candles · AsOf {_esc(scene.as_of_time.isoformat())}</text>',
        f'<text x="76" y="91" fill="#d9b85f" font-size="12">{_esc(scene.preview_label)} · {_esc(scene.oos_label)} · {_esc(scene.advice_label)} · Core: {_esc(scene.core_status)}</text>',
    ]

    for index in range(5):
        price = low + span * Decimal(index) / Decimal(4)
        yy = y(price)
        output.append(f'<line x1="{_n(PLOT_LEFT)}" y1="{_n(yy)}" x2="{_n(PLOT_RIGHT)}" y2="{_n(yy)}" stroke="#223049" stroke-width="1"/>')
        output.append(f'<text x="{_n(PLOT_LEFT-10)}" y="{_n(yy+4)}" text-anchor="end" class="small muted">{_esc(format(price, ".2f"))}</text>')

    for zone in scene.resonance_zones:
        left = x(zone.confirm_time)
        top = y(zone.price_high)
        height = max(2.0, y(zone.price_low) - top)
        output.append(f'<rect x="{_n(left)}" y="{_n(top)}" width="{_n(PLOT_RIGHT-left)}" height="{_n(height)}" fill="#9b7bd8" fill-opacity="0.13" stroke="#a88be0" stroke-opacity="0.38" stroke-width="1"/>')

    if scene.active_box is not None:
        box = scene.active_box
        left = x(box.confirm_time)
        top = y(box.upper_high)
        height = max(3.0, y(box.lower_low) - top)
        output.append(f'<rect x="{_n(left)}" y="{_n(top)}" width="{_n(PLOT_RIGHT-left)}" height="{_n(height)}" fill="#e6b95d" fill-opacity="0.055" stroke="#e6b95d" stroke-opacity="0.92" stroke-width="2"/>')
        output.append(f'<line x1="{_n(left)}" y1="{_n(y(box.lower_high))}" x2="{_n(PLOT_RIGHT)}" y2="{_n(y(box.lower_high))}" stroke="#e6b95d" stroke-opacity="0.42"/>')
        output.append(f'<line x1="{_n(left)}" y1="{_n(y(box.upper_low))}" x2="{_n(PLOT_RIGHT)}" y2="{_n(y(box.upper_low))}" stroke="#e6b95d" stroke-opacity="0.42"/>')

    candle_step = (PLOT_RIGHT - PLOT_LEFT) / max(len(scene.candles), 1)
    candle_width = max(2.0, min(8.0, candle_step * 0.58))
    for candle in scene.candles:
        xx = x(candle.end_time)
        upward = candle.close >= candle.open
        color = "#77a9cf" if upward else "#c6a36d"
        output.append(f'<line x1="{_n(xx)}" y1="{_n(y(candle.high))}" x2="{_n(xx)}" y2="{_n(y(candle.low))}" stroke="{color}" stroke-width="1"/>')
        body_top = min(y(candle.open), y(candle.close))
        body_height = max(1.4, abs(y(candle.open) - y(candle.close)))
        output.append(f'<rect x="{_n(xx-candle_width/2)}" y="{_n(body_top)}" width="{_n(candle_width)}" height="{_n(body_height)}" fill="{color}" fill-opacity="0.74"/>')

    for boundary in scene.confirmed_boundaries + scene.candidate_boundaries:
        center = (boundary.price_low + boundary.price_high) / Decimal(2)
        yy = y(center)
        color, width, dash, opacity = _style(boundary)
        if boundary.show_origin_extension and boundary.origin_time < boundary.confirm_time:
            output.append(f'<line x1="{_n(x(boundary.origin_time))}" y1="{_n(yy)}" x2="{_n(x(boundary.confirm_time))}" y2="{_n(yy)}" stroke="#a4adba" stroke-width="1" stroke-dasharray="2 4" stroke-opacity="0.38"/>')
        dash_attr = f' stroke-dasharray="{dash}"' if dash else ""
        output.append(f'<line x1="{_n(x(boundary.confirm_time))}" y1="{_n(yy)}" x2="{_n(x(boundary.display_end_time))}" y2="{_n(yy)}" stroke="{color}" stroke-width="{width}" stroke-opacity="{opacity}"{dash_attr}/>' )

    as_of_x = x(scene.as_of_time)
    output.extend(
        [
            f'<line x1="{_n(as_of_x)}" y1="{_n(PLOT_TOP)}" x2="{_n(as_of_x)}" y2="{_n(PLOT_BOTTOM)}" stroke="#e8edf5" stroke-width="1" stroke-dasharray="3 5" stroke-opacity="0.58"/>',
            f'<text x="{_n(as_of_x-6)}" y="{_n(PLOT_TOP+16)}" text-anchor="end" fill="#dce4ef" font-size="11">processing AsOf</text>',
            '<text x="1040" y="142" fill="#edf2f7" font-size="15" class="heading">Visual hierarchy</text>',
            '<line x1="1040" y1="168" x2="1080" y2="168" stroke="#f2d34f" stroke-width="2.4"/><text x="1090" y="172" class="label" fill="#cbd5e1">Confirmed major</text>',
            '<line x1="1040" y1="198" x2="1080" y2="198" stroke="#42c6e8" stroke-width="2.2"/><text x="1090" y="202" class="label" fill="#cbd5e1">High timeframe</text>',
            '<line x1="1040" y1="228" x2="1080" y2="228" stroke="#69c58a" stroke-width="1.8" stroke-dasharray="7 5"/><text x="1090" y="232" class="label" fill="#cbd5e1">Candidate</text>',
            '<rect x="1040" y="250" width="40" height="14" fill="#9b7bd8" fill-opacity="0.22" stroke="#a88be0" stroke-opacity="0.55"/><text x="1090" y="262" class="label" fill="#cbd5e1">Resonance Zone</text>',
            '<rect x="1040" y="280" width="40" height="14" fill="#e6b95d" fill-opacity="0.08" stroke="#e6b95d"/><text x="1090" y="292" class="label" fill="#cbd5e1">Active Box</text>',
            '<line x1="1040" y1="320" x2="1080" y2="320" stroke="#7f8b9d" stroke-opacity="0.36" stroke-dasharray="5 5"/><text x="1090" y="324" class="label" fill="#cbd5e1">Broken / retired</text>',
            '<text x="1040" y="370" fill="#edf2f7" font-size="15" class="heading">Scene counts</text>',
            f'<text x="1040" y="398" class="label" fill="#cbd5e1">Candles  {len(scene.candles)}</text>',
            f'<text x="1040" y="424" class="label" fill="#cbd5e1">Boundaries  {scene.boundary_count}</text>',
            f'<text x="1040" y="450" class="label" fill="#cbd5e1">Zones  {len(scene.resonance_zones)}</text>',
            f'<text x="1040" y="476" class="label" fill="#cbd5e1">Active Box  {1 if scene.active_box else 0}</text>',
            f'<text x="76" y="654" class="small muted">OriginTime extension is grey; state color begins only at ConfirmTime. Candle tone is neutral chronology, not a directional recommendation.</text>',
            f'<text x="76" y="678" class="small muted">{_esc(scene.preview_label)} · seed {scene.seed} · {_esc(scene.partition)} · {_esc(scene.core_status)}</text>',
            "</svg>",
        ]
    )
    return "\n".join(output) + "\n"


def extract_scene_from_svg(svg: str) -> VisualScene:
    """Restore the exact scene embedded in an SVG for bounded --check mode."""

    if not isinstance(svg, str):
        raise VisualRenderError("SVG payload must be text")
    try:
        root = ET.fromstring(svg)
        metadata = next(
            item for item in root.iter() if item.tag.rsplit("}", 1)[-1] == "metadata"
        )
        if metadata.text is None:
            raise VisualRenderError("SVG metadata is empty")
        import json

        payload = json.loads(metadata.text)
        return VisualScene.from_dict(payload)
    except (ET.ParseError, StopIteration, TypeError, ValueError) as exc:
        if isinstance(exc, VisualRenderError):
            raise
        raise VisualRenderError("SVG does not contain a valid VisualScene") from exc
