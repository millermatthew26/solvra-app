"""
Solvra Kernel — Baseline Engine
=================================
Computes and versions personal baselines per user per signal.
Spec Section 18 — Baseline Engine.

Uses robust statistical methods (median, MAD) that are resistant
to outliers and sparse data — appropriate for self-reported health data.

Pillar 3 — Every baseline carries full provenance:
  window used, count, method, quality weighting applied.
"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import statistics

from shilu_kernel.models.entities import (
    Measurement, DerivedFeature, UncertaintyLevel, AuditEventType, Actor
)
from shilu_kernel.config.thresholds import (
    BASELINE_MIN_MEASUREMENTS, BASELINE_MIN_DAYS,
    BASELINE_SHORT_WINDOW_DAYS, BASELINE_LONG_WINDOW_DAYS,
    CALIBRATION_THRESHOLDS, MVL_THRESHOLDS
)
from shilu_kernel.engines.audit_engine import AuditEngine


def median(values: List[float]) -> float:
    sorted_vals = sorted(values)
    n = len(sorted_vals)
    mid = n // 2
    return sorted_vals[mid] if n % 2 else (sorted_vals[mid-1] + sorted_vals[mid]) / 2


def mad(values: List[float], center: Optional[float] = None) -> float:
    """Median Absolute Deviation — robust dispersion measure."""
    if len(values) < 2:
        return 0.0
    c = center if center is not None else median(values)
    deviations = [abs(v - c) for v in values]
    return median(deviations)


class BaselineEngine:

    def __init__(self, audit_engine: AuditEngine):
        self.audit = audit_engine
        # user_id → signal_id → list of DerivedFeature (versioned baselines)
        self._baselines: Dict[str, Dict[str, List[DerivedFeature]]] = {}

    # ── PUBLIC API ────────────────────────────────────────────────────────────

    def compute_baselines(
        self,
        user_id:      str,
        signal_id:    str,
        measurements: List[Measurement],
    ) -> Dict[str, Optional[DerivedFeature]]:
        """
        Compute short-window and long-window baselines for a signal.
        Returns dict with keys: 'short', 'long', 'uncertainty'.

        Returns None for a window if insufficient data exists.
        Never produces a baseline silently — always declares uncertainty.
        """
        now = datetime.utcnow()

        short_window = timedelta(days=BASELINE_SHORT_WINDOW_DAYS)
        long_window  = timedelta(days=BASELINE_LONG_WINDOW_DAYS)

        short_measurements = [
            m for m in measurements
            if m.timestamp >= now - short_window and not m.is_deleted
        ]
        long_measurements = [
            m for m in measurements
            if m.timestamp >= now - long_window and not m.is_deleted
        ]

        short_baseline = self._compute_single_baseline(
            user_id, signal_id, short_measurements,
            window_days=BASELINE_SHORT_WINDOW_DAYS, label="short"
        )
        long_baseline = self._compute_single_baseline(
            user_id, signal_id, long_measurements,
            window_days=BASELINE_LONG_WINDOW_DAYS, label="long"
        )

        # Store versioned baselines
        user_baselines = self._baselines.setdefault(user_id, {})
        signal_baselines = user_baselines.setdefault(signal_id, [])

        if short_baseline:
            signal_baselines.append(short_baseline)
            self.audit.record(
                event_type  = AuditEventType.BASELINE_UPDATE,
                actor       = Actor.SYSTEM,
                entity_id   = short_baseline.id,
                entity_type = "derived_feature",
                details     = f"user={user_id} signal={signal_id} window=short value={short_baseline.value:.2f}",
            )

        if long_baseline:
            signal_baselines.append(long_baseline)
            self.audit.record(
                event_type  = AuditEventType.BASELINE_UPDATE,
                actor       = Actor.SYSTEM,
                entity_id   = long_baseline.id,
                entity_type = "derived_feature",
                details     = f"user={user_id} signal={signal_id} window=long value={long_baseline.value:.2f}",
            )

        overall_uncertainty = self._determine_uncertainty(
            user_id, signal_id, measurements, short_baseline, long_baseline
        )

        return {
            "short":       short_baseline,
            "long":        long_baseline,
            "uncertainty": overall_uncertainty,
        }

    def get_latest_baseline(
        self, user_id: str, signal_id: str, window: str = "short"
    ) -> Optional[DerivedFeature]:
        """Return the most recent baseline for a given window."""
        baselines = self._baselines.get(user_id, {}).get(signal_id, [])
        matching = [b for b in baselines if window in b.feature_type]
        return matching[-1] if matching else None

    def mvl_status(
        self, user_id: str, signal_id: str, measurements: List[Measurement]
    ) -> Dict:
        """
        Report MVL threshold progress for a signal.
        Used for transparent progress disclosure to users.
        Spec Section 12 — MVL Thresholds.
        """
        if signal_id not in MVL_THRESHOLDS:
            return {"applicable": False}

        threshold = MVL_THRESHOLDS[signal_id]
        valid = [m for m in measurements if not m.is_deleted]

        if not valid:
            return {
                "applicable":       True,
                "threshold_met":    False,
                "readings_needed":  threshold.min_readings,
                "readings_have":    0,
                "days_needed":      threshold.min_days,
                "days_have":        0,
                "description":      threshold.description,
            }

        readings_have = len(valid)
        span_days = (valid[-1].timestamp - valid[0].timestamp).days

        return {
            "applicable":       True,
            "threshold_met":    readings_have >= threshold.min_readings and span_days >= threshold.min_days,
            "readings_needed":  threshold.min_readings,
            "readings_have":    readings_have,
            "days_needed":      threshold.min_days,
            "days_have":        span_days,
            "description":      threshold.description,
        }

    # ── INTERNAL ─────────────────────────────────────────────────────────────

    def _compute_single_baseline(
        self,
        user_id:     str,
        signal_id:   str,
        measurements: List[Measurement],
        window_days: int,
        label:       str,
    ) -> Optional[DerivedFeature]:
        """
        Compute a single baseline from a set of measurements.
        Returns None if insufficient data — never silently fills with a guess.
        """
        valid = [m for m in measurements if not m.is_deleted]

        if len(valid) < BASELINE_MIN_MEASUREMENTS:
            return None

        span_days = (valid[-1].timestamp - valid[0].timestamp).days
        if span_days < BASELINE_MIN_DAYS:
            return None

        # Quality-weighted median using iterative approximation
        weights = [m.quality_weight() for m in valid]
        values  = [m.value for m in valid]
        weight_sum = sum(weights)

        # Weighted median approximation (sort by value, find weight midpoint)
        paired = sorted(zip(values, weights), key=lambda x: x[0])
        cumulative = 0.0
        half_weight = weight_sum / 2
        weighted_median = paired[-1][0]
        for val, w in paired:
            cumulative += w
            if cumulative >= half_weight:
                weighted_median = val
                break

        dispersion = mad(values, weighted_median)

        uncertainty = self._uncertainty_from_data(
            count=len(valid),
            span_days=span_days,
            dispersion=dispersion,
            baseline_value=weighted_median,
            signal_id=signal_id,
        )

        return DerivedFeature(
            user_id           = user_id,
            signal_id         = signal_id,
            feature_type      = f"baseline_{label}",
            value             = round(weighted_median, 3),
            window_start      = valid[0].timestamp,
            window_end        = valid[-1].timestamp,
            measurement_count = len(valid),
            method            = f"quality-weighted median, MAD={dispersion:.3f}, window={window_days}d",
            quality_weight_sum = weight_sum,
            uncertainty       = uncertainty,
        )

    def _uncertainty_from_data(
        self,
        count:           int,
        span_days:       int,
        dispersion:      float,
        baseline_value:  float,
        signal_id:       str,
    ) -> UncertaintyLevel:
        """
        Determine uncertainty tier based on data coverage and consistency.
        Spec Section 14 — Calibration Layer.
        Uses thresholds from config — all thresholds are clinician-defined.
        """
        if baseline_value == 0:
            return UncertaintyLevel.HIGH

        relative_dispersion = dispersion / baseline_value

        high_threshold, low_threshold = CALIBRATION_THRESHOLDS.get(
            signal_id, (0.20, 0.10)
        )

        # Also factor in data coverage
        if count < BASELINE_MIN_MEASUREMENTS or span_days < BASELINE_MIN_DAYS:
            return UncertaintyLevel.HIGH

        if relative_dispersion > high_threshold or count < 8:
            return UncertaintyLevel.HIGH
        elif relative_dispersion > low_threshold or count < 15:
            return UncertaintyLevel.MEDIUM
        else:
            return UncertaintyLevel.LOW

    def _determine_uncertainty(
        self,
        user_id:       str,
        signal_id:     str,
        measurements:  List[Measurement],
        short_baseline: Optional[DerivedFeature],
        long_baseline:  Optional[DerivedFeature],
    ) -> UncertaintyLevel:
        """
        Overall uncertainty considering both baselines and coverage.
        Returns the more conservative (higher) uncertainty of the two.
        Under uncertainty, be more conservative — Pillar 2.
        """
        if short_baseline is None:
            return UncertaintyLevel.HIGH

        # Most conservative of the two
        levels = [b.uncertainty for b in [short_baseline, long_baseline] if b is not None]
        order  = [UncertaintyLevel.HIGH, UncertaintyLevel.MEDIUM, UncertaintyLevel.LOW]
        return min(levels, key=lambda l: order.index(l))


# ─── POPULATION CONTEXT ASSESSMENT ───────────────────────────────────────────

class PopulationContextEngine:
    """
    Compares established personal baselines against population reference ranges.
    Produces BaselineContextNotes — one per signal, once, calmly.

    This engine addresses the 'unhealthy baseline' problem:
      A user whose personal normal is outside population norms needs to know
      this — once, with calm honest language — not repeatedly alarmed.

    THREE-SITUATION DESIGN (alert fatigue prevention):
      1. ACUTE DEVIATION     → handled by SafetyEngine (escalation)
      2. CHRONIC ELEVATION   → handled HERE (one-time BaselineContextNote)
      3. BORDERLINE POSITION → handled HERE (honest uncertainty language)

    The SafetyEngine and PopulationContextEngine serve different purposes.
    They must never be conflated.
    """

    def __init__(self, audit_engine):
        self.audit = audit_engine
        # user_id → signal_id → BaselineContextNote (one per signal)
        self._notes: Dict[str, Dict[str, "BaselineContextNote"]] = {}

    def assess_baseline_context(
        self,
        user_id:        str,
        signal_id:      str,
        personal_baseline: "DerivedFeature",
        user_age_range: Optional[str] = "all",
        user_sex:       Optional[str] = "all",
    ) -> Optional["BaselineContextNote"]:
        """
        Compare a personal baseline to population reference ranges.
        Returns a BaselineContextNote if warranted, else None.

        Rules:
          - Only runs when baseline uncertainty is MEDIUM or LOW (sufficient data)
          - Returns None if a non-dormant note already exists for this signal
          - Returns None if no population reference exists for this signal
          - Generates note ONCE — acknowledgment makes it dormant
        """
        from shilu_kernel.models.entities import (
            BaselineContextNote, BaselineContextStatus, UncertaintyLevel, AuditEventType, Actor
        )
        from shilu_kernel.config.thresholds import POPULATION_REFERENCES

        # Don't run if baseline is still high uncertainty
        if personal_baseline.uncertainty == UncertaintyLevel.HIGH:
            return None

        # Check for existing active note
        existing = self._notes.get(user_id, {}).get(signal_id)
        if existing and not existing.dormant:
            return None   # already surfaced, waiting for acknowledgment

        # Check for dormant note — only re-activate if baseline shifted materially
        if existing and existing.dormant:
            from shilu_kernel.config.thresholds import POPULATION_CONTEXT_REACTIVATION_SHIFT
            shift = abs(personal_baseline.value - existing.personal_baseline) / max(existing.personal_baseline, 0.001)
            if shift < POPULATION_CONTEXT_REACTIVATION_SHIFT:
                return None   # baseline hasn't shifted enough to re-surface

        # Find population reference
        refs = POPULATION_REFERENCES.get(signal_id, [])
        if not refs:
            return None

        # Select best matching reference (age/sex match, fall back to "all")
        ref = self._select_reference(refs, user_age_range, user_sex)
        if not ref:
            return None

        # Determine status
        status = self._determine_status(personal_baseline.value, ref)

        # Only generate a note if outside normal range or borderline
        if status == BaselineContextStatus.WITHIN_RANGE:
            return None

        # Build calm, non-diagnostic message
        message = self._build_context_message(
            signal_id, personal_baseline.value, ref, status
        )

        from shilu_kernel.models.entities import SIGNAL_DEFINITIONS
        sig = SIGNAL_DEFINITIONS.get(signal_id)
        sig_name = sig.name if sig else signal_id.replace("_", " ").title()

        note = BaselineContextNote(
            user_id                  = user_id,
            signal_id                = signal_id,
            signal_name              = sig_name,
            personal_baseline        = personal_baseline.value,
            personal_baseline_unit   = personal_baseline.feature_type,
            population_normal_low    = ref.normal_low,
            population_normal_high   = ref.normal_high,
            status                   = status,
            context_message          = message,
            guideline_source         = ref.guideline_source,
            debate_note              = ref.debate_note,
        )

        # Store and audit
        user_notes = self._notes.setdefault(user_id, {})
        user_notes[signal_id] = note
        self.audit.record(
            event_type  = AuditEventType.FINDING_CREATED,
            actor       = Actor.SYSTEM,
            entity_id   = note.id,
            entity_type = "baseline_context_note",
            details     = f"user={user_id} signal={signal_id} status={status.value} baseline={personal_baseline.value:.1f}",
        )

        return note

    def acknowledge_note(self, user_id: str, signal_id: str) -> bool:
        """Mark a BaselineContextNote as acknowledged and dormant."""
        from datetime import datetime
        note = self._notes.get(user_id, {}).get(signal_id)
        if note:
            note.acknowledged    = True
            note.acknowledged_at = datetime.utcnow()
            note.dormant         = True
            return True
        return False

    def get_active_notes(self, user_id: str) -> List["BaselineContextNote"]:
        """Return all non-dormant BaselineContextNotes for a user."""
        return [
            note for note in self._notes.get(user_id, {}).values()
            if not note.dormant
        ]

    # ── INTERNAL ─────────────────────────────────────────────────────────────

    def _select_reference(self, refs, age_range, sex):
        """Select best matching population reference."""
        # Try exact match first
        for r in refs:
            if r.age_range == age_range and r.sex == sex:
                return r
        # Fall back to "all"
        for r in refs:
            if r.age_range == "all" and r.sex == "all":
                return r
        return refs[0] if refs else None

    def _determine_status(self, value: float, ref) -> "BaselineContextStatus":
        from shilu_kernel.models.entities import BaselineContextStatus
        # Check if within normal range
        if ref.normal_low <= value <= ref.normal_high:
            return BaselineContextStatus.WITHIN_RANGE
        # Check borderline (within 5% of boundary)
        margin = (ref.normal_high - ref.normal_low) * 0.05
        if (ref.normal_low - margin) <= value <= (ref.normal_high + margin):
            return BaselineContextStatus.BORDERLINE
        # Outside range
        if ref.concern_high and value > ref.concern_high:
            return BaselineContextStatus.OUTSIDE_RANGE
        if ref.concern_low and value < ref.concern_low:
            return BaselineContextStatus.OUTSIDE_RANGE
        return BaselineContextStatus.BORDERLINE

    def _build_context_message(self, signal_id, value, ref, status) -> str:
        """Build calm, honest, non-diagnostic context message."""
        from shilu_kernel.models.entities import BaselineContextStatus, SIGNAL_DEFINITIONS
        sig = SIGNAL_DEFINITIONS.get(signal_id)
        sig_name = sig.name if sig else signal_id.replace("_", " ").title()

        if status == BaselineContextStatus.OUTSIDE_RANGE:
            direction = "above" if value > ref.normal_high else "below"
            return (
                f"Your personal {sig_name} baseline of {value:.1f} {ref.unit} has been "
                f"consistent in your data. For context, population guidelines suggest "
                f"{ref.normal_low:.0f}–{ref.normal_high:.0f} {ref.unit} as a typical range. "
                f"Your baseline sits {direction} that range. "
                f"This is not a new development — it appears to be your established pattern. "
                f"Solvra is not making a clinical determination. This context is worth mentioning to your "
                f"doctor at your next visit. "
                f"{('Note: ' + ref.debate_note) if ref.debate_note else ''}"
            )
        elif status == BaselineContextStatus.BORDERLINE:
            return (
                f"Your personal {sig_name} baseline of {value:.1f} {ref.unit} sits near the "
                f"boundary of what population guidelines consider a typical range "
                f"({ref.normal_low:.0f}–{ref.normal_high:.0f} {ref.unit}). "
                f"This is a borderline position — not clearly concerning, but worth awareness. "
                f"Solvra is not making a clinical determination. "
                f"{('Note: ' + ref.debate_note) if ref.debate_note else ''}"
            )
        return ""
