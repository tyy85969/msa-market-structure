"""Immutable provenance values for traceable structure objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from .errors import DomainValidationError
from .primitives import (
    SCHEMA_VERSION,
    _canonical_text_tuple,
    _deserialize_list,
    _require_non_empty_text,
    _require_optional_text,
    _strict_payload,
    _wrap_validation,
)


@dataclass(frozen=True, slots=True)
class ProvenanceRef:
    """Finite, non-nested source identity and parent lineage snapshot."""

    source_module: str
    source_version: str
    source_object_id: str
    policy_id: str | None
    parent_object_ids: tuple[str, ...]
    notes: tuple[str, ...]

    def __post_init__(self) -> None:
        object_name = type(self).__name__
        _require_non_empty_text(object_name, "source_module", self.source_module)
        _require_non_empty_text(object_name, "source_version", self.source_version)
        _require_non_empty_text(
            object_name, "source_object_id", self.source_object_id
        )
        _require_optional_text(object_name, "policy_id", self.policy_id)
        parents = _canonical_text_tuple(
            object_name,
            "parent_object_ids",
            self.parent_object_ids,
            non_empty=False,
            unique=True,
            sort_values=True,
        )
        notes = _canonical_text_tuple(
            object_name,
            "notes",
            self.notes,
            non_empty=False,
            unique=False,
            sort_values=False,
        )
        object.__setattr__(self, "parent_object_ids", parents)
        object.__setattr__(self, "notes", notes)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "source_module": self.source_module,
            "source_version": self.source_version,
            "source_object_id": self.source_object_id,
            "policy_id": self.policy_id,
            "parent_object_ids": list(self.parent_object_ids),
            "notes": list(self.notes),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ProvenanceRef:
        object_name = cls.__name__
        fields = {
            "source_module",
            "source_version",
            "source_object_id",
            "policy_id",
            "parent_object_ids",
            "notes",
        }
        data = _strict_payload(payload, object_name, fields)
        try:
            return cls(
                source_module=data["source_module"],
                source_version=data["source_version"],
                source_object_id=data["source_object_id"],
                policy_id=data["policy_id"],
                parent_object_ids=tuple(
                    _deserialize_list(data, object_name, "parent_object_ids")
                ),
                notes=tuple(_deserialize_list(data, object_name, "notes")),
            )
        except DomainValidationError as exc:
            _wrap_validation(object_name, exc)
