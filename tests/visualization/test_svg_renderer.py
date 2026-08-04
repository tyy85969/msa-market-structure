import xml.etree.ElementTree as ET

from msa.visualization import VisualScene, extract_scene_from_svg, render_svg
from tests.visualization.conftest import scene_fixture


def test_svg_is_deterministic_and_roundtrips_scene(scene: VisualScene) -> None:
    first = render_svg(scene)
    second = render_svg(scene)
    assert first.encode() == second.encode()
    assert extract_scene_from_svg(first) == scene
    ET.fromstring(first)


def test_svg_has_no_external_resources_or_signal_vocabulary(scene: VisualScene) -> None:
    payload = render_svg(scene)
    root = ET.fromstring(payload)
    for item in root.iter():
        for name, value in item.attrib.items():
            if name.rsplit("}", 1)[-1] in {"href", "src"}:
                assert "://" not in value
                assert not value.startswith(("/", "//"))
    lowered = payload.lower()
    for forbidden in (">buy<", ">sell<", ">long<", ">short<", ">entry<", ">exit<", "arrow"):
        assert forbidden not in lowered


def test_single_candle_empty_zone_and_no_active_box_render_safely() -> None:
    scene = scene_fixture(include_zone=False, include_box=False)
    root = ET.fromstring(render_svg(scene))
    assert root.tag.endswith("svg")
