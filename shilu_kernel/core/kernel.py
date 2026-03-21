"""
Solvra Kernel — Orchestrator
==============================
The single entry point for all kernel operations.
Coordinates all engines in the correct order, enforces safety priority,
and returns structured output with full provenance.
Spec Section 5 — System Architecture.
Spec Section 6.1 — Kernel Service Modules.

Usage:
    kernel = SolvraKernel()

    # Ingest a measurement
    result = kernel.ingest_measurement(user_id, signal_id, value, unit, timestamp)

    # Get current health picture for a signal
    picture = kernel.get_signal_picture(user_id, signal_id)

    # Get all active alerts (including non-suppressible)
    alerts = kernel.get_alerts(user_id)

    # Export user state
    export = kernel.export_state(user_id)
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Any

from shilu_kernel.models.entities import (
    Measurement, Finding, RiskFlag, Alert, EscalationEvent,
    DerivedFeature, UncertaintyLevel, RiskBand, AlertSeverity,
    AuditEventType, Actor, SIGNAL_DEFINITIONS, QualityFlag
)
from shilu_kernel.engines.audit_engine import AuditEngine
from shilu_kernel.engines.ingestion_service import IngestionService
from shilu_kernel.engines.baseline_engine import BaselineEngine
from shilu_kernel.engines.change_detector import ChangeDetector
from shilu_kernel.engines.safety_engine import SafetyEngine
from shilu_kernel.engines.explanation_generator import ExplanationGenerator, Explanation


@dataclass
class IngestResult:
    """Result of a measurement ingestion."""
    measurement: Measurement
    warnings:    List[str]
    alerts:      List[Alert]
    escalations: List[EscalationEvent]


@dataclass
class SignalPicture:
    """
    The complete current picture for a single signal.
    Every field carries provenance — this is the Evidence Ledger in action.
    """
    signal_id:      str
    signal_name:    str
    short_baseline: Optional[DerivedFeature]
    long_baseline:  Optional[DerivedFeature]
    findings:       List[Finding]
    risk_band:      Optional[RiskBand]
    uncertainty:    UncertaintyLevel
    explanation:    Explanation
    mvl_status:     Dict
    generated_at:   datetime = field(default_factory=datetime.utcnow)


class SolvraKernel:
    """
    The governed execution core of Solvra.

    Instantiate once per application. All engines share the same audit log.
    In production: wire each engine to persistent storage backends.
    In this prototype: all state is held in memory.
    """

    def __init__(self):
        # Single shared audit engine — all events flow through here
        self.audit       = AuditEngine()

        # Service modules (Spec Section 6.1)
        self.ingestion        = IngestionService(self.audit)
        self.baseline         = BaselineEngine(self.audit)
        self.detector         = ChangeDetector(self.audit)
        self.safety           = SafetyEngine(self.audit)
        self.explainer        = ExplanationGenerator()

        # Dual-reference architecture — population context layer
        # Runs alongside personal baseline engine, never replaces it
        from shilu_kernel.engines.baseline_engine import PopulationContextEngine
        self.population_context = PopulationContextEngine(self.audit)

    # ── INGEST ────────────────────────────────────────────────────────────────

    def ingest_measurement(
        self,
        user_id:     str,
        signal_id:   str,
        value:       float,
        unit:        str,
        timestamp:   datetime,
        notes:       Optional[str] = None,
        approximate: bool = False,
    ) -> IngestResult:
        """
        Accept a new measurement and immediately evaluate safety.
        Safety evaluation runs on every ingest — cannot be skipped.
        Returns the measurement, any warnings, and any triggered alerts.
        """
        # 1. Ingest and validate
        measurement, warnings = self.ingestion.ingest(
            user_id     = user_id,
            signal_id   = signal_id,
            value       = value,
            unit        = unit,
            timestamp   = timestamp,
            notes       = notes,
            approximate = approximate,
        )

        # 2. Safety evaluation — runs immediately on every ingest
        all_measurements = self.ingestion.get_measurements(user_id, signal_id=signal_id)
        alerts, escalations = self.safety.evaluate(
            user_id      = user_id,
            signal_id    = signal_id,
            measurements = all_measurements,
            findings     = [],   # simplified: full findings run in get_signal_picture
        )

        return IngestResult(
            measurement = measurement,
            warnings    = warnings,
            alerts      = alerts,
            escalations = escalations,
        )

    # ── SIGNAL PICTURE ────────────────────────────────────────────────────────

    def get_signal_picture(self, user_id: str, signal_id: str) -> SignalPicture:
        """
        Compute the complete current picture for a signal.
        Runs: baselines → change detection → risk flagging → safety → explanation.

        This is the primary analytical output of the kernel.
        Every element carries provenance per the Evidence Ledger design.
        """
        measurements = self.ingestion.get_measurements(user_id, signal_id=signal_id)
        sig = SIGNAL_DEFINITIONS.get(signal_id)
        sig_name = sig.name if sig else signal_id

        # 1. Baselines
        baselines = self.baseline.compute_baselines(user_id, signal_id, measurements)
        short_b = baselines["short"]
        long_b  = baselines["long"]
        uncertainty = baselines["uncertainty"]

        # 2. MVL status (transparent progress)
        mvl_status = self.baseline.mvl_status(user_id, signal_id, measurements)

        # 3. Change detection
        findings = self.detector.detect_all(
            user_id        = user_id,
            signal_id      = signal_id,
            measurements   = measurements,
            short_baseline = short_b,
            long_baseline  = long_b,
        )

        # 4. Risk flagging
        risk_flag = self._compute_risk_flag(user_id, signal_id, findings, uncertainty, short_b)

        # 5. Safety (comprehensive, with findings)
        self.safety.evaluate(
            user_id      = user_id,
            signal_id    = signal_id,
            measurements = measurements,
            findings     = findings,
        )

        # 6. Explanation — five-section template
        explanation = self.explainer.generate(
            user_id        = user_id,
            signal_id      = signal_id,
            findings       = findings,
            short_baseline = short_b,
            long_baseline  = long_b,
            risk_flag      = risk_flag,
            mvl_status     = mvl_status,
        )

        # 7. Population context assessment (dual-reference architecture)
        # Runs only when baseline is mature enough (MEDIUM or LOW uncertainty)
        # Generates a one-time calm BaselineContextNote if personal baseline
        # sits outside population reference ranges.
        # This is NOT a safety evaluation — it is contextual information only.
        if short_b is not None:
            self.population_context.assess_baseline_context(
                user_id           = user_id,
                signal_id         = signal_id,
                personal_baseline = short_b,
            )

        return SignalPicture(
            signal_id      = signal_id,
            signal_name    = sig_name,
            short_baseline = short_b,
            long_baseline  = long_b,
            findings       = findings,
            risk_band      = risk_flag.band if risk_flag else None,
            uncertainty    = uncertainty,
            explanation    = explanation,
            mvl_status     = mvl_status,
        )

    # ── ALERTS ────────────────────────────────────────────────────────────────

    def get_alerts(self, user_id: str, include_acknowledged: bool = True) -> List[Alert]:
        return self.safety.get_alerts(user_id, include_acknowledged)

    def acknowledge_alert(self, user_id: str, alert_id: str) -> bool:
        return self.safety.acknowledge(user_id, alert_id)

    def has_unacknowledged_urgent(self, user_id: str) -> bool:
        """UI must check this and gate navigation until resolved."""
        return self.safety.has_unacknowledged_urgent(user_id)

    # ── EXPORT ────────────────────────────────────────────────────────────────

    def export_state(self, user_id: str) -> Dict[str, Any]:
        """
        Export all user-owned data in a portable, human-readable format.
        Spec Section 3.1 — Export Service.
        Pillar 1 — user data is always exportable.
        """
        export = {
            "user_id":          user_id,
            "export_generated": datetime.utcnow().isoformat(),
            "solvra_version":   "kernel-v0.1-prototype",
            "measurements":     {},
            "baselines":        {},
            "findings":         [],
            "alerts":           [],
            "escalations":      [],
            "audit_integrity":  self.audit.verify_chain(),
        }

        # Measurements per signal
        for sig_id in SIGNAL_DEFINITIONS:
            measurements = self.ingestion.get_measurements(user_id, signal_id=sig_id)
            if measurements:
                export["measurements"][sig_id] = [
                    {
                        "id":            m.id,
                        "value":         m.value,
                        "unit":          m.unit,
                        "timestamp":     m.timestamp.isoformat(),
                        "quality_flags": [f.value for f in m.quality_flags],
                        "source_type":   m.source_type.value,
                        "notes":         m.notes,
                    }
                    for m in measurements
                ]

                # Baselines
                short_b = self.baseline.get_latest_baseline(user_id, sig_id, "short")
                long_b  = self.baseline.get_latest_baseline(user_id, sig_id, "long")
                if short_b or long_b:
                    export["baselines"][sig_id] = {
                        "short": {
                            "value":   short_b.value,
                            "method":  short_b.method,
                            "count":   short_b.measurement_count,
                            "window":  f"{short_b.window_start.date()} to {short_b.window_end.date()}",
                            "uncertainty": short_b.uncertainty.value,
                        } if short_b else None,
                        "long": {
                            "value":   long_b.value,
                            "method":  long_b.method,
                            "count":   long_b.measurement_count,
                            "window":  f"{long_b.window_start.date()} to {long_b.window_end.date()}",
                            "uncertainty": long_b.uncertainty.value,
                        } if long_b else None,
                    }

        # Alerts
        export["alerts"] = [
            {
                "id":             a.id,
                "severity":       a.severity.value,
                "title":          a.title,
                "message":        a.message,
                "safe_next_step": a.safe_next_step,
                "acknowledged":   a.acknowledged,
                "created_at":     a.created_at.isoformat(),
            }
            for a in self.safety.get_alerts(user_id)
        ]

        # Escalations
        export["escalations"] = [
            {
                "id":               e.id,
                "level":            e.escalation_level.value,
                "recommendation":   e.recommendation,
                "evidence_summary": e.evidence_summary,
                "triggered_at":     e.triggered_at.isoformat(),
            }
            for e in self.safety.get_escalations(user_id)
        ]

        # Audit log for this export
        self.audit.record(
            event_type  = AuditEventType.EXPORT_GENERATED,
            actor       = Actor.USER,
            entity_id   = user_id,
            entity_type = "user",
            details     = f"export_generated={export['export_generated']}",
        )

        return export

    # ── AUDIT ─────────────────────────────────────────────────────────────────

    def verify_audit_integrity(self) -> bool:
        """Verify the audit chain has not been tampered with."""
        return self.audit.verify_chain()

    # ── INTERNAL ──────────────────────────────────────────────────────────────

    def _compute_risk_flag(
        self,
        user_id:     str,
        signal_id:   str,
        findings:    List[Finding],
        uncertainty: UncertaintyLevel,
        baseline:    Optional[DerivedFeature],
    ) -> Optional[RiskFlag]:
        """
        Translate findings into a conservative risk band.
        Risk bands are non-diagnostic — they describe concern level, not conditions.
        Spec Section 10 — Risk Flagging.
        """
        if not findings and uncertainty == UncertaintyLevel.HIGH:
            return RiskFlag(
                user_id     = user_id,
                domain      = SIGNAL_DEFINITIONS.get(signal_id, type('',(),{'domain':'general'})()).domain if signal_id in SIGNAL_DEFINITIONS else "general",
                band        = RiskBand.MONITOR,
                uncertainty = UncertaintyLevel.HIGH,
                rationale   = "Insufficient data to establish a reliable picture. Continue monitoring.",
                finding_ids = [],
            )

        if not findings:
            return None

        from shilu_kernel.models.entities import FindingType
        has_drift    = any(f.finding_type == FindingType.SUSTAINED_DRIFT for f in findings)
        has_spike    = any(f.finding_type == FindingType.SPIKE for f in findings)
        has_coverage = any(f.finding_type == FindingType.COVERAGE_RISK for f in findings)
        high_conf    = any(f.confidence > 0.70 for f in findings)

        if has_drift and high_conf and uncertainty != UncertaintyLevel.HIGH:
            band = RiskBand.ELEVATED_CONCERN
        elif has_drift or has_spike:
            band = RiskBand.MONITOR
        elif has_coverage:
            band = RiskBand.MONITOR
        else:
            band = RiskBand.LOW_CONCERN

        sig = SIGNAL_DEFINITIONS.get(signal_id)
        domain = sig.domain if sig else "general"

        flag = RiskFlag(
            user_id     = user_id,
            domain      = domain,
            band        = band,
            uncertainty = uncertainty,
            rationale   = f"Based on {len(findings)} finding(s) detected across your {signal_id.replace('_', ' ')} readings.",
            finding_ids = [f.id for f in findings],
        )

        self.audit.record(
            event_type  = AuditEventType.RISKFLAG_CREATED,
            actor       = Actor.SYSTEM,
            entity_id   = flag.id,
            entity_type = "risk_flag",
            details     = f"user={user_id} signal={signal_id} band={band.value} uncertainty={uncertainty.value}",
        )

        return flag


    # ── DIGITAL TWIN STATUS ───────────────────────────────────────────────────

    def get_digital_twin_status(self, user_id: str) -> "DigitalTwinStatus":
        """
        Return the current phase of the user's digital twin across all signals.

        The digital twin begins at Phase 1 from the first measurement.
        Phase progression is transparent — users see exactly where their
        twin is and what it needs to advance.

        This is not a product tier or a paywall — it is an honest description
        of how well the kernel currently knows this individual.
        """
        from shilu_kernel.models.entities import (
            DigitalTwinPhase, DigitalTwinStatus, UncertaintyLevel
        )

        signals_in_phase = {}
        all_signals = SIGNAL_DEFINITIONS.keys()

        for signal_id in all_signals:
            measurements = self.ingestion.get_measurements(user_id, signal_id=signal_id)
            if not measurements:
                signals_in_phase[signal_id] = DigitalTwinPhase.PHASE_1_PERSONAL_RECORD
                continue

            # Check MVL status
            mvl = self.baseline.mvl_status(user_id, signal_id, measurements)
            if not mvl.get("threshold_met", False):
                signals_in_phase[signal_id] = DigitalTwinPhase.PHASE_1_PERSONAL_RECORD
                continue

            # Check baseline quality
            baselines = self.baseline.compute_baselines(user_id, signal_id, measurements)
            short_b = baselines.get("short")
            long_b  = baselines.get("long")

            if short_b is None:
                signals_in_phase[signal_id] = DigitalTwinPhase.PHASE_1_PERSONAL_RECORD
                continue

            if long_b is None or baselines.get("uncertainty") == UncertaintyLevel.HIGH:
                signals_in_phase[signal_id] = DigitalTwinPhase.PHASE_2_BASELINE_MODEL
                continue

            # If both baselines exist and uncertainty is medium or low → trajectory capable
            signals_in_phase[signal_id] = DigitalTwinPhase.PHASE_3_TRAJECTORY_MODEL

        # Overall phase = most common phase across signals (conservative)
        phase_counts = {}
        for p in signals_in_phase.values():
            phase_counts[p] = phase_counts.get(p, 0) + 1

        phase_order = [
            DigitalTwinPhase.PHASE_1_PERSONAL_RECORD,
            DigitalTwinPhase.PHASE_2_BASELINE_MODEL,
            DigitalTwinPhase.PHASE_3_TRAJECTORY_MODEL,
        ]
        # Overall = lowest phase that majority of signals have reached
        overall_phase = DigitalTwinPhase.PHASE_1_PERSONAL_RECORD
        for phase in phase_order:
            count = sum(1 for p in signals_in_phase.values() if p.value >= phase.value)
            if count >= len(signals_in_phase) * 0.5:
                overall_phase = phase

        maturity_messages = {
            DigitalTwinPhase.PHASE_1_PERSONAL_RECORD: (
                "Your digital twin is forming. Solvra is collecting your personal health data "
                "and building the foundation of your individual model. Keep logging consistently — "
                "every measurement makes your twin more accurate and more yours."
            ),
            DigitalTwinPhase.PHASE_2_BASELINE_MODEL: (
                "Your digital twin has established personal baselines for most of your signals. "
                "Solvra now knows what your numbers look like when you are at your normal — "
                "not the population average, but your specific pattern. Change detection is active."
            ),
            DigitalTwinPhase.PHASE_3_TRAJECTORY_MODEL: (
                "Your digital twin is tracking your trajectory. Solvra can now detect sustained "
                "drift, volatility changes, and meaningful patterns across your history. "
                "The longer your record grows, the more personal and precise your twin becomes."
            ),
        }

        return DigitalTwinStatus(
            user_id           = user_id,
            overall_phase     = overall_phase,
            signals_in_phase  = signals_in_phase,
            maturity_message  = maturity_messages[overall_phase],
        )

    def get_baseline_context_notes(self, user_id: str) -> List:
        """
        Return any active (non-dormant) BaselineContextNotes for a user.
        These are one-time calm notes surfaced when a personal baseline
        sits outside population reference ranges.
        Not escalations. Not alerts. Informational context only.
        """
        return self.population_context.get_active_notes(user_id)

    def acknowledge_baseline_context_note(self, user_id: str, signal_id: str) -> bool:
        """
        User acknowledges a BaselineContextNote.
        After acknowledgment the note goes dormant and will not re-surface
        unless the baseline shifts materially.
        """
        return self.population_context.acknowledge_note(user_id, signal_id)
