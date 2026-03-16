"""
Solvra Kernel — Ingestion Service
===================================
Accepts user health inputs, validates schema and ranges,
applies quality scoring, tags provenance, and writes to state.
Spec Section 6.1 — Ingestion Service.
Spec Section 7.2 — Measurement Schema Requirements.
Spec Section 7.3 — Deletion & Audit Scar Rules (input quality layer addition).

Pillar 1 — Personal Ownership:
  Every measurement is tagged with user identity and provenance.
  Corrections are new measurements, never overwrites.

Pillar 3 — Trust Through Verifiable Integrity:
  Every write produces an immutable AuditEvent.
"""

from datetime import datetime, timezone
from typing import List, Optional, Dict, Tuple

from solvra_kernel.models.entities import (
    Measurement, QualityFlag, SourceType, AuditEventType, Actor,
    SIGNAL_DEFINITIONS
)
from solvra_kernel.engines.audit_engine import AuditEngine


class ValidationError(Exception):
    """Raised when a measurement fails validation."""
    pass


class IngestionService:

    def __init__(self, audit_engine: AuditEngine):
        self.audit = audit_engine
        self._store: Dict[str, Measurement] = {}      # id → Measurement
        self._user_measurements: Dict[str, List[str]] = {}  # user_id → [ids]

    # ── INGEST ────────────────────────────────────────────────────────────────

    def ingest(
        self,
        user_id:      str,
        signal_id:    str,
        value:        float,
        unit:         str,
        timestamp:    datetime,
        entry_method: str = "web_form",
        notes:        Optional[str] = None,
        approximate:  bool = False,
    ) -> Tuple[Measurement, List[str]]:
        """
        Validate and store a new measurement.
        Returns (measurement, warnings) where warnings are non-blocking notices.

        Warnings are shown to the user transparently.
        Validation errors are blocking — the measurement is rejected.
        """
        warnings = []

        # 1. Signal must be defined
        if signal_id not in SIGNAL_DEFINITIONS:
            raise ValidationError(f"Unknown signal: {signal_id}")

        sig = SIGNAL_DEFINITIONS[signal_id]

        # 2. Range validation
        if not (sig.valid_min <= value <= sig.valid_max):
            raise ValidationError(
                f"Value {value} {unit} is outside the valid range "
                f"({sig.valid_min}–{sig.valid_max} {sig.unit}) for {sig.name}. "
                f"Please check your entry."
            )

        # 3. Unit normalization (basic — extend per signal as needed)
        normalized_value, unit = self._normalize_unit(signal_id, value, unit)

        # 4. Build quality flags
        quality_flags = [QualityFlag.SELF_REPORTED]

        if approximate:
            quality_flags.append(QualityFlag.APPROXIMATE)
            warnings.append(
                "This entry is marked as approximate. "
                "Solvra will reflect this uncertainty in any insights derived from it."
            )

        # 5. Temporal consistency check — is this being entered retrospectively?
        entry_lag_hours = (datetime.utcnow() - timestamp.replace(tzinfo=None)).total_seconds() / 3600
        if entry_lag_hours > 48:
            quality_flags.append(QualityFlag.BATCH_ENTERED)
            warnings.append(
                f"This reading was entered {int(entry_lag_hours / 24)} days after it was taken. "
                "Retrospective entries carry slightly more uncertainty than real-time entries. "
                "Solvra will account for this."
            )

        # 6. Internal consistency check (signal-specific)
        consistency_warning = self._check_consistency(user_id, signal_id, normalized_value)
        if consistency_warning:
            quality_flags.append(QualityFlag.OUTLIER_SUSPECTED)
            warnings.append(consistency_warning)

        # 7. Build and store the measurement
        measurement = Measurement(
            user_id       = user_id,
            signal_id     = signal_id,
            value         = normalized_value,
            unit          = sig.unit,
            timestamp     = timestamp,
            source_type   = SourceType.MANUAL_ENTRY,
            entry_method  = entry_method,
            quality_flags = quality_flags,
            notes         = notes,
        )

        self._store[measurement.id] = measurement
        self._user_measurements.setdefault(user_id, []).append(measurement.id)

        # 8. Audit event — every write is logged
        self.audit.record(
            event_type  = AuditEventType.CREATE_MEASUREMENT,
            actor       = Actor.USER,
            entity_id   = measurement.id,
            entity_type = "measurement",
            details     = f"user={user_id} signal={signal_id} value={normalized_value} flags={[f.value for f in quality_flags]}",
        )

        return measurement, warnings

    # ── CORRECTION (not overwrite) ────────────────────────────────────────────

    def correct(
        self,
        user_id:               str,
        original_measurement_id: str,
        corrected_value:       float,
        reason:                str,
    ) -> Tuple[Measurement, List[str]]:
        """
        Submit a correction to a prior measurement.
        The original is NOT modified — a new measurement supersedes it.
        Spec Section 7.2 — immutability rule.
        """
        original = self._store.get(original_measurement_id)
        if not original or original.user_id != user_id:
            raise ValidationError("Measurement not found or access denied.")

        corrected, warnings = self.ingest(
            user_id      = user_id,
            signal_id    = original.signal_id,
            value        = corrected_value,
            unit         = original.unit,
            timestamp    = original.timestamp,
            entry_method = "correction",
            notes        = f"Correction of {original_measurement_id}. Reason: {reason}",
        )
        corrected.supersedes_id = original_measurement_id

        self.audit.record(
            event_type  = AuditEventType.SUPERSEDE_MEASUREMENT,
            actor       = Actor.USER,
            entity_id   = corrected.id,
            entity_type = "measurement",
            reason_code = "user_correction",
            details     = f"supersedes={original_measurement_id} reason={reason}",
        )

        return corrected, warnings

    # ── LOGICAL DELETE ────────────────────────────────────────────────────────

    def request_delete(self, user_id: str, measurement_id: str, reason: str) -> bool:
        """
        Logical deletion — hides from UI but retains audit scar.
        Safety-critical escalation events referencing this measurement are preserved.
        Spec Section 7.3 — Deletion & Audit Scar Rules.
        """
        measurement = self._store.get(measurement_id)
        if not measurement or measurement.user_id != user_id:
            return False

        measurement.is_deleted = True

        # Audit scar — the record that a measurement existed and was deleted
        self.audit.record(
            event_type  = AuditEventType.DELETE_REQUEST,
            actor       = Actor.USER,
            entity_id   = measurement_id,
            entity_type = "measurement",
            reason_code = "user_delete_request",
            details     = f"user={user_id} signal={measurement.signal_id} reason={reason}",
        )

        return True

    # ── QUERIES ───────────────────────────────────────────────────────────────

    def get_measurements(
        self,
        user_id:      str,
        signal_id:    Optional[str] = None,
        since:        Optional[datetime] = None,
        include_deleted: bool = False,
    ) -> List[Measurement]:
        ids = self._user_measurements.get(user_id, [])
        results = [self._store[i] for i in ids if i in self._store]

        if not include_deleted:
            results = [m for m in results if not m.is_deleted]
        if signal_id:
            results = [m for m in results if m.signal_id == signal_id]
        if since:
            results = [m for m in results if m.timestamp >= since]

        return sorted(results, key=lambda m: m.timestamp)

    # ── INTERNAL HELPERS ──────────────────────────────────────────────────────

    def _normalize_unit(self, signal_id: str, value: float, unit: str) -> Tuple[float, str]:
        """Convert common unit variants to canonical units."""
        sig = SIGNAL_DEFINITIONS[signal_id]

        # Weight: lbs → kg
        if signal_id == "weight" and unit.lower() in ("lb", "lbs", "pounds"):
            return round(value * 0.453592, 2), "kg"

        # Waist: inches → cm
        if signal_id == "waist_circ" and unit.lower() in ("in", "inches", "inch"):
            return round(value * 2.54, 2), "cm"

        # Height: inches → cm (for BMI)
        if signal_id == "height" and unit.lower() in ("in", "inches"):
            return round(value * 2.54, 2), "cm"

        return value, sig.unit

    def _check_consistency(
        self, user_id: str, signal_id: str, value: float
    ) -> Optional[str]:
        """
        Basic plausibility check against recent measurements.
        Returns a warning string if the value is suspicious, else None.
        """
        recent = self.get_measurements(user_id, signal_id=signal_id)
        if len(recent) < 3:
            return None   # not enough history to flag

        recent_values = [m.value for m in recent[-10:]]
        median = sorted(recent_values)[len(recent_values) // 2]

        # Flag if more than 50% deviation from recent median
        if median > 0 and abs(value - median) / median > 0.50:
            return (
                f"This {SIGNAL_DEFINITIONS[signal_id].name} reading of {value} "
                f"is quite different from your recent readings (around {median:.1f}). "
                "Please double-check your entry. If it is correct, Solvra will take it "
                "into account with appropriate uncertainty."
            )

        return None
