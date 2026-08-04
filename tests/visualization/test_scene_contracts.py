from dataclasses import replace

import pytest

from msa.visualization import VisualContractError, VisualScene


def test_scene_roundtrips_exactly(scene: VisualScene) -> None:
    assert VisualScene.from_dict(scene.to_dict()) == scene


def test_seed_3_and_oos_are_rejected(scene: VisualScene) -> None:
    with pytest.raises(VisualContractError, match="VALIDATION seed 2"):
        replace(scene, seed=3, partition="OOS")


def test_unknown_contract_fields_are_rejected(scene: VisualScene) -> None:
    payload = scene.to_dict()
    payload["unknown"] = True
    with pytest.raises(VisualContractError, match="fields must be exact"):
        VisualScene.from_dict(payload)
