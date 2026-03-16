"""
Solvra Kernel — Trend & Change Detection Engine
=================================================
Detects meaningful changes in user health signals over time.
Produces Findings that feed into Risk Flagging and Safety Escalation.
Spec Section 19 — Change Detection.

Finding types (Spec Section 19.1):
  A) Spike — single reading beyond expected range
  B) Sustained Drift — shift in short vs long baseline
  C) Volatility Change — dispersion increase
  D) Coverage Risk — insufficient recent readings

All findings carry: evidence window, confidence, uncertainty.
Findings are non-diagnostic — they describe patterns, not conditions.
"""

from datetime import datetime, timedelta
from typing import List, Optional, Dict

from solvra_kernel.models.entities import (
    Measurement, DerivedFeature, Finding, FindingType, UncertaintyLevel, AuditEventType, Actor
)
from solvra_kernel.config.thresholds import (
    SPIKE_THRESHOLD_MAD_MULTIPLIER,
    DRIFT_THRESHOLD_PERCENT,
    DRIFT_MIN_DAYS,
    VOLATILITY_INCREASE_THRESHOLD,
    COVERAGE_RISK_MAX_GAP_DAYS,
)
from solvra_kernel.engines.audit_engine import AuditEngine
from solvra_kernel.engines.baseline_engine import median, mad


