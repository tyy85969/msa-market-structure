from dataclasses import replace
from datetime import timedelta
from hashlib import sha256
import json

import pytest

from msa.research.resonance import (
    ResonanceFrameHistory,
    ResonanceScoreHistory,
    ResonanceScoringEngineError,
    ResonanceScoringInputError,
    replay_score_history,
)
from tests.research.resonance.fixtures import T2, assembler, frame_input

from .fixtures import scorer, source_history


def _payload_digest(value: object) -> str:
    encoded = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode()
    return sha256(encoded).hexdigest()


def test_batch_scores_exactly_one_frame_per_source_frame() -> None:
    source = source_history()
    history = scorer().build_batch(source)
    assert len(history.frames) == len(source.frames)
    assert tuple(item.as_of_time for item in history.frames) == tuple(item.as_of_time for item in source.frames)
    assert tuple(item.source_frame_id for item in history.frames) == tuple(item.frame_id for item in source.frames)
    assert history.final_frame == history.frames[-1]


def test_default_replay_is_full_payload_equivalent_to_batch() -> None:
    source = source_history()
    assert replay_score_history(scorer(), source).to_dict() == scorer().build_batch(source).to_dict()


def test_explicit_replay_accepts_legal_extra_as_of_frame() -> None:
    source = source_history()
    extra = assembler().build_as_of(frame_input(), T2 + timedelta(seconds=30))
    frames = tuple(sorted(source.frames + (extra,), key=lambda item: item.as_of_time))
    replay = replay_score_history(scorer(), source, frames)
    assert len(replay.frames) == len(source.frames) + 1
    assert extra.frame_id in {item.source_frame_id for item in replay.frames}


def test_explicit_replay_rejects_missing_source_duplicate_and_time_regression() -> None:
    source = source_history()
    with pytest.raises(ResonanceScoringInputError, match="omit"):
        replay_score_history(scorer(), source, source.frames[:-1])
    with pytest.raises(ResonanceScoringInputError, match="strictly"):
        replay_score_history(scorer(), source, tuple(reversed(source.frames)))
    with pytest.raises(ResonanceScoringInputError, match="strictly"):
        replay_score_history(scorer(), source, source.frames + (source.frames[-1],))


def test_future_source_append_does_not_change_old_score_frame_payloads() -> None:
    full_source = source_history()
    prefix_source = ResonanceFrameHistory(
        frames=full_source.frames[:-1],
        final_frame=full_source.frames[-2],
        config_snapshot=full_source.config_snapshot,
    )
    prefix = scorer().build_batch(prefix_source)
    full = scorer().build_batch(full_source)
    assert tuple(item.to_dict() for item in full.frames[:-1]) == tuple(item.to_dict() for item in prefix.frames)


def test_price_only_and_lifecycle_only_identity_behavior() -> None:
    history = scorer().build_batch(source_history())
    at_t2 = next(item for item in history.frames if item.as_of_time == T2)
    at_t3 = history.frames[-1]
    by_subject_t2 = {zone.member_subject_ids: zone for zone in at_t2.zones}
    by_subject_t3 = {zone.member_subject_ids: zone for zone in at_t3.zones}
    assert set(by_subject_t2) == set(by_subject_t3)
    for key in by_subject_t2:
        assert by_subject_t2[key].zone_key_id == by_subject_t3[key].zone_key_id
        assert by_subject_t2[key].zone_snapshot_id != by_subject_t3[key].zone_snapshot_id
    at_t1 = history.frames[1]
    common = set(zone.member_subject_ids for zone in at_t1.zones) & set(by_subject_t2)
    for key in common:
        first = next(zone for zone in at_t1.zones if zone.member_subject_ids == key)
        second = by_subject_t2[key]
        assert first.zone_key_id == second.zone_key_id


def test_score_history_contract_rejects_final_frame_conflict() -> None:
    history = scorer().build_batch(source_history())
    with pytest.raises(ResonanceScoringEngineError, match="final_frame"):
        replace(history, final_frame=history.frames[0])
    assert ResonanceScoreHistory.from_dict(history.to_dict()) == history


