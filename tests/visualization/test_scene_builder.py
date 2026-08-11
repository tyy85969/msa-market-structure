from __future__ import annotations

import ast
import inspect

import pytest

import msa.visualization.scene_builder as scene_builder
from msa.validation.contracts import SyntheticScenarioKind
from msa.visualization import VisualPreviewScopeError, build_visual_scene
from tests.research.msa_core.fixtures import batch_run


@pytest.fixture(scope="module")
def core_fixture_run():
    return batch_run()


def test_builder_projects_public_bundle_facts(core_fixture_run) -> None:
    scene = build_visual_scene(SyntheticScenarioKind.SINGLE_TREND, 2, core_fixture_run)
    final = core_fixture_run.final_bundle
    assert len(scene.resonance_zones) == len(final.score_frame.zones)
    assert (scene.active_box is not None) == (final.selection_frame.active_box_snapshot is not None)
    assert all(item.available_time <= scene.as_of_time for item in scene.candles)


def test_builder_rejects_seed_3_before_touching_run() -> None:
    with pytest.raises(VisualPreviewScopeError, match="VALIDATION seed 2"):
        build_visual_scene(SyntheticScenarioKind.RANGE, 3, None)  # type: ignore[arg-type]


def test_builder_does_not_import_core_algorithm_modules() -> None:
    tree = ast.parse(inspect.getsource(scene_builder))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {
        node.module or ""
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert not any(
        name.endswith((".pipeline", ".assembler", ".scoring", ".engine", ".policy"))
        for name in imported
    )
