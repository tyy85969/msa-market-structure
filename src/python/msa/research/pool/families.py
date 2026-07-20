"""Deterministic dependency-family resolution and explanation grouping."""

from __future__ import annotations

from collections.abc import Iterable

from msa.domain import LevelCandidate

from .contracts import DependencyFamilyAssignment, DependencyGroup
from .errors import LevelPoolClusteringError


IMPLICIT_RATIONALE = "no explicit dependency evidence supplied"


def assignment_map(
    assignments: tuple[DependencyFamilyAssignment, ...],
) -> dict[str, DependencyFamilyAssignment]:
    """Return validated candidate-to-assignment lookup for internal use."""

    if not isinstance(assignments, tuple) or any(
        not isinstance(item, DependencyFamilyAssignment) for item in assignments
    ):
        raise LevelPoolClusteringError(
            "assignments must be a DependencyFamilyAssignment tuple"
        )
    result: dict[str, DependencyFamilyAssignment] = {}
    for item in assignments:
        if item.candidate_id in result:
            raise LevelPoolClusteringError("duplicate dependency assignment")
        result[item.candidate_id] = item
    return result


def dependency_family_id(
    candidate: LevelCandidate,
    assignments: dict[str, DependencyFamilyAssignment],
) -> str:
    """Resolve explicit evidence or the deterministic candidate-local family."""

    if not isinstance(candidate, LevelCandidate):
        raise LevelPoolClusteringError("candidate must be a LevelCandidate")
    assignment = assignments.get(candidate.candidate_id)
    return (
        assignment.dependency_family_id
        if assignment is not None
        else f"candidate:{candidate.candidate_id}"
    )


def build_dependency_groups(
    candidates: Iterable[LevelCandidate],
    assignments: dict[str, DependencyFamilyAssignment],
) -> tuple[DependencyGroup, ...]:
    """Group only the supplied cluster members without removing any evidence."""

    grouped: dict[str, list[LevelCandidate]] = {}
    for candidate in candidates:
        if not isinstance(candidate, LevelCandidate):
            raise LevelPoolClusteringError("dependency members must be candidates")
        family_id = dependency_family_id(candidate, assignments)
        grouped.setdefault(family_id, []).append(candidate)
    result: list[DependencyGroup] = []
    for family_id in sorted(grouped):
        members = tuple(sorted(grouped[family_id], key=lambda item: item.candidate_id))
        explicit = all(item.candidate_id in assignments for item in members)
        rationales = (
            tuple(
                sorted(
                    {
                        assignments[item.candidate_id].rationale
                        for item in members
                    }
                )
            )
            if explicit
            else (IMPLICIT_RATIONALE,)
        )
        result.append(
            DependencyGroup(
                dependency_family_id=family_id,
                member_candidate_ids=tuple(item.candidate_id for item in members),
                source_types=tuple(
                    sorted({item.source_type for item in members}, key=lambda x: x.value)
                ),
                timeframes=tuple(
                    sorted({item.timeframe for item in members}, key=lambda x: x.value)
                ),
                structure_families=tuple(
                    sorted({item.structure_family for item in members})
                ),
                explicit_assignment=explicit,
                rationales=rationales,
            )
        )
    return tuple(result)
