from .fixtures import replay_with_extra, score_history, selector


def test_batch_and_replay_repeated_payloads_are_identical() -> None:
    value = selector()
    source = score_history()
    explicit = replay_with_extra()
    assert value.build_batch(source).to_dict() == value.build_batch(source).to_dict()
    from msa.research.active_box import replay_active_box_history

    assert (
        replay_active_box_history(value, source, explicit).to_dict()
        == replay_active_box_history(value, source, explicit).to_dict()
    )


def test_no_runtime_mutable_cache_is_added() -> None:
    value = selector()
    value.build_batch(score_history())
    assert not hasattr(value, "__dict__")
    assert tuple(value.__slots__) == ("config",)
