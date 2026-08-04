"""Generate or byte-check the bounded MSA Core visual preview."""

from __future__ import annotations

import argparse
import sys
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src/python"))

from msa.visualization import (
    VisualScene,
    build_visual_scene,
    extract_scene_from_svg,
    render_html_report,
    render_svg,
)
from msa.visualization.errors import VisualRenderError


ARTIFACTS = ROOT / "docs" / "preview" / "artifacts"
SCENARIOS = (
    "SINGLE_TREND",
    "RANGE",
    "V_REVERSAL",
    "FALSE_BREAK",
    "GAP_SHOCK",
)


class _HTMLCheck(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.svg_count = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "svg":
            self.svg_count += 1
        for name, value in attrs:
            if name in {"src", "href"} and value is not None:
                if "://" in value or value.startswith(("//", "/")):
                    raise VisualRenderError("HTML contains a network or absolute resource")


def _paths() -> tuple[Path, ...]:
    return tuple(ARTIFACTS / f"{item.lower()}.svg" for item in SCENARIOS)


def _validate_svg(payload: str) -> None:
    root = ET.fromstring(payload)
    for item in root.iter():
        for name, value in item.attrib.items():
            local_name = name.rsplit("}", 1)[-1]
            if local_name in {"href", "src"} and (
                "://" in value or value.startswith(("//", "/"))
            ):
                raise VisualRenderError("SVG contains an external resource")


def _validate_html(payload: str) -> None:
    parser = _HTMLCheck()
    parser.feed(payload)
    parser.close()
    if parser.svg_count != len(SCENARIOS):
        raise VisualRenderError("HTML must contain exactly five inline SVGs")


def _validate_common(payload: str) -> None:
    lowered = payload.lower()
    for forbidden in ("file://", "localhost", "temp\\", "tmp\\"):
        if forbidden in lowered:
            raise VisualRenderError(f"artifact contains forbidden text: {forbidden}")


def _render(scenes: tuple[VisualScene, ...]) -> tuple[dict[str, str], str]:
    svgs = {scene.scenario: render_svg(scene) for scene in scenes}
    html = render_html_report(scenes, svgs)
    for payload in svgs.values():
        _validate_common(payload)
        _validate_svg(payload)
    _validate_common(html)
    _validate_html(html)
    return svgs, html


def _generate_scenes() -> tuple[VisualScene, ...]:
    # Imports stay local so --check never constructs Dataset or executes Core.
    from msa.research.msa_core import MSACorePipeline
    from msa.validation.contracts import SyntheticScenarioKind
    from msa.validation.experiments import (
        build_synthetic_source_input,
        core_experiment_baseline,
    )

    config = core_experiment_baseline().core_config_snapshot
    pipeline = MSACorePipeline(config)
    scenes = []
    for name in SCENARIOS:
        scenario = SyntheticScenarioKind(name)
        source_input = build_synthetic_source_input(scenario, 2)
        run = pipeline.run(source_input)
        scenes.append(build_visual_scene(scenario, 2, run))
    return tuple(scenes)


def _load_scenes() -> tuple[VisualScene, ...]:
    scenes = []
    for path, expected in zip(_paths(), SCENARIOS):
        if not path.is_file():
            raise VisualRenderError(f"missing preview artifact: {path.name}")
        scene = extract_scene_from_svg(path.read_text(encoding="utf-8"))
        if scene.scenario != expected:
            raise VisualRenderError("SVG scenario order is inconsistent")
        scenes.append(scene)
    return tuple(scenes)


def _print_summary(scenes: tuple[VisualScene, ...], action: str) -> None:
    for scene in scenes:
        print(
            f"{action}: {scene.scenario.lower()}.svg "
            f"candles={len(scene.candles)} zones={len(scene.resonance_zones)} "
            f"boundaries={scene.boundary_count} active_box={1 if scene.active_box else 0}"
        )
    print(f"{action}: msa_visual_preview_index.html")


def generate() -> tuple[VisualScene, ...]:
    scenes = _generate_scenes()
    svgs, html = _render(scenes)
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    for scene, path in zip(scenes, _paths()):
        path.write_bytes(svgs[scene.scenario].encode("utf-8"))
    (ARTIFACTS / "msa_visual_preview_index.html").write_bytes(
        html.encode("utf-8")
    )
    _print_summary(scenes, "wrote")
    return scenes


def check() -> tuple[VisualScene, ...]:
    scenes = _load_scenes()
    svgs, html = _render(scenes)
    for scene, path in zip(scenes, _paths()):
        if path.read_bytes() != svgs[scene.scenario].encode("utf-8"):
            raise VisualRenderError(f"preview SVG is not canonical: {path.name}")
    index = ARTIFACTS / "msa_visual_preview_index.html"
    if not index.is_file() or index.read_bytes() != html.encode("utf-8"):
        raise VisualRenderError("preview HTML is missing or not canonical")
    _print_summary(scenes, "checked")
    return scenes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--check",
        action="store_true",
        help="byte-check committed artifacts without executing Core",
    )
    args = parser.parse_args()
    check() if args.check else generate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
