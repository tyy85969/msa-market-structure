"""Offline HTML index for the five bounded SVG previews."""

from __future__ import annotations

import html
from collections.abc import Mapping

from .contracts import VisualScene
from .errors import VisualRenderError


def _slug(scenario: str) -> str:
    return scenario.lower()


def render_html_report(
    scenes: tuple[VisualScene, ...],
    rendered_svgs: Mapping[str, str],
) -> str:
    if not isinstance(scenes, tuple) or not scenes:
        raise VisualRenderError("scenes must be a non-empty tuple")
    if any(not isinstance(scene, VisualScene) for scene in scenes):
        raise VisualRenderError("scenes must contain VisualScene values")
    if set(rendered_svgs) != {scene.scenario for scene in scenes}:
        raise VisualRenderError("rendered SVG coverage must exactly match scenes")

    parts = [
        "<!doctype html>",
        '<html lang="en">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width,initial-scale=1">',
        "<title>MSA Core bounded visual preview</title>",
        "<style>",
        ":root{color-scheme:dark;font-family:Segoe UI,Arial,sans-serif;background:#07101d;color:#edf2f7}",
        "*{box-sizing:border-box}body{margin:0;background:#07101d}header,main,footer{max-width:1420px;margin:auto}",
        "header{padding:36px 28px 20px}h1{font-size:30px;margin:0 0 12px}p{color:#aeb9ca;line-height:1.55;margin:7px 0}",
        ".notice{display:flex;flex-wrap:wrap;gap:10px;margin-top:18px}.pill{border:1px solid #44516a;border-radius:999px;padding:7px 11px;color:#d8e0eb;font-size:13px}",
        "main{padding:12px 28px 40px;display:grid;gap:24px}.card{background:#0d1726;border:1px solid #263550;border-radius:12px;overflow:hidden;box-shadow:0 14px 34px #02060c66}",
        ".card-head{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:18px 22px;border-bottom:1px solid #263550}.card h2{font-size:18px;margin:0}.card a{color:#68c7e8;text-decoration:none}.card a:hover{text-decoration:underline}",
        ".canvas{padding:10px;background:#0b1220}.canvas svg{display:block;width:100%;height:auto}footer{padding:0 28px 36px;color:#8592a6;font-size:13px}",
        "</style>",
        "</head>",
        "<body>",
        "<header>",
        "<h1>MSA Core bounded visual preview</h1>",
        "<p>Five deterministic synthetic VALIDATION seed-2 scenes for visual inspection of structural boundaries, Resonance Zones, and the Active Box.</p>",
        '<div class="notice"><span class="pill">Synthetic VALIDATION Preview</span><span class="pill">Not OOS</span><span class="pill">Not Trading Advice</span><span class="pill">Core status: BLOCKED_BEFORE_OOS</span></div>',
        "</header>",
        "<main>",
    ]
    for scene in scenes:
        slug = _slug(scene.scenario)
        svg = rendered_svgs[scene.scenario]
        parts.extend(
            [
                f'<section class="card" id="{html.escape(slug)}">',
                '<div class="card-head">',
                f'<h2>{html.escape(scene.scenario.replace("_", " "))}</h2>',
                f'<a href="{html.escape(slug)}.svg">Open standalone SVG</a>',
                "</div>",
                f'<div class="canvas">{svg.rstrip()}</div>',
                "</section>",
            ]
        )
    parts.extend(
        [
            "</main>",
            "<footer>Visual preview only. Visual feedback does not change Core parameters, formal Evidence, Gates, or remediation scope.</footer>",
            "</body>",
            "</html>",
        ]
    )
    return "\n".join(parts) + "\n"
