"""Canonical market-data contracts, source adapters, and quality reports."""

from msa.data.contracts import (
    CanonicalBar,
    ContractValidationError,
    IncompleteBarError,
    Timeframe,
    VolumeType,
)
from msa.data.loaders import DataLoadError, LoadResult, load_csv, load_records
from msa.data.quality import (
    DataQualityIssue,
    DataQualityReport,
    IssueSeverity,
    validate_bar_sequence,
)
from msa.data.source_config import (
    CompletedBarPolicy,
    SourceConfigurationError,
    SourceDataConfig,
    TimestampSemantics,
)

__all__ = [
    "CanonicalBar",
    "CompletedBarPolicy",
    "ContractValidationError",
    "DataLoadError",
    "DataQualityIssue",
    "DataQualityReport",
    "IncompleteBarError",
    "IssueSeverity",
    "LoadResult",
    "SourceConfigurationError",
    "SourceDataConfig",
    "Timeframe",
    "TimestampSemantics",
    "VolumeType",
    "load_csv",
    "load_records",
    "validate_bar_sequence",
]
