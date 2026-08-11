from html.parser import HTMLParser

from msa.visualization import VisualScene, render_html_report, render_svg


class Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.svg_count = 0
        self.links: list[str] = []

    def handle_starttag(self, tag, attrs) -> None:
        if tag == "svg":
            self.svg_count += 1
        for name, value in attrs:
            if name in {"href", "src"} and value:
                self.links.append(value)


def test_html_is_deterministic_offline_and_contains_five_inline_svgs(
    five_scenes: tuple[VisualScene, ...],
) -> None:
    svgs = {item.scenario: render_svg(item) for item in five_scenes}
    first = render_html_report(five_scenes, svgs)
    assert first == render_html_report(five_scenes, svgs)
    parser = Parser()
    parser.feed(first)
    parser.close()
    assert parser.svg_count == 5
    assert all("://" not in item and not item.startswith("/") for item in parser.links)
    assert "cdn" not in first.lower()


def test_html_contains_required_scope_labels(five_scenes) -> None:
    svgs = {item.scenario: render_svg(item) for item in five_scenes}
    payload = render_html_report(five_scenes, svgs)
    for label in ("Synthetic VALIDATION Preview", "Not OOS", "Not Trading Advice", "BLOCKED_BEFORE_OOS"):
        assert label in payload
