from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET

from msa.visualization import extract_scene_from_svg, render_svg


ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "docs" / "preview" / "artifacts"
NAMES = ("single_trend", "range", "v_reversal", "false_break", "gap_shock")


class SVGCounter(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.count = 0

    def handle_starttag(self, tag, attrs) -> None:
        if tag == "svg":
            self.count += 1


def test_five_committed_svg_outputs_are_parseable_and_canonical() -> None:
    for name in NAMES:
        path = ARTIFACTS / f"{name}.svg"
        payload = path.read_text(encoding="utf-8")
        ET.fromstring(payload)
        scene = extract_scene_from_svg(payload)
        assert scene.seed == 2 and scene.partition == "VALIDATION"
        assert render_svg(scene).encode() == path.read_bytes()


def test_committed_html_output_is_parseable() -> None:
    parser = SVGCounter()
    parser.feed((ARTIFACTS / "msa_visual_preview_index.html").read_text(encoding="utf-8"))
    parser.close()
    assert parser.count == 5
