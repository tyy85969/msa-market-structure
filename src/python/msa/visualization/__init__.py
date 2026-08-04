"""Public API for the bounded MSA Core visual preview."""

from .contracts import (
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
from .errors import (
    MSAVisualizationError,
    VisualContractError,
    VisualPreviewScopeError,
    VisualRenderError,
    VisualSceneBuildError,
)
from .html_report import render_html_report
from .scene_builder import build_visual_scene
from .svg_renderer import extract_scene_from_svg, render_svg

__all__ = [
    "ADVICE_LABEL",
    "CORE_STATUS",
    "OOS_LABEL",
    "PREVIEW_LABEL",
    "BoundaryTier",
    "DisplayState",
    "MSAVisualizationError",
    "VisualActiveBox",
    "VisualBoundary",
    "VisualCandle",
    "VisualContractError",
    "VisualLevel",
    "VisualPreviewScopeError",
    "VisualRenderError",
    "VisualScene",
    "VisualSceneBuildError",
    "VisualZone",
    "build_visual_scene",
    "extract_scene_from_svg",
    "render_html_report",
    "render_svg",
]
