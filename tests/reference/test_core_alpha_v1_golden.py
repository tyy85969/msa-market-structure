import hashlib
from pathlib import Path

from msa.reference import core_alpha_v1_config, core_alpha_v1_profile
from msa.reference.identity import digest
from msa.research.msa_core import MSACorePipeline, replay_msa_core_run
from tests.research.msa_core.fixtures import extra_schedule, source_input


ROOT = Path(__file__).resolve().parents[2]


def test_core_alpha_v1_reference_goldens() -> None:
    config = core_alpha_v1_config()
    profile = core_alpha_v1_profile()
    source = source_input()
    pipeline = MSACorePipeline(config)
    batch = pipeline.run(source)
    default_replay = replay_msa_core_run(pipeline, source)
    extra_replay = replay_msa_core_run(pipeline, source, extra_schedule())
    json_bytes = (
        ROOT / "docs" / "reference" / "core_alpha_v1_config.json"
    ).read_bytes()

    assert profile.profile_semantic_id == (
        "core-baseline-profile-v1-"
        "a63b572b9416d8ba23aa74e80c3960847f7d0ca0118ede85a2408f10fbff3b49"
    )
    assert profile.core_config_payload_digest == (
        "992f9ab6b04384c69cb1f3a68d49a51480e2d67b579254ab9ce58677ac168a14"
    )
    assert hashlib.sha256(json_bytes).hexdigest() == (
        "f7cae328c78e5f1e7bdb69cdb4eb3f8bada9d7facae656cbd8652751a24db396"
    )
    assert digest(profile.to_dict()) == (
        "f5a4fbc49b8cfbc16e8eb0161cfd71bf48996a9785693a32de2da21e2970bbce"
    )
    assert batch.run_id == (
        "msa-core-run-v1-"
        "15de89a73398f0dd4e008ae20a07d199637eccf5b8cf57ffcdf75cd32f3c56e9"
    )
    assert default_replay.run_id == (
        "msa-core-run-v1-"
        "15de89a73398f0dd4e008ae20a07d199637eccf5b8cf57ffcdf75cd32f3c56e9"
    )
    assert extra_replay.run_id == (
        "msa-core-run-v1-"
        "26bee8b81a9606dec082c9e1069f15a3905cc86c0ab55b25f1d2773320632f39"
    )
