"""Stateless C-008B structural metric evaluator."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_EVEN, localcontext

from msa.research.msa_core import MSACoreRun
from msa.validation import CausalAuditor, MSAValidationError
from msa.validation import ValidationMetricName

from .contracts import (
    METRIC_REPORT_ASSUMPTIONS,
    METRIC_REPORT_PROVENANCE_ENTRY,
    MetricEvaluationReport,
    MetricObservationStatus,
    StructuralMetricConfig,
    resolve_metric_config,
)
from .errors import MetricInputError
from .events import _extract_events, resolve_evaluation_as_of
from .formula_registry import default_metric_formula_registry
from .identity import DECIMAL_PRECISION, digest, semantic_id
from .matching import match_resonance_outcomes
from .observations import _observations, build_metric_aggregates


@dataclass(frozen=True, slots=True)
class StructuralMetricEvaluator:
    """Frozen, stateless structural evaluation facade."""

    config: StructuralMetricConfig = StructuralMetricConfig()

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "config", resolve_metric_config(self.config)
        )

    def evaluate(
        self,
        run: MSACoreRun,
        evaluation_as_of_time: datetime | None = None,
    ) -> MetricEvaluationReport:
        if not isinstance(run, MSACoreRun):
            raise MetricInputError("run must be an MSACoreRun")
        cutoff = resolve_evaluation_as_of(run, evaluation_as_of_time)
        try:
            with localcontext() as context:
                context.prec = 28
                context.rounding = ROUND_HALF_EVEN
                audit = CausalAuditor().audit_run(run)
        except MSAValidationError as exc:
            raise MetricInputError(
                "MSACoreRun could not be audited safely"
            ) from exc
        if not audit.passed:
            raise MetricInputError(
                "MSACoreRun failed the independent CausalAuditor"
            )
        try:
            source_run_payload_digest = digest(run.to_dict())
        except (
            AttributeError,
            KeyError,
            TypeError,
            AssertionError,
            ValueError,
        ) as exc:
            raise MetricInputError(
                "MSACoreRun payload could not be digested safely"
            ) from exc
        formulas = default_metric_formula_registry()
        with localcontext() as context:
            context.prec = DECIMAL_PRECISION
            context.rounding = ROUND_HALF_EVEN
            events = _extract_events(run, self.config, cutoff)
            base_observations = _observations(
                run, events, self.config, cutoff
            )
            resonance_formula = next(
                item
                for item in formulas
                if item.metric_name
                is ValidationMetricName.RESONANCE_LIFT
            )
            matches, pair_observations = match_resonance_outcomes(
                events,
                base_observations,
                resonance_formula,
                self.config,
            )
            observations = (*base_observations, *pair_observations)
            aggregates = build_metric_aggregates(
                formulas, observations, self.config
            )
        provenance = (
            METRIC_REPORT_PROVENANCE_ENTRY,
            f"source_run_id={run.run_id}",
            f"source_run_payload_digest={source_run_payload_digest}",
            f"evaluation_as_of_time={cutoff.isoformat()}",
            f"engine_id={self.config.engine_id}",
        )
        matured = sum(
            item.status is MetricObservationStatus.MATURED
            for item in observations
        )
        censored = sum(
            item.status is MetricObservationStatus.CENSORED_RIGHT
            for item in observations
        )
        unavailable = sum(
            item.status is MetricObservationStatus.UNAVAILABLE_INPUT
            for item in observations
        )
        payload = {
            "source_run_id": run.run_id,
            "evaluation_as_of_time": cutoff.isoformat(),
            "config_snapshot": self.config.to_dict(),
            "formula_registry": [item.to_dict() for item in formulas],
            "events": [item.to_dict() for item in events],
            "observations": [
                item.to_dict() for item in observations
            ],
            "resonance_matches": [
                item.to_dict() for item in matches
            ],
            "aggregates": [item.to_dict() for item in aggregates],
            "event_count": len(events),
            "matured_observation_count": matured,
            "censored_observation_count": censored,
            "unavailable_observation_count": unavailable,
            "assumptions": list(METRIC_REPORT_ASSUMPTIONS),
            "warnings": [],
            "provenance": list(provenance),
            "schema_version": 1,
        }
        return MetricEvaluationReport(
            metric_report_id=semantic_id(
                "metric-evaluation-report-v1-", payload
            ),
            source_run_id=run.run_id,
            evaluation_as_of_time=cutoff,
            config_snapshot=self.config,
            formula_registry=formulas,
            events=events,
            observations=observations,
            resonance_matches=matches,
            aggregates=aggregates,
            event_count=len(events),
            matured_observation_count=matured,
            censored_observation_count=censored,
            unavailable_observation_count=unavailable,
            assumptions=METRIC_REPORT_ASSUMPTIONS,
            warnings=(),
            provenance=provenance,
        )


def evaluate_structural_metrics(
    run: MSACoreRun,
    config: StructuralMetricConfig | None = None,
    evaluation_as_of_time: datetime | None = None,
) -> MetricEvaluationReport:
    """Evaluate a causally audited Run with no hidden state."""

    return StructuralMetricEvaluator(
        resolve_metric_config(config)
    ).evaluate(run, evaluation_as_of_time)


def validate_metric_evaluation_report(
    run: MSACoreRun,
    report: MetricEvaluationReport,
) -> MetricEvaluationReport:
    """Prove that a formal report exactly recomputes from a formal source Run."""

    from .errors import MetricReportError, StructuralMetricError

    if not isinstance(run, MSACoreRun):
        raise MetricInputError("run must be an MSACoreRun")
    if not isinstance(report, MetricEvaluationReport):
        raise MetricReportError(
            "report must be a MetricEvaluationReport"
        )
    try:
        report_payload = report.to_dict()
        canonical_report = MetricEvaluationReport.from_dict(report_payload)
    except StructuralMetricError as exc:
        raise MetricReportError(
            "report failed formal structural validation"
        ) from exc
    except (
        AttributeError,
        KeyError,
        TypeError,
        AssertionError,
        ValueError,
    ) as exc:
        raise MetricReportError(
            "report could not be inspected safely"
        ) from exc
    expected = StructuralMetricEvaluator(
        canonical_report.config_snapshot
    ).evaluate(run, canonical_report.evaluation_as_of_time)
    if expected.to_dict() != report_payload:
        raise MetricReportError(
            "report does not exactly recompute from the supplied source Run"
        )
    return report
