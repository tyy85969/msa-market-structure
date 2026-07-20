"""Public immutable domain model contract for MSA C-002."""

from .enums import (
    ActiveBoxStatus,
    BoundarySide,
    ConfirmationStatus,
    Direction,
    LifecycleState,
    MarketRole,
    StructureObjectKind,
    StructureSourceType,
)
from .errors import (
    DomainAvailabilityError,
    DomainSerializationError,
    DomainValidationError,
)
from .models import (
    ActiveBox,
    BoundaryRef,
    LevelCandidate,
    StructureCluster,
    TimeframeState,
)
from .primitives import PriceRange, ScaleDescriptor
from .provenance import ProvenanceRef

__all__ = [
    "ActiveBox",
    "ActiveBoxStatus",
    "BoundaryRef",
    "BoundarySide",
    "ConfirmationStatus",
    "DomainAvailabilityError",
    "DomainSerializationError",
    "DomainValidationError",
    "Direction",
    "LevelCandidate",
    "LifecycleState",
    "MarketRole",
    "PriceRange",
    "ProvenanceRef",
    "ScaleDescriptor",
    "StructureCluster",
    "StructureObjectKind",
    "StructureSourceType",
    "TimeframeState",
]
