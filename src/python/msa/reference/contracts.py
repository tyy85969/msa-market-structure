"""Immutable authority-bound contracts for Core Alpha reference profiles."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, fields
from typing import Any

from msa.research.msa_core import MSACoreConfig, MSACoreError

from .errors import (
    MSAReferenceError,
    ReferenceAuthorityError,
    ReferenceConfigurationError,
    ReferenceInputError,
    ReferenceSerializationError,
)
from .identity import digest, require_semantic_id, semantic_id


SCHEMA_VERSION = 1
CORE_ALPHA_V1_PROFILE_ID = "msa-core-alpha-v1"
CORE_ALPHA_V1_PROFILE_VERSION = "1.0.0"
CORE_ALPHA_V1_REFERENCE_COMMIT_SHA = (
    "d72c18f7994afd506e6ecf044571ccffbc695631"
)
CORE_ALPHA_V1_SOURCE_AUTHORITY = (
    "Exact serialized payload was promoted by explicit project-owner approval.",
    "Authorized source: tests.research.msa_core.fixtures.config().to_dict()",
    "Authorized source commit: d72c18f7994afd506e6ecf044571ccffbc695631",
    "Production code does not import test modules.",
    "No parameter optimization or modification occurred.",
    "The profile is a semantic reference, not a profitability claim.",
)
CORE_ALPHA_V1_ASSUMPTIONS = (
    "Core Alpha v1 is an explicit semantic reference profile, not a universal default.",
    "Parameters have not been optimized for XAUUSD or any other market.",
    "Active Box is a structural research object, not a trading signal.",
    "This profile establishes neither profitability nor production readiness.",
)


_AUTHORIZED_CORE_CONFIG_JSON = """{
  "active_box_config": {
    "absolute_replacement_distance_margin": "1",
    "allowed_resonance_classes": [
      "LOCAL_CLUSTER",
      "MULTI_CONTEXT_RESONANCE",
      "SINGLE"
    ],
    "engine_id": "c007c-active-box-contract",
    "engine_version": "1.0.0",
    "minimum_quality_score": "0",
    "minimum_replacement_selection_score_improvement": "0.1",
    "minimum_selection_score": "0.25",
    "output_scale": {
      "rank": 1,
      "scale_id": "primary",
      "schema_version": 1
    },
    "output_timeframe": "H4",
    "policy_id": "nearest-qualified-hysteresis-v1",
    "reference_replacement_distance_fraction": null,
    "replacement_distance_mode": "ABSOLUTE",
    "require_expected_side": true,
    "require_positive_distance_factor": true,
    "schema_version": 1,
    "selection_policy": "NEAREST_QUALIFIED_WITH_HYSTERESIS",
    "strict": true,
    "symbol": "XAUUSD"
  },
  "engine_id": "c007d-msa-core",
  "engine_version": "1.0.0",
  "frame_config": {
    "contexts": [
      {
        "scale": {
          "rank": 2,
          "scale_id": "macro",
          "schema_version": 1
        },
        "schema_version": 1,
        "timeframe": "H12"
      },
      {
        "scale": {
          "rank": 1,
          "scale_id": "primary",
          "schema_version": 1
        },
        "schema_version": 1,
        "timeframe": "H4"
      }
    ],
    "engine_id": "c007a-resonance-frame",
    "engine_version": "1.0.0",
    "evidence_policy": "ALL_EFFECTIVE_LIFECYCLE_STATES",
    "policy_id": "all-effective-lifecycle-v1",
    "reference_price_field": "CLOSE",
    "reference_price_timeframe": "H1",
    "schema_version": 1,
    "strict": true,
    "symbol": "XAUUSD"
  },
  "policy_id": "causal-msa-core-alpha-v1",
  "schema_version": 1,
  "scoring_config": {
    "absolute_distance_horizon": "50",
    "absolute_tolerance": "1",
    "aligned_direction_factor": "1",
    "candidate_tier_weight": "0.5",
    "clustering_policy": "SIDE_SEPARATED_SINGLE_LINK",
    "confirmed_tier_weight": "1",
    "contains_price_factor": "0.8",
    "context_diversity_bonus_cap": "1",
    "context_diversity_bonus_per_extra": "0.3",
    "context_weights": [
      {
        "context": {
          "scale": {
            "rank": 2,
            "scale_id": "macro",
            "schema_version": 1
          },
          "schema_version": 1,
          "timeframe": "H12"
        },
        "schema_version": 1,
        "weight": "2"
      },
      {
        "context": {
          "scale": {
            "rank": 1,
            "scale_id": "primary",
            "schema_version": 1
          },
          "schema_version": 1,
          "timeframe": "H4"
        },
        "schema_version": 1,
        "weight": "1"
      }
    ],
    "dependency_repeat_credit": "0.25",
    "distance_horizon_mode": "ABSOLUTE",
    "engine_id": "c007b-resonance-scoring",
    "engine_version": "1.0.0",
    "expected_side_factor": "1",
    "flipped_lifecycle_weight": "0.7",
    "fresh_lifecycle_weight": "1",
    "freshness_floor": "0.2",
    "freshness_horizon_seconds": "86400",
    "minimum_resonant_context_count": 2,
    "minimum_resonant_evidence_count": 2,
    "neutral_direction_factor": "0.8",
    "opposed_direction_factor": "0.5",
    "opposite_side_factor": "0.2",
    "policy_id": "side-separated-single-link-v1",
    "reference_distance_fraction": null,
    "reference_tolerance_fraction": null,
    "schema_version": 1,
    "source_diversity_bonus_cap": "1",
    "source_diversity_bonus_per_extra": "0.2",
    "strict": true,
    "tested_lifecycle_weight": "0.9",
    "tolerance_mode": "ABSOLUTE",
    "touch_floor": "0.5",
    "touch_penalty_per_extra": "0.1",
    "turning_direction_factor": "0.7",
    "unknown_direction_factor": "0.6",
    "weakened_lifecycle_weight": "0.8"
  },
  "strict": true
}"""


def _authorized_core_config_payload() -> dict[str, object]:
    try:
        value = json.loads(_AUTHORIZED_CORE_CONFIG_JSON)
    except (TypeError, ValueError) as exc:
        raise ReferenceConfigurationError(
            "frozen Core Alpha v1 payload is invalid JSON"
        ) from exc
    if not isinstance(value, dict):
        raise ReferenceConfigurationError(
            "frozen Core Alpha v1 payload must be a mapping"
        )
    return value


def _schema(value: object, object_name: str, error_type: type[ValueError]) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise error_type(f"{object_name}.schema_version must be an integer")
    if value != SCHEMA_VERSION:
        raise error_type(
            f"{object_name}.schema_version must equal {SCHEMA_VERSION}"
        )
    return value


def _text(value: object, field_name: str, error_type: type[ValueError]) -> str:
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise error_type(f"{field_name} must be non-empty single-line text")
    return value


def _text_tuple(
    value: object, field_name: str, error_type: type[ValueError]
) -> tuple[str, ...]:
    if (
        not isinstance(value, tuple)
        or not value
        or any(
            not isinstance(item, str)
            or not item
            or "\n" in item
            or "\r" in item
            for item in value
        )
        or len(set(value)) != len(value)
    ):
        raise error_type(
            f"{field_name} must be a non-empty tuple of unique single-line text"
        )
    return value


def _exact_payload(
    payload: object, object_name: str, field_names: set[str]
) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping):
        raise ReferenceSerializationError(
            f"{object_name} payload must be a mapping"
        )
    if any(not isinstance(key, str) for key in payload):
        raise ReferenceSerializationError(
            f"{object_name} payload keys must be strings"
        )
    expected = field_names | {"schema_version"}
    if set(payload) != expected:
        raise ReferenceSerializationError(
            f"{object_name} payload fields must equal {sorted(expected)}"
        )
    _schema(payload["schema_version"], object_name, ReferenceSerializationError)
    return payload


def validate_core_alpha_v1_config(value: object) -> MSACoreConfig:
    """Require the exact, formally round-trippable authorized Core config."""

    if not isinstance(value, MSACoreConfig):
        raise ReferenceInputError("value must be an MSACoreConfig")
    try:
        payload = value.to_dict()
        restored = MSACoreConfig.from_dict(payload)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ReferenceConfigurationError(
            "value is not a formal MSACoreConfig"
        ) from exc
    if restored != value or restored.to_dict() != payload:
        raise ReferenceConfigurationError(
            "MSACoreConfig must complete an exact formal round trip"
        )
    if payload != _authorized_core_config_payload():
        raise ReferenceAuthorityError(
            "MSACoreConfig does not equal the authorized Core Alpha v1 payload"
        )
    return value


@dataclass(frozen=True, slots=True)
class CoreBaselineProfile:
    profile_semantic_id: str
    profile_id: str
    profile_version: str
    reference_commit_sha: str
    core_config: MSACoreConfig
    core_config_payload_digest: str
    source_authority: tuple[str, ...]
    assumptions: tuple[str, ...]
    schema_version: int = SCHEMA_VERSION

    def _identity_payload(self) -> dict[str, object]:
        return {
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "reference_commit_sha": self.reference_commit_sha,
            "core_config": self.core_config.to_dict(),
            "core_config_payload_digest": self.core_config_payload_digest,
            "source_authority": list(self.source_authority),
            "assumptions": list(self.assumptions),
            "schema_version": self.schema_version,
        }

    def __post_init__(self) -> None:
        name = type(self).__name__
        _schema(self.schema_version, name, ReferenceConfigurationError)
        for field_name in (
            "profile_semantic_id",
            "profile_id",
            "profile_version",
            "reference_commit_sha",
            "core_config_payload_digest",
        ):
            _text(
                getattr(self, field_name),
                f"{name}.{field_name}",
                ReferenceConfigurationError,
            )
        if self.profile_id != CORE_ALPHA_V1_PROFILE_ID:
            raise ReferenceAuthorityError(
                "profile_id must equal the authorized Core Alpha v1 ID"
            )
        if self.profile_version != CORE_ALPHA_V1_PROFILE_VERSION:
            raise ReferenceAuthorityError(
                "profile_version must equal the authorized Core Alpha v1 version"
            )
        if self.reference_commit_sha != CORE_ALPHA_V1_REFERENCE_COMMIT_SHA:
            raise ReferenceAuthorityError(
                "reference_commit_sha must equal the authorized source commit"
            )
        validate_core_alpha_v1_config(self.core_config)
        expected_digest = digest(self.core_config.to_dict())
        if self.core_config_payload_digest != expected_digest:
            raise ReferenceAuthorityError(
                "core_config_payload_digest must bind the complete config payload"
            )
        _text_tuple(
            self.source_authority,
            f"{name}.source_authority",
            ReferenceConfigurationError,
        )
        if self.source_authority != CORE_ALPHA_V1_SOURCE_AUTHORITY:
            raise ReferenceAuthorityError(
                "source_authority must equal the approved authority statement"
            )
        _text_tuple(
            self.assumptions,
            f"{name}.assumptions",
            ReferenceConfigurationError,
        )
        if self.assumptions != CORE_ALPHA_V1_ASSUMPTIONS:
            raise ReferenceAuthorityError(
                "assumptions must equal the frozen Core Alpha v1 assumptions"
            )
        require_semantic_id(
            self.profile_semantic_id,
            prefix="core-baseline-profile-v1-",
            payload=self._identity_payload(),
            field_name="profile_semantic_id",
            error_type=ReferenceAuthorityError,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "profile_semantic_id": self.profile_semantic_id,
            "profile_id": self.profile_id,
            "profile_version": self.profile_version,
            "reference_commit_sha": self.reference_commit_sha,
            "core_config": self.core_config.to_dict(),
            "core_config_payload_digest": self.core_config_payload_digest,
            "source_authority": list(self.source_authority),
            "assumptions": list(self.assumptions),
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> CoreBaselineProfile:
        names = {item.name for item in fields(cls)} - {"schema_version"}
        data = _exact_payload(payload, cls.__name__, names)
        try:
            return cls(
                profile_semantic_id=data["profile_semantic_id"],
                profile_id=data["profile_id"],
                profile_version=data["profile_version"],
                reference_commit_sha=data["reference_commit_sha"],
                core_config=MSACoreConfig.from_dict(data["core_config"]),
                core_config_payload_digest=data[
                    "core_config_payload_digest"
                ],
                source_authority=tuple(data["source_authority"]),
                assumptions=tuple(data["assumptions"]),
                schema_version=data["schema_version"],
            )
        except MSAReferenceError as exc:
            raise ReferenceSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc
        except (MSACoreError, AttributeError, KeyError, TypeError, ValueError) as exc:
            raise ReferenceSerializationError(
                f"invalid serialized {cls.__name__}"
            ) from exc


def _build_core_alpha_v1_profile(config: MSACoreConfig) -> CoreBaselineProfile:
    config_digest = digest(config.to_dict())
    identity_payload = {
        "profile_id": CORE_ALPHA_V1_PROFILE_ID,
        "profile_version": CORE_ALPHA_V1_PROFILE_VERSION,
        "reference_commit_sha": CORE_ALPHA_V1_REFERENCE_COMMIT_SHA,
        "core_config": config.to_dict(),
        "core_config_payload_digest": config_digest,
        "source_authority": list(CORE_ALPHA_V1_SOURCE_AUTHORITY),
        "assumptions": list(CORE_ALPHA_V1_ASSUMPTIONS),
        "schema_version": SCHEMA_VERSION,
    }
    return CoreBaselineProfile(
        profile_semantic_id=semantic_id(
            "core-baseline-profile-v1-", identity_payload
        ),
        profile_id=CORE_ALPHA_V1_PROFILE_ID,
        profile_version=CORE_ALPHA_V1_PROFILE_VERSION,
        reference_commit_sha=CORE_ALPHA_V1_REFERENCE_COMMIT_SHA,
        core_config=config,
        core_config_payload_digest=config_digest,
        source_authority=CORE_ALPHA_V1_SOURCE_AUTHORITY,
        assumptions=CORE_ALPHA_V1_ASSUMPTIONS,
    )


def validate_core_alpha_v1_profile(value: object) -> CoreBaselineProfile:
    """Require complete formal validity and exact Core Alpha v1 authority."""

    if not isinstance(value, CoreBaselineProfile):
        raise ReferenceInputError("value must be a CoreBaselineProfile")
    try:
        payload = value.to_dict()
        restored = CoreBaselineProfile.from_dict(payload)
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise ReferenceConfigurationError(
            "value is not a formal CoreBaselineProfile"
        ) from exc
    expected_config = MSACoreConfig.from_dict(_authorized_core_config_payload())
    expected = _build_core_alpha_v1_profile(expected_config)
    if restored != value or payload != expected.to_dict():
        raise ReferenceAuthorityError(
            "profile does not equal the authorized Core Alpha v1 profile"
        )
    return value
