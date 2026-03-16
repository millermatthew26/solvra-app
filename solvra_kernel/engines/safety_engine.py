"""
Solvra Kernel — Safety & Escalation Engine
============================================
Non-bypassable safety logic. Highest priority in the kernel.
Spec Section 23 — Safety & Escalation Engine.
Spec Section 13 — v0.1 Safety rules.

If a safety rule triggers, the system MUST produce an Alert
and EscalationEvent regardless of any user preference or setting.

Three escalation levels (from risk analysis):
  Level 1 — Awareness:     informational, dismissible
  Level 2 — Prompt Action: requires explicit acknowledgment
  Level 3 — Urgent:        non-dismissible, seek immediate care

Pillar 2 — Safety Before Autonomy:
  "Certain risks cannot be hidden or suppressed."
"""

from datetime import datetime, timedelta
from typing import List, Optional, Tuple

from solvra_kernel.models.entities import (
    Measurement, Finding, Alert, EscalationEvent,
    AlertSeverity, EscalationLevel, UncertaintyLevel,
    AuditEventType, Actor, SIGNAL_DEFINITIONS
)
from solvra_kernel.config.thresholds import SAFETY_THRESHOLDS
from solvra_kernel.engines.audit_engine import AuditEngine


class SafetyEngine:

    def __init__(self, audit_engine: AuditEngine):
        self.audit    = audit_engine
        self._alerts:      List[Alert] = []
        self._escalations: List[EscalationEvent] = []

    # ── MAIN EVALUATION ───────────────────────────────────────────────────────

    def evaluate(
        self,
        user_id:      str,
        signal_id:    str,
        measurements: List[Measurement],
        findings:     List[Finding],
    ) -> Tuple[List[Alert], List[EscalationEvent]]:
        """
        Evaluate all safety rules for a signal.
        Returns (alerts, escalation_events) — both may be empty.

        This method cannot be bypassed, suppressed, or disabled.
        """
        new_alerts:      List[Alert] = []
        new_escalations: List[EscalationEvent] = []

        valid = [m for m in measurements if not m.is_deleted]
        if not valid:
            return new_alerts, new_escalations

        # Rule 1: Single-reading threshold check (Immediate Red Flag)
        alert, escalation = self._check_single_reading(user_id, signal_id, valid)
        if alert:
            new_alerts.append(alert)
        if escalation:
            new_escalations.append(escalation)

        # Rule 2: Sustained pattern threshold check (Pattern Red Flag)
        alert, escalation = self._check_sustained_pattern(user_id, signal_id, valid, findings)
        if alert:
            new_alerts.append(alert)
        if escalation:
            new_escalations.append(escalation)

        # Store and audit all new events
        for alert in new_alerts:
            self._alerts.append(alert)
            self.audit.record(
                event_type  = AuditEventType.ALERT_ISSUED,
                actor       = Actor.SYSTEM,
                entity_id   = alert.id,
                entity_type = "alert",
                details     = f"user={user_id} signal={signal_id} severity={alert.severity.value} level={alert.escalation_level}",
            )

        for esc in new_escalations:
            self._escalations.append(esc)
            self.audit.record(
                event_type  = AuditEventType.ESCALATION_TRIGGERED,
                actor       = Actor.SYSTEM,
                entity_id   = esc.id,
                entity_type = "escalation_event",
                details     = f"user={user_id} signal={signal_id} level={esc.escalation_level.value}",
            )

        return new_alerts, new_escalations

    # ── ACKNOWLEDGMENT ────────────────────────────────────────────────────────

    def acknowledge(self, user_id: str, alert_id: str) -> bool:
        """
        Record user acknowledgment of an alert.
        Acknowledgment is logged with timestamp — required for Level 2 and 3.
        URGENT alerts require acknowledgment before normal UI is restored.
        """
        for alert in self._alerts:
            if alert.id == alert_id:
                alert.acknowledged    = True
                alert.acknowledged_at = datetime.utcnow()
                self.audit.record(
                    event_type  = AuditEventType.ALERT_ISSUED,
                    actor       = Actor.USER,
                    entity_id   = alert_id,
                    entity_type = "alert",
                    reason_code = "user_acknowledged",
                    details     = f"acknowledged_at={alert.acknowledged_at.isoformat()}",
                )
                return True
        return False

    def has_unacknowledged_urgent(self, user_id: str) -> bool:
        """
        Returns True if the user has any unacknowledged URGENT alerts.
        UI layer must check this and restrict navigation until resolved.
        """
        return any(
            a.severity == AlertSeverity.URGENT
            and not a.acknowledged
            for a in self._alerts
        )

    # ── QUERIES ───────────────────────────────────────────────────────────────

    def get_alerts(self, user_id: str, include_acknowledged: bool = True) -> List[Alert]:
        alerts = [a for a in self._alerts]
        if not include_acknowledged:
            alerts = [a for a in alerts if not a.acknowledged]
        return sorted(alerts, key=lambda a: a.created_at, reverse=True)

    def get_escalations(self, user_id: str) -> List[EscalationEvent]:
        return [e for e in self._escalations]

    # ── INTERNAL RULE CHECKS ──────────────────────────────────────────────────

    def _check_single_reading(
        self,
        user_id:    str,
        signal_id:  str,
        measurements: List[Measurement],
    ) -> Tuple[Optional[Alert], Optional[EscalationEvent]]:
        """
        Check the most recent reading against single-value safety thresholds.
        A single dangerous reading triggers immediately.
        """
        latest = measurements[-1]

        for threshold_key, threshold in SAFETY_THRESHOLDS.items():
            if threshold.signal_id != signal_id:
                continue

            # Level 3 — URGENT (single reading in danger zone)
            if threshold.level_3_value is not None:
                if ("_high" in threshold_key and latest.value >= threshold.level_3_value) or \
                   ("_low"  in threshold_key and latest.value <= threshold.level_3_value):
                    return self._build_level_3(user_id, signal_id, latest, threshold_key)

            # Level 2 — PROMPT ACTION (single reading in concern zone)
            if threshold.level_2_value is not None:
                if ("_high" in threshold_key and latest.value >= threshold.level_2_value) or \
                   ("_low"  in threshold_key and latest.value <= threshold.level_2_value):
                    return self._build_level_2_single(user_id, signal_id, latest, threshold_key)

        return None, None

    def _check_sustained_pattern(
        self,
        user_id:      str,
        signal_id:    str,
        measurements: List[Measurement],
        findings:     List[Finding],
    ) -> Tuple[Optional[Alert], Optional[EscalationEvent]]:
        """
        Check for sustained patterns that cross Level 2 thresholds.
        Requires multiple readings over multiple days.
        """
        from solvra_kernel.models.entities import FindingType
        drift_findings = [f for f in findings if f.finding_type == FindingType.SUSTAINED_DRIFT]

        if not drift_findings:
            return None, None

        for threshold_key, threshold in SAFETY_THRESHOLDS.items():
            if threshold.signal_id != signal_id:
                continue
            if threshold.level_2_value is None:
                continue

            # Check if recent readings are mostly above the sustained concern threshold
            recent = measurements[-threshold.level_2_sustained_days:]
            concern_count = 0
            for m in recent:
                if ("_high" in threshold_key and m.value >= threshold.level_2_value) or \
                   ("_low"  in threshold_key and m.value <= threshold.level_2_value):
                    concern_count += 1

            if concern_count >= max(3, len(recent) * 0.6):
                return self._build_level_2_pattern(
                    user_id, signal_id, recent, threshold_key, concern_count
                )

        return None, None

    # ── ALERT BUILDERS ────────────────────────────────────────────────────────

    def _build_level_3(
        self, user_id, signal_id, measurement, threshold_key
    ) -> Tuple[Alert, EscalationEvent]:
        sig_name = SIGNAL_DEFINITIONS.get(signal_id, type('', (), {'name': signal_id})()).name if signal_id in SIGNAL_DEFINITIONS else signal_id

        alert = Alert(
            user_id          = user_id,
            severity         = AlertSeverity.URGENT,
            title            = f"Important: {sig_name} reading needs attention today",
            message          = (
                f"Your {sig_name} reading of {measurement.value:.1f} is in a range "
                f"that warrants same-day attention. "
                f"Please contact your doctor or seek medical evaluation today. "
                f"If you feel unwell, call emergency services."
            ),
            safe_next_step   = "Contact your doctor or seek medical evaluation today. Call 911 if you feel unwell.",
            uncertainty      = UncertaintyLevel.LOW,   # threshold-based, not statistical
            escalation_level = EscalationLevel.LEVEL_3_URGENT,
            suppressible     = False,   # enforced in Alert.__post_init__
        )

        escalation = EscalationEvent(
            user_id          = user_id,
            escalation_level = EscalationLevel.LEVEL_3_URGENT,
            recommendation   = alert.safe_next_step,
            evidence_summary = f"{sig_name}={measurement.value:.1f} at {measurement.timestamp.isoformat()} [threshold={threshold_key}]",
            finding_ids      = [],
            alert_id         = alert.id,
        )
        alert_with_esc = Alert(
            user_id          = alert.user_id,
            severity         = alert.severity,
            title            = alert.title,
            message          = alert.message,
            safe_next_step   = alert.safe_next_step,
            uncertainty      = alert.uncertainty,
            escalation_level = alert.escalation_level,
        )

        return alert, escalation

    def _build_level_2_single(
        self, user_id, signal_id, measurement, threshold_key
    ) -> Tuple[Alert, EscalationEvent]:
        sig_name = SIGNAL_DEFINITIONS[signal_id].name if signal_id in SIGNAL_DEFINITIONS else signal_id

        alert = Alert(
            user_id          = user_id,
            severity         = AlertSeverity.MONITOR,
            title            = f"Your {sig_name} reading is worth discussing with your doctor",
            message          = (
                f"Your {sig_name} reading of {measurement.value:.1f} is in a range "
                f"that Solvra considers worth bringing to your doctor's attention. "
                f"This is not a diagnosis, and a single reading does not tell the full story. "
                f"Monitoring this over the coming days and scheduling a conversation with your "
                f"healthcare provider is recommended."
            ),
            safe_next_step   = "Monitor over the next few days and schedule a conversation with your healthcare provider.",
            uncertainty      = UncertaintyLevel.MEDIUM,
            escalation_level = EscalationLevel.LEVEL_2_PROMPT_ACTION,
        )

        escalation = EscalationEvent(
            user_id          = user_id,
            escalation_level = EscalationLevel.LEVEL_2_PROMPT_ACTION,
            recommendation   = alert.safe_next_step,
            evidence_summary = f"{sig_name}={measurement.value:.1f} [threshold={threshold_key}]",
            alert_id         = alert.id,
        )

        return alert, escalation

    def _build_level_2_pattern(
        self, user_id, signal_id, recent_measurements, threshold_key, concern_count
    ) -> Tuple[Alert, EscalationEvent]:
        sig_name = SIGNAL_DEFINITIONS[signal_id].name if signal_id in SIGNAL_DEFINITIONS else signal_id
        span_days = (recent_measurements[-1].timestamp - recent_measurements[0].timestamp).days

        alert = Alert(
            user_id          = user_id,
            severity         = AlertSeverity.MONITOR,
            title            = f"A pattern in your {sig_name} readings is worth discussing with your doctor",
            message          = (
                f"Over the past {span_days} days, {concern_count} of your {len(recent_measurements)} "
                f"{sig_name} readings have been in a range that Solvra considers worth bringing "
                f"to a healthcare provider. This sustained pattern — not just a single reading — "
                f"is what prompted this notice. Solvra is not diagnosing anything. "
                f"Your doctor is the right person to evaluate what this means for you."
            ),
            safe_next_step   = "Schedule a timely conversation with your healthcare provider and share your Solvra export.",
            uncertainty      = UncertaintyLevel.MEDIUM,
            escalation_level = EscalationLevel.LEVEL_2_PROMPT_ACTION,
        )

        escalation = EscalationEvent(
            user_id          = user_id,
            escalation_level = EscalationLevel.LEVEL_2_PROMPT_ACTION,
            recommendation   = alert.safe_next_step,
            evidence_summary = f"Sustained pattern: {concern_count}/{len(recent_measurements)} readings [threshold={threshold_key}] over {span_days} days",
            finding_ids      = [],
            alert_id         = alert.id,
        )

        return alert, escalation