class ChangeDetector:

    def __init__(self, audit_engine: AuditEngine):
        self.audit = audit_engine

    def detect_all(
        self,
        user_id:        str,
        signal_id:      str,
        measurements:   List[Measurement],
        short_baseline: Optional[DerivedFeature],
        long_baseline:  Optional[DerivedFeature],
    ) -> List[Finding]:
        """
        Run all change detection algorithms for a signal.
        Returns list of Findings (may be empty).
        """
        findings = []
        valid = [m for m in measurements if not m.is_deleted]

        if not valid:
            return findings

        # A) Spike detection
        spike = self._detect_spike(user_id, signal_id, valid, short_baseline)
        if spike:
            findings.append(spike)

        # B) Sustained drift
        drift = self._detect_sustained_drift(
            user_id, signal_id, valid, short_baseline, long_baseline
        )
        if drift:
            findings.append(drift)

        # C) Volatility change
        volatility = self._detect_volatility_change(
            user_id, signal_id, valid, short_baseline
        )
        if volatility:
            findings.append(volatility)

        # D) Coverage risk
        coverage = self._detect_coverage_risk(user_id, signal_id, valid)
        if coverage:
            findings.append(coverage)

        # Audit each finding
        for f in findings:
            self.audit.record(
                event_type  = AuditEventType.FINDING_CREATED,
                actor       = Actor.SYSTEM,
                entity_id   = f.id,
                entity_type = "finding",
                details     = f"user={user_id} signal={signal_id} type={f.finding_type.value} confidence={f.confidence:.2f}",
            )

        return findings

    # ── A) SPIKE DETECTION ────────────────────────────────────────────────────

    def _detect_spike(
        self,
        user_id:    str,
        signal_id:  str,
        measurements: List[Measurement],
        baseline:   Optional[DerivedFeature],
    ) -> Optional[Finding]:
        """
        Detect a single reading that is unusually far from the baseline.
        Spec Section 19.1 — Spike finding type.
        """
        if not measurements or baseline is None:
            return None

        latest = measurements[-1]

        # Compute MAD from recent readings
        recent_values = [m.value for m in measurements[-20:]]
        dispersion    = mad(recent_values, baseline.value)

        if dispersion == 0:
            return None

        z_score = abs(latest.value - baseline.value) / dispersion

        if z_score > SPIKE_THRESHOLD_MAD_MULTIPLIER:
            direction = "above" if latest.value > baseline.value else "below"
            confidence = min(0.90, 0.50 + (z_score - SPIKE_THRESHOLD_MAD_MULTIPLIER) * 0.10)

            return Finding(
                user_id               = user_id,
                signal_id             = signal_id,
                finding_type          = FindingType.SPIKE,
                description           = (
                    f"Your most recent reading ({latest.value:.1f}) is notably {direction} "
                    f"your personal baseline ({baseline.value:.1f}). "
                    f"This may reflect a real change, a measurement condition, or normal variation. "
                    f"A follow-up reading is recommended to confirm."
                ),
                evidence_window_start = latest.timestamp,
                evidence_window_end   = latest.timestamp,
                confidence            = round(confidence, 2),
                uncertainty           = baseline.uncertainty,
                supporting_measurement_ids = [latest.id],
                baseline_ref_id       = baseline.id,
            )

        return None

    # ── B) SUSTAINED DRIFT ────────────────────────────────────────────────────

    def _detect_sustained_drift(
        self,
        user_id:        str,
        signal_id:      str,
        measurements:   List[Measurement],
        short_baseline: Optional[DerivedFeature],
        long_baseline:  Optional[DerivedFeature],
    ) -> Optional[Finding]:
        """
        Detect a sustained shift in the short-window baseline vs long-window.
        Requires both baselines and sufficient time span.
        Spec Section 19.1 — Sustained Drift finding type.
        """
        if short_baseline is None or long_baseline is None:
            return None
        if long_baseline.value == 0:
            return None

        percent_change = (short_baseline.value - long_baseline.value) / long_baseline.value

        if abs(percent_change) < DRIFT_THRESHOLD_PERCENT:
            return None

        # Verify the drift has persisted for the minimum number of days
        recent_measurements = [
            m for m in measurements
            if m.timestamp >= short_baseline.window_start
        ]
        if len(recent_measurements) < 3:
            return None

        span_days = (
            recent_measurements[-1].timestamp - recent_measurements[0].timestamp
        ).days

        if span_days < DRIFT_MIN_DAYS:
            return None

        direction = "upward" if percent_change > 0 else "downward"
        pct_str   = f"{abs(percent_change)*100:.1f}%"
        confidence = min(0.85, 0.55 + abs(percent_change) * 0.5)

        # More conservative uncertainty when drift is detected
        uncertainty = UncertaintyLevel.MEDIUM
        if short_baseline.uncertainty == UncertaintyLevel.HIGH:
            uncertainty = UncertaintyLevel.HIGH

        return Finding(
            user_id               = user_id,
            signal_id             = signal_id,
            finding_type          = FindingType.SUSTAINED_DRIFT,
            description           = (
                f"Your recent {signal_id.replace('_', ' ')} readings have trended {direction} "
                f"by approximately {pct_str} compared to your longer-term pattern. "
                f"This trend has been present for {span_days} days. "
                f"Whether this represents a meaningful change worth discussing with your doctor "
                f"depends on context that Solvra does not yet have."
            ),
            evidence_window_start = recent_measurements[0].timestamp,
            evidence_window_end   = recent_measurements[-1].timestamp,
            confidence            = round(confidence, 2),
            uncertainty           = uncertainty,
            supporting_measurement_ids = [m.id for m in recent_measurements],
            baseline_ref_id       = long_baseline.id,
        )

    # ── C) VOLATILITY CHANGE ─────────────────────────────────────────────────

    def _detect_volatility_change(
        self,
        user_id:    str,
        signal_id:  str,
        measurements: List[Measurement],
        baseline:   Optional[DerivedFeature],
    ) -> Optional[Finding]:
        """
        Detect a significant increase in measurement variability.
        Increased volatility often indicates lifestyle instability
        or measurement inconsistency — interpreted cautiously.
        Spec Section 19.1 — Volatility Change finding type.
        """
        if len(measurements) < 10 or baseline is None:
            return None

        # Compare MAD of recent half vs earlier half
        mid = len(measurements) // 2
        early_values  = [m.value for m in measurements[:mid]]
        recent_values = [m.value for m in measurements[mid:]]

        early_mad  = mad(early_values)
        recent_mad = mad(recent_values)

        if early_mad == 0:
            return None

        ratio = recent_mad / early_mad

        if ratio < VOLATILITY_INCREASE_THRESHOLD:
            return None

        return Finding(
            user_id               = user_id,
            signal_id             = signal_id,
            finding_type          = FindingType.VOLATILITY_SHIFT,
            description           = (
                f"Your {signal_id.replace('_', ' ')} readings have become more variable recently. "
                f"This pattern can reflect lifestyle changes, measurement timing variation, "
                f"or other factors. Solvra is flagging this for your awareness, "
                f"not as a clinical concern. More consistent measurement conditions "
                f"would help clarify the picture."
            ),
            evidence_window_start = measurements[mid].timestamp,
            evidence_window_end   = measurements[-1].timestamp,
            confidence            = min(0.75, 0.40 + ratio * 0.10),
            uncertainty           = UncertaintyLevel.HIGH,   # volatility = high uncertainty
            supporting_measurement_ids = [m.id for m in measurements[mid:]],
            baseline_ref_id       = baseline.id,
        )

    # ── D) COVERAGE RISK ──────────────────────────────────────────────────────

    def _detect_coverage_risk(
        self,
        user_id:      str,
        signal_id:    str,
        measurements: List[Measurement],
    ) -> Optional[Finding]:
        """
        Flag when there has been an extended gap in readings.
        Spec Section 19.1 — Coverage Risk finding type.
        System must state uncertainty and avoid confident projections.
        """
        if not measurements:
            return None

        last_reading = measurements[-1].timestamp
        days_since   = (datetime.utcnow() - last_reading).days

        if days_since < COVERAGE_RISK_MAX_GAP_DAYS:
            return None

        return Finding(
            user_id               = user_id,
            signal_id             = signal_id,
            finding_type          = FindingType.COVERAGE_RISK,
            description           = (
                f"Solvra has not received a {signal_id.replace('_', ' ')} reading "
                f"for {days_since} days. Without recent data, Solvra cannot give you "
                f"a meaningful current picture for this signal. "
                f"Any previous insights for this signal should be treated as less current."
            ),
            evidence_window_start = last_reading,
            evidence_window_end   = datetime.utcnow(),
            confidence            = 1.0,     # coverage gap is a fact, not a probability
            uncertainty           = UncertaintyLevel.HIGH,
            supporting_measurement_ids = [measurements[-1].id],
        )
