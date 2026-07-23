from msa.research.active_box import ActiveBoxEventType
from msa.research.msa_core import replay_msa_core_run
from msa.research.msa_core.identity import digest

from .fixtures import batch_run, extra_run, pipeline, source_input


def test_c007d_golden_identities_and_digests() -> None:
    run = batch_run()
    default_replay = replay_msa_core_run(pipeline(), source_input())
    explicit_replay = extra_run()
    first_active = next(
        frame.active_box_snapshot
        for frame in run.active_box_history.frames
        if frame.active_box_snapshot is not None
    )
    first_frozen = next(
        event
        for event in run.active_box_history.events
        if event.event_type is ActiveBoxEventType.FROZEN
    )
    replacement = next(
        event
        for event in run.active_box_history.events
        if event.event_type is ActiveBoxEventType.CREATED
        and event.event_reason.value == "PAIR_CHANGED"
    )
    assert run.frame_bundles[0].bundle_id == (
        "msa-core-bundle-v1-"
        "a845a3dfd1ed3c0ca1b0b63db5a1b9253c21965558127fd45fb22ad678157039"
    )
    assert run.frame_bundles[-1].bundle_id == (
        "msa-core-bundle-v1-"
        "9e59ef25b6a8f0e8d5f6e5bf1c55de4cb31d3bb611bad54cf33c052e85455d0b"
    )
    assert run.run_id == (
        "msa-core-run-v1-"
        "15de89a73398f0dd4e008ae20a07d199637eccf5b8cf57ffcdf75cd32f3c56e9"
    )
    assert digest(run.to_dict()) == (
        "d27d9f594722fc9c1778ce009a6a54101b50d511b2ae17dc6b4c9c638eca4907"
    )
    assert digest(default_replay.to_dict()) == (
        "d27d9f594722fc9c1778ce009a6a54101b50d511b2ae17dc6b4c9c638eca4907"
    )
    assert digest(explicit_replay.to_dict()) == (
        "b3bc8988b3d3903d10804c9a0c9822b360fb76dc0526556c590f567a5b8e79ac"
    )
    assert first_active.box_key_id == (
        "active-box-key-v1-"
        "da66761b00c9f58c124a6e2150adad20cc597fdc4f197fde422c54b47d9f1dde"
    )
    assert first_frozen.event_id == (
        "active-box-event-v1-"
        "7a82874bf1a200e6d1f54b722d7065de524b977701a601aa6928b3266b592d6f"
    )
    assert replacement.box_key_id == (
        "active-box-key-v1-"
        "9fb1aec9ab2d67ba562ccc73713d09d21cedc9d8f0dbe1fb9999098517891586"
    )