def test_normal_payloads_and_identities_remain_at_c007b_baseline() -> None:
    frame = scorer().score_frame(source_history().frames[1])
    history = scorer().build_batch(source_history())
    assert tuple(_payload_digest(item.to_dict()) for item in frame.zones) == (
        "eeb51b47e60622181c2d5517ff4f1f1d117cc7a08b7d3c2a9370f3f2de33327b",
        "e042374d34a88c1e3aa7a45edad6380b5fb943332bdfd2f4a84b93ad5aa253bc",
        "c6ca04edd13248dcef4f455a585bc39d90a520143c08c9ca1645e4e4677247f1",
        "6ae4a1fc76697b6b3fb2bc5e4fdb3d992eba5c3a57dbb341ed26409104484727",
    )
    assert _payload_digest(frame.to_dict()) == (
        "3a6d3d10f97137f6fea9f3cf53de574cd5777b2e915b062a2fe7c8e715c8db65"
    )
    assert _payload_digest(history.to_dict()) == (
        "3bf0923a68d679558a1b8e41194422c8ab24142abf367dcfe5ed90249d493fef"
    )
    assert tuple(item.zone_key_id for item in frame.zones) == (
        "resonance-zone-key-v1-f254fa7728aa86e621f4447f1dbbe8546b8ccd99a803e63a8a82991ee6a618c2",
        "resonance-zone-key-v1-f0e252d90e7024a6d22beb3118060a7daff759de6b7cb37f65ffb36d1c074905",
        "resonance-zone-key-v1-e55d010dbe3242bbbdd6f3b615695b3447790182e327d7eeda0a5d4d59317e89",
        "resonance-zone-key-v1-22eba589289e9fa3c1dc5cf89961a0e92c75ccafd5c9b9cf5a10725b4c680f9e",
    )
    assert tuple(item.zone_snapshot_id for item in frame.zones) == (
        "resonance-zone-snapshot-v1-a7b9d0dc431a12dab02ee99ebc0b2888b029dc46ee5ebe5722572b3138f9107f",
        "resonance-zone-snapshot-v1-f3f5d908baeff14f1b656cea01cff053cbf57e72658d1acbeda416110b01ce3a",
        "resonance-zone-snapshot-v1-e732605ee7496546421b7f90d122069ae19c36d2cecaf45cf653e48ad136a106",
        "resonance-zone-snapshot-v1-d751e9fe9459c42d398312f2fd52a754af8ad9de192474b97eb2866aef1e37ca",
    )
    assert tuple(
        tuple(item.contribution_id for item in zone.contributions)
        for zone in frame.zones
    ) == (
        (
            "resonance-contribution-v1-8760ede0f5c6c28dfa61f12cfc29af0682b17faac13e8a0a0d46674b7e681519",
            "resonance-contribution-v1-5dda832059b5915d401c74ac2915089c6bf835fef3fd45fafa0533917357feae",
        ),
        ("resonance-contribution-v1-9f4890e8a6d9a26e0a80d727684807faa87411a954e0c52cf9e38642fa08d8a2",),
        ("resonance-contribution-v1-3a5f4d1634714b4c0fe222ce23db2c6757e8d3fec84c0edd20d0d7829c64797b",),
        ("resonance-contribution-v1-710e33af3f9e8e6703494428b62bbe7771891de2a274a2dcad92185817bf6243",),
    )
    assert tuple(
        tuple(item.component_id for item in zone.dependency_components)
        for zone in frame.zones
    ) == (
        ("resonance-dependency-component-v1-595169b09c01bf74335fe6df75b92fb31d4b45aee472f547d5b4bce6077a3356",),
        ("resonance-dependency-component-v1-7c0219e87a31724a029b65bbfbc9bf76aece65c01cf97ee96da0ce438215b21c",),
        ("resonance-dependency-component-v1-a4ea217ce60950ede14912213cbcef60d999a461985df4a497adafb53ad314e1",),
        ("resonance-dependency-component-v1-783ae423299141055b9a7b7b24ed98a97a456a64fb848ddd4555c67a8dab212f",),
    )
    assert frame.score_frame_id == (
        "resonance-score-frame-v1-24e91806b1c645d3e71d38d364d22c4f969691b7b3255fadf72eb8cadda184b6"
    )
    assert tuple(item.score_frame_id for item in history.frames) == (
        "resonance-score-frame-v1-7d0558672ad34df0a2eda82f7c79168bd7b08edea0b2c6cbbcb9a06ed2411d26",
        "resonance-score-frame-v1-24e91806b1c645d3e71d38d364d22c4f969691b7b3255fadf72eb8cadda184b6",
        "resonance-score-frame-v1-d231a6bf25117338d41cb3f77d85f241a3b45d4d45053f92abe8bdc9a661e7e6",
        "resonance-score-frame-v1-7c6b6345e4aaf4e046d42ba9179a232e514857c90c55fe39db2522208ef2e241",
    )
