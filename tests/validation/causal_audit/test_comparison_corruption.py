from __future__ import annotations

from copy import deepcopy

import pytest

from msa.validation import CausalAuditor, ValidationComparisonError

from .fixtures import valid_prefix_pair, valid_shared_asof_pair


def _corrupt(run, attack: str) -> None:
    if attack == "schedule_container":
        object.__setattr__(run, "processing_times", [])
    elif attack == "schedule_value":
        object.__setattr__(
            run,
            "processing_times",
            (run.processing_times[0], object()),
        )
    elif attack == "bundle_asof":
        object.__setattr__(
            run.frame_bundles[0], "as_of_time", []
        )
    elif attack == "events_container":
        object.__setattr__(run.active_box_history, "events", object())
    elif attack == "events_member":
        object.__setattr__(
            run.active_box_history, "events", (object(),)
        )
    elif attack == "event_confirm":
        object.__setattr__(
            run.active_box_history.events[0],
            "event_confirm_time",
            [],
        )
    elif attack == "frozen_container":
        object.__setattr__(
            run.active_box_history, "frozen_boxes", object()
        )
    elif attack == "frozen_member":
        object.__setattr__(
            run.active_box_history, "frozen_boxes", (object(),)
        )
    elif attack == "frozen_confirm":
        object.__setattr__(
            run.active_box_history.frozen_boxes[0].active_box,
            "confirm_time",
            [],
        )
    else:
        raise AssertionError(attack)


@pytest.mark.parametrize(
    "attack",
    (
        "schedule_container",
        "schedule_value",
        "bundle_asof",
        "events_container",
        "events_member",
        "event_confirm",
        "frozen_container",
        "frozen_member",
        "frozen_confirm",
    ),
)
@pytest.mark.parametrize("comparison", ("prefix", "shared"))
def test_prefix_and_shared_comparisons_fail_closed_on_corruption(
    attack: str,
    comparison: str,
) -> None:
    if comparison == "prefix":
        left, right = valid_prefix_pair()
        cutoff = None
    else:
        left, right, cutoff = valid_shared_asof_pair()
    damaged = deepcopy(left)
    _corrupt(damaged, attack)

    with pytest.raises(ValidationComparisonError):
        if comparison == "prefix":
            CausalAuditor().compare_prefix(damaged, right)
        else:
            CausalAuditor().compare_shared_asof(
                damaged, right, cutoff
            )


def test_prefix_relationship_corruption_fails_closed() -> None:
    prefix, extended = valid_prefix_pair()
    damaged = deepcopy(prefix)
    object.__setattr__(
        damaged,
        "processing_times",
        (
            prefix.processing_times[0],
            extended.processing_times[-1],
        ),
    )

    with pytest.raises(ValidationComparisonError):
        CausalAuditor().compare_prefix(damaged, extended)
