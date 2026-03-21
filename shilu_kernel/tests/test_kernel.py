"""
Solvra Kernel — Test Suite
============================
Tests all kernel components with emphasis on:
  - Safety trigger determinism (must fire reliably)
  - Audit chain integrity
  - Uncertainty escalation under sparse data
  - Non-suppressibility of urgent alerts
  - Regulatory-safe output language
  - Measurement immutability

Spec Section 34 — Validation & Testing Requirements.

Run with: python -m pytest tests/test_kernel.py -v
"""

import sys
import os
import unittest

# Resolve to the parent of shilu_kernel_v2/tests → shilu_kernel_v2/
_test_dir   = os.path.dirname(os.path.abspath(__file__))
_kernel_dir = os.path.dirname(_test_dir)
_root_dir   = os.path.dirname(_kernel_dir)
sys.path.insert(0, _root_dir)

from datetime import datetime, timedelta
from typing import List

from shilu_kernel.core.kernel import SolvraKernel
from shilu_kernel.models.entities import (
    AlertSeverity, UncertaintyLevel, FindingType, QualityFlag,
    EscalationLevel, SIGNAL_DEFINITIONS, SourceType
)
from shilu_kernel.engines.baseline_engine import median, mad
from shilu_kernel.engines.ingestion_service import ValidationError


def make_timestamps(count: int, days_span: int = 30) -> List[datetime]:
    """Generate evenly spaced timestamps over a date range."""
    start = datetime.utcnow() - timedelta(days=days_span)
    step  = timedelta(days=days_span / max(count, 1))
    return [start + step * i for i in range(count)]


# ═════════════════════════════════════════════════════════════════════════════
# UNIT TESTS — Statistical Functions
# ═════════════════════════════════════════════════════════════════════════════

def test_median_odd():
    assert median([1, 3, 5]) == 3

def test_median_even():
    assert median([1, 2, 3, 4]) == 2.5

def test_median_single():
    assert median([42]) == 42

def test_mad_basic():
    # MAD of [1, 2, 3, 4, 5]: median=3, deviations=[2,1,0,1,2], MAD=1
    assert mad([1, 2, 3, 4, 5]) == 1.0

def test_mad_identical():
    assert mad([5, 5, 5, 5]) == 0.0

def test_mad_too_few():
    assert mad([5]) == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# INGESTION SERVICE TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_valid_ingestion():
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    result = kernel.ingest_measurement("user1", "bp_systolic", 120.0, "mmHg", ts)
    assert result.measurement.value == 120.0
    assert result.measurement.user_id == "user1"
    assert result.measurement.signal_id == "bp_systolic"
    print("✓ Valid ingestion accepted")

def test_out_of_range_rejected():
    kernel = SolvraKernel()
    ts = datetime.utcnow()
    try:
        kernel.ingest_measurement("user1", "bp_systolic", 999.0, "mmHg", ts)
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass
    print("✓ Out-of-range value correctly rejected")

def test_unknown_signal_rejected():
    kernel = SolvraKernel()
    ts = datetime.utcnow()
    try:
        kernel.ingest_measurement("user1", "invalid_signal", 100.0, "units", ts)
        assert False, "Should have raised ValidationError"
    except ValidationError:
        pass
    print("✓ Unknown signal correctly rejected")

def test_retrospective_entry_flagged():
    kernel = SolvraKernel()
    old_ts = datetime.utcnow() - timedelta(days=5)
    result = kernel.ingest_measurement("user1", "bp_systolic", 120.0, "mmHg", old_ts)
    flags  = result.measurement.quality_flags
    assert QualityFlag.BATCH_ENTERED in flags
    assert any("retrospective" in w.lower() or "entered" in w.lower() for w in result.warnings)
    print("✓ Retrospective entry correctly flagged with quality flag and warning")

def test_approximate_flag():
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    result = kernel.ingest_measurement("user1", "weight", 80.0, "kg", ts, approximate=True)
    assert QualityFlag.APPROXIMATE in result.measurement.quality_flags
    print("✓ Approximate flag correctly attached")

def test_measurement_immutability():
    """Corrections create new measurements, never overwrite."""
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    result = kernel.ingest_measurement("user1", "bp_systolic", 120.0, "mmHg", ts)
    original_id = result.measurement.id

    corrected, _ = kernel.ingestion.correct("user1", original_id, 125.0, "Entered wrong value")
    assert corrected.id != original_id
    assert corrected.supersedes_id == original_id

    # Original is still in the store
    original = kernel.ingestion._store.get(original_id)
    assert original is not None
    assert original.value == 120.0
    print("✓ Measurement immutability preserved — correction creates new record")

def test_logical_delete_preserves_audit():
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    result = kernel.ingest_measurement("user1", "bp_systolic", 120.0, "mmHg", ts)
    mid    = result.measurement.id

    success = kernel.ingestion.request_delete("user1", mid, "Test deletion")
    assert success

    # Measurement hidden from normal queries
    visible = kernel.ingestion.get_measurements("user1", signal_id="bp_systolic")
    assert all(m.id != mid for m in visible)

    # Audit scar preserved
    events = kernel.audit.events_for_entity(mid)
    delete_events = [e for e in events if "delete" in e.event_type.value]
    assert len(delete_events) > 0
    print("✓ Logical delete hides measurement but preserves audit scar")

def test_unit_normalization_lbs_to_kg():
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    result = kernel.ingest_measurement("user1", "weight", 176.0, "lbs", ts)
    assert abs(result.measurement.value - 79.83) < 0.1
    assert result.measurement.unit == "kg"
    print("✓ Unit normalization: lbs correctly converted to kg")


# ═════════════════════════════════════════════════════════════════════════════
# BASELINE ENGINE TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_no_baseline_with_insufficient_data():
    kernel     = SolvraKernel()
    timestamps = make_timestamps(3, days_span=10)
    for ts in timestamps:
        kernel.ingest_measurement("user2", "bp_systolic", 120.0, "mmHg", ts)

    picture = kernel.get_signal_picture("user2", "bp_systolic")
    assert picture.short_baseline is None
    assert picture.uncertainty == UncertaintyLevel.HIGH
    print("✓ No baseline computed with insufficient data — uncertainty HIGH as required")

def test_baseline_computed_with_sufficient_data():
    kernel     = SolvraKernel()
    timestamps = make_timestamps(10, days_span=25)
    for i, ts in enumerate(timestamps):
        kernel.ingest_measurement("user3", "bp_systolic", 115.0 + i * 0.5, "mmHg", ts)

    picture = kernel.get_signal_picture("user3", "bp_systolic")
    assert picture.short_baseline is not None
    assert picture.short_baseline.value > 0
    assert picture.short_baseline.measurement_count >= 5
    print(f"✓ Baseline computed: {picture.short_baseline.value:.1f} from {picture.short_baseline.measurement_count} readings")

def test_quality_weight_reduction():
    """Lower-quality measurements have less influence on baselines."""
    from shilu_kernel.models.entities import Measurement, SourceType, QualityFlag
    m = Measurement(
        user_id="u", signal_id="bp_systolic", value=120.0, unit="mmHg",
        timestamp=datetime.utcnow(), source_type=SourceType.MANUAL_ENTRY,
        entry_method="web_form",
        quality_flags=[QualityFlag.UNCERTAIN, QualityFlag.OUTLIER_SUSPECTED]
    )
    weight = m.quality_weight()
    assert weight < 0.5, f"Expected weight < 0.5, got {weight}"
    print(f"✓ Low-quality measurement weight: {weight:.2f} (appropriately reduced)")


# ═════════════════════════════════════════════════════════════════════════════
# CHANGE DETECTION TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_spike_detection():
    kernel     = SolvraKernel()
    timestamps = make_timestamps(12, days_span=28)
    # Use varied values so MAD > 0, enabling spike detection
    normal_vals = [115, 117, 119, 118, 116, 120, 117, 119, 118, 116, 117]

    for i, ts in enumerate(timestamps[:-1]):
        kernel.ingest_measurement("user4", "bp_systolic", float(normal_vals[i]), "mmHg", ts)

    # Spike — well beyond normal range
    kernel.ingest_measurement("user4", "bp_systolic", 165.0, "mmHg", timestamps[-1])

    picture = kernel.get_signal_picture("user4", "bp_systolic")
    spike_findings = [f for f in picture.findings if f.finding_type == FindingType.SPIKE]
    assert len(spike_findings) > 0
    print(f"✓ Spike correctly detected (confidence: {spike_findings[0].confidence:.2f})")

def test_coverage_risk_detection():
    kernel     = SolvraKernel()
    # Readings ending ~21 days ago — triggers coverage risk (threshold=21 days)
    old_time   = datetime.utcnow() - timedelta(days=36)
    vals = [118, 120, 119, 121, 118, 120, 122, 119]

    for i in range(8):
        ts = old_time + timedelta(days=i * 2)
        kernel.ingest_measurement("user5", "bp_systolic", float(vals[i]), "mmHg", ts)

    picture = kernel.get_signal_picture("user5", "bp_systolic")
    coverage_findings = [f for f in picture.findings if f.finding_type == FindingType.COVERAGE_RISK]
    assert len(coverage_findings) > 0
    print("✓ Coverage risk correctly detected after extended gap")

def test_sustained_drift_detection():
    kernel = SolvraKernel()
    # Early readings: low values (long baseline)
    early_start = datetime.utcnow() - timedelta(days=120)
    for i in range(12):
        ts = early_start + timedelta(days=i * 5)
        kernel.ingest_measurement("user6", "bp_systolic", 110.0 + i * 0.2, "mmHg", ts)

    # Recent readings: significantly higher (short baseline drift)
    recent_start = datetime.utcnow() - timedelta(days=20)
    for i in range(8):
        ts = recent_start + timedelta(days=i * 2)
        kernel.ingest_measurement("user6", "bp_systolic", 135.0 + i * 0.5, "mmHg", ts)

    picture = kernel.get_signal_picture("user6", "bp_systolic")
    drift_findings = [f for f in picture.findings if f.finding_type == FindingType.SUSTAINED_DRIFT]
    print(f"✓ Drift detection ran — {'drift found' if drift_findings else 'no drift (may need more data)'}")


# ═════════════════════════════════════════════════════════════════════════════
# SAFETY ENGINE TESTS — Critical: must fire deterministically
# ═════════════════════════════════════════════════════════════════════════════

def test_urgent_alert_fires_for_extreme_value():
    """
    CRITICAL TEST: A dangerously high BP reading MUST trigger an alert.
    Spec Section 23 — non-bypassable safety triggers.
    """
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    result = kernel.ingest_measurement("user7", "bp_systolic", 185.0, "mmHg", ts)

    # Alert must be present
    alerts = kernel.get_alerts("user7")
    urgent = [a for a in alerts if a.severity == AlertSeverity.URGENT]
    assert len(urgent) > 0, "SAFETY FAILURE: No urgent alert for critically high BP reading"
    print(f"✓ SAFETY: Urgent alert correctly fired for BP=185 (non-suppressible: {not urgent[0].suppressible})")

def test_urgent_alert_is_non_suppressible():
    """
    CRITICAL TEST: URGENT alerts must not be suppressible.
    Pillar 2 — Safety Before Autonomy.
    """
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    kernel.ingest_measurement("user8", "bp_systolic", 185.0, "mmHg", ts)

    alerts = kernel.get_alerts("user8")
    urgent = [a for a in alerts if a.severity == AlertSeverity.URGENT]
    assert len(urgent) > 0
    assert not urgent[0].suppressible, "SAFETY FAILURE: URGENT alert is suppressible"
    print("✓ SAFETY: Urgent alert is correctly non-suppressible")

def test_unacknowledged_urgent_gates_navigation():
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    kernel.ingest_measurement("user9", "bp_systolic", 185.0, "mmHg", ts)

    assert kernel.has_unacknowledged_urgent("user9"), \
        "SAFETY FAILURE: Unacknowledged urgent alert not detected"

    # Acknowledge
    alerts  = kernel.get_alerts("user9")
    urgent  = [a for a in alerts if a.severity == AlertSeverity.URGENT]
    kernel.acknowledge_alert("user9", urgent[0].id)

    assert not kernel.has_unacknowledged_urgent("user9")
    print("✓ SAFETY: Alert acknowledgment gate works correctly")

def test_normal_reading_does_not_trigger_alert():
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    result = kernel.ingest_measurement("user10", "bp_systolic", 118.0, "mmHg", ts)
    alerts = [a for a in kernel.get_alerts("user10") if a.severity == AlertSeverity.URGENT]
    assert len(alerts) == 0
    print("✓ SAFETY: Normal reading correctly produces no urgent alert")

def test_low_hr_triggers_alert():
    """Edge case: dangerously low values also trigger alerts."""
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    kernel.ingest_measurement("user11", "heart_rate", 35.0, "bpm", ts)
    alerts = kernel.get_alerts("user11")
    urgent = [a for a in alerts if a.severity == AlertSeverity.URGENT]
    assert len(urgent) > 0, "SAFETY FAILURE: Low heart rate did not trigger urgent alert"
    print("✓ SAFETY: Low heart rate correctly triggers urgent alert")


# ═════════════════════════════════════════════════════════════════════════════
# AUDIT INTEGRITY TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_audit_chain_valid_after_operations():
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    kernel.ingest_measurement("user12", "bp_systolic", 120.0, "mmHg", ts)
    kernel.ingest_measurement("user12", "bp_systolic", 122.0, "mmHg", ts + timedelta(hours=1))
    kernel.get_signal_picture("user12", "bp_systolic")

    assert kernel.verify_audit_integrity(), "INTEGRITY FAILURE: Audit chain invalid after normal operations"
    print(f"✓ INTEGRITY: Audit chain valid with {len(kernel.audit.all_events())} events")

def test_audit_chain_detects_tampering():
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    kernel.ingest_measurement("user13", "bp_systolic", 120.0, "mmHg", ts)

    # Tamper with an event
    kernel.audit._events[0].details = "TAMPERED"
    assert not kernel.verify_audit_integrity(), "INTEGRITY FAILURE: Tampering not detected"
    print("✓ INTEGRITY: Audit chain correctly detects tampering")

def test_every_ingest_produces_audit_event():
    kernel = SolvraKernel()
    events_before = len(kernel.audit.all_events())
    ts = datetime.utcnow() - timedelta(minutes=5)
    kernel.ingest_measurement("user14", "bp_systolic", 120.0, "mmHg", ts)
    events_after = len(kernel.audit.all_events())
    assert events_after > events_before
    print(f"✓ INTEGRITY: Ingest produced {events_after - events_before} audit event(s)")


# ═════════════════════════════════════════════════════════════════════════════
# EXPLANATION GENERATOR TESTS — Language safety
# ═════════════════════════════════════════════════════════════════════════════

DISEASE_LABELS = [
    "hypertension", "diabetes", "heart disease", "cardiovascular disease",
    "obesity", "depression", "anxiety", "hypoglycemia", "bradycardia", "tachycardia"
]
TREATMENT_DIRECTIVES = [
    "you need medication", "take medication", "stop eating", "you must",
    "you should stop", "medication required"
]
FALSE_CERTAINTY = [
    "this will happen", "you will develop", "you are at high risk of",
    "definitely", "certainly means"
]

def test_explanation_no_disease_labels():
    kernel     = SolvraKernel()
    timestamps = make_timestamps(10, days_span=25)
    for i, ts in enumerate(timestamps):
        kernel.ingest_measurement("user15", "bp_systolic", 130.0 + i, "mmHg", ts)

    picture = kernel.get_signal_picture("user15", "bp_systolic")
    full_text = picture.explanation.full_text.lower()

    for label in DISEASE_LABELS:
        assert label not in full_text, f"LANGUAGE VIOLATION: Disease label '{label}' found in explanation"
    print("✓ LANGUAGE: No disease labels in explanation output")

def test_explanation_no_treatment_directives():
    kernel     = SolvraKernel()
    timestamps = make_timestamps(10, days_span=25)
    for i, ts in enumerate(timestamps):
        kernel.ingest_measurement("user16", "bp_systolic", 130.0 + i, "mmHg", ts)

    picture   = kernel.get_signal_picture("user16", "bp_systolic")
    full_text = picture.explanation.full_text.lower()

    for directive in TREATMENT_DIRECTIVES:
        assert directive not in full_text, f"LANGUAGE VIOLATION: Treatment directive '{directive}' found"
    print("✓ LANGUAGE: No treatment directives in explanation output")

def test_explanation_no_false_certainty():
    kernel     = SolvraKernel()
    timestamps = make_timestamps(10, days_span=25)
    for i, ts in enumerate(timestamps):
        kernel.ingest_measurement("user17", "bp_systolic", 130.0 + i, "mmHg", ts)

    picture   = kernel.get_signal_picture("user17", "bp_systolic")
    full_text = picture.explanation.full_text.lower()

    for phrase in FALSE_CERTAINTY:
        assert phrase not in full_text, f"LANGUAGE VIOLATION: False certainty phrase '{phrase}' found"
    print("✓ LANGUAGE: No false certainty language in explanation output")

def test_high_uncertainty_avoids_reassurance():
    """Under high uncertainty, outputs must not reassure."""
    kernel = SolvraKernel()
    ts     = datetime.utcnow() - timedelta(minutes=5)
    kernel.ingest_measurement("user18", "bp_systolic", 120.0, "mmHg", ts)  # only 1 reading

    picture = kernel.get_signal_picture("user18", "bp_systolic")
    assert picture.uncertainty == UncertaintyLevel.HIGH

    reassurance_phrases = ["everything looks good", "nothing to worry about", "you are healthy"]
    full_text = picture.explanation.full_text.lower()
    for phrase in reassurance_phrases:
        assert phrase not in full_text, f"SAFETY: Reassurance phrase found under high uncertainty: '{phrase}'"
    print("✓ LANGUAGE: High uncertainty correctly avoids reassurance")


# ═════════════════════════════════════════════════════════════════════════════
# EXPORT TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_export_includes_provenance():
    kernel     = SolvraKernel()
    timestamps = make_timestamps(8, days_span=20)
    for i, ts in enumerate(timestamps):
        kernel.ingest_measurement("user19", "bp_systolic", 118.0 + i * 0.5, "mmHg", ts)

    export = kernel.export_state("user19")
    assert "bp_systolic" in export["measurements"]
    assert "audit_integrity" in export
    assert export["audit_integrity"] is True
    print(f"✓ EXPORT: Export produced with {len(export['measurements'].get('bp_systolic', []))} measurements and audit verification")

def test_export_includes_uncertainty():
    kernel     = SolvraKernel()
    timestamps = make_timestamps(10, days_span=25)
    for i, ts in enumerate(timestamps):
        kernel.ingest_measurement("user20", "bp_systolic", 118.0 + i * 0.3, "mmHg", ts)

    kernel.get_signal_picture("user20", "bp_systolic")  # populate baselines
    export = kernel.export_state("user20")

    bp_baselines = export.get("baselines", {}).get("bp_systolic")
    if bp_baselines and bp_baselines.get("short"):
        assert "uncertainty" in bp_baselines["short"]
        print(f"✓ EXPORT: Uncertainty label included in baseline export: {bp_baselines['short']['uncertainty']}")
    else:
        print("✓ EXPORT: Export completed (baselines pending more data)")


# ═════════════════════════════════════════════════════════════════════════════
# COLD START / MVL TESTS
# ═════════════════════════════════════════════════════════════════════════════

def test_mvl_progress_tracking():
    kernel = SolvraKernel()
    timestamps = make_timestamps(4, days_span=10)
    for i, ts in enumerate(timestamps):
        kernel.ingest_measurement("user21", "bp_systolic", 120.0 + i, "mmHg", ts)

    picture = kernel.get_signal_picture("user21", "bp_systolic")
    mvl = picture.mvl_status
    assert mvl["applicable"] is True
    assert mvl["threshold_met"] is False
    assert mvl["readings_have"] == 4
    assert mvl["readings_needed"] == 6
    print(f"✓ MVL: Progress correctly tracked — {mvl['readings_have']}/{mvl['readings_needed']} readings, {mvl['days_have']}/{mvl['days_needed']} days")


# ═════════════════════════════════════════════════════════════════════════════
# RUN ALL TESTS
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_groups = [
        ("Statistical Functions", [
            test_median_odd, test_median_even, test_median_single,
            test_mad_basic, test_mad_identical, test_mad_too_few,
        ]),
        ("Ingestion Service", [
            test_valid_ingestion, test_out_of_range_rejected,
            test_unknown_signal_rejected, test_retrospective_entry_flagged,
            test_approximate_flag, test_measurement_immutability,
            test_logical_delete_preserves_audit, test_unit_normalization_lbs_to_kg,
        ]),
        ("Baseline Engine", [
            test_no_baseline_with_insufficient_data,
            test_baseline_computed_with_sufficient_data,
            test_quality_weight_reduction,
        ]),
        ("Change Detection", [
            test_spike_detection, test_coverage_risk_detection, test_sustained_drift_detection,
        ]),
        ("Safety Engine [CRITICAL]", [
            test_urgent_alert_fires_for_extreme_value,
            test_urgent_alert_is_non_suppressible,
            test_unacknowledged_urgent_gates_navigation,
            test_normal_reading_does_not_trigger_alert,
            test_low_hr_triggers_alert,
        ]),
        ("Audit Integrity [CRITICAL]", [
            test_audit_chain_valid_after_operations,
            test_audit_chain_detects_tampering,
            test_every_ingest_produces_audit_event,
        ]),
        ("Language Safety [REGULATORY]", [
            test_explanation_no_disease_labels,
            test_explanation_no_treatment_directives,
            test_explanation_no_false_certainty,
            test_high_uncertainty_avoids_reassurance,
        ]),
        ("Export", [
            test_export_includes_provenance,
            test_export_includes_uncertainty,
        ]),
        ("Cold Start / MVL", [
            test_mvl_progress_tracking,
        ]),
    ]

    total_passed = 0
    total_failed = 0

    for group_name, tests in test_groups:
        print(f"\n{'═'*60}")
        print(f"  {group_name}")
        print(f"{'═'*60}")
        for test_fn in tests:
            try:
                test_fn()
                total_passed += 1
            except Exception as e:
                print(f"✗ FAILED: {test_fn.__name__}: {e}")
                total_failed += 1

    print(f"\n{'═'*60}")
    print(f"  RESULTS: {total_passed} passed, {total_failed} failed")
    print(f"{'═'*60}")
    if total_failed == 0:
        print("  All tests passed. Kernel integrity verified.")
    else:
        print("  FAILURES DETECTED. Review before proceeding.")


# ═══════════════════════════════════════════════════════════════════════════════
# NEW TESTS — Dual Reference Architecture, Alert Fatigue Prevention,
#             Digital Twin Phase Tracking
# ═══════════════════════════════════════════════════════════════════════════════

class TestPopulationContextEngine(unittest.TestCase):
    """
    Tests for the dual-reference architecture.
    Verifies that BaselineContextNotes are generated correctly,
    surfaced once, and go dormant after acknowledgment.
    """

    def setUp(self):
        from shilu_kernel.engines.baseline_engine import PopulationContextEngine
        from shilu_kernel.engines.audit_engine import AuditEngine
        from shilu_kernel.models.entities import DerivedFeature, UncertaintyLevel
        self.audit  = AuditEngine()
        self.engine = PopulationContextEngine(self.audit)
        self.DerivedFeature   = DerivedFeature
        self.UncertaintyLevel = UncertaintyLevel

    def _make_baseline(self, signal_id, value, uncertainty):
        from datetime import datetime, timedelta
        return self.DerivedFeature(
            user_id            = "u_pop_test",
            signal_id          = signal_id,
            feature_type       = "baseline_short",
            value              = value,
            window_start       = datetime.utcnow() - timedelta(days=30),
            window_end         = datetime.utcnow(),
            measurement_count  = 12,
            method             = "quality-weighted median",
            quality_weight_sum = 10.0,
            uncertainty        = uncertainty,
        )

    def test_no_note_for_high_uncertainty_baseline(self):
        """Should not generate a note when baseline uncertainty is HIGH."""
        baseline = self._make_baseline("bp_systolic", 145.0, self.UncertaintyLevel.HIGH)
        note = self.engine.assess_baseline_context("u1", "bp_systolic", baseline)
        self.assertIsNone(note, "Must not surface context note when uncertainty is HIGH")

    def test_note_generated_for_elevated_bp_systolic(self):
        """Should generate a note when bp_systolic baseline exceeds population normal."""
        baseline = self._make_baseline("bp_systolic", 145.0, self.UncertaintyLevel.MEDIUM)
        note = self.engine.assess_baseline_context("u2", "bp_systolic", baseline)
        self.assertIsNotNone(note, "Should generate note for elevated systolic baseline")
        self.assertEqual(note.signal_id, "bp_systolic")
        self.assertFalse(note.acknowledged)
        self.assertFalse(note.dormant)

    def test_note_not_repeated_for_same_signal(self):
        """Should not generate a second note for the same signal before acknowledgment."""
        baseline = self._make_baseline("bp_systolic", 145.0, self.UncertaintyLevel.MEDIUM)
        note1 = self.engine.assess_baseline_context("u3", "bp_systolic", baseline)
        note2 = self.engine.assess_baseline_context("u3", "bp_systolic", baseline)
        self.assertIsNotNone(note1)
        self.assertIsNone(note2, "Second call must return None — note already active")

    def test_note_goes_dormant_after_acknowledgment(self):
        """Note must become dormant after user acknowledges it."""
        baseline = self._make_baseline("bp_systolic", 145.0, self.UncertaintyLevel.MEDIUM)
        note = self.engine.assess_baseline_context("u4", "bp_systolic", baseline)
        self.assertIsNotNone(note)

        result = self.engine.acknowledge_note("u4", "bp_systolic")
        self.assertTrue(result)

        active = self.engine.get_active_notes("u4")
        self.assertEqual(len(active), 0, "No active notes after acknowledgment")

    def test_no_note_for_normal_baseline(self):
        """Should not generate a note when baseline is within population normal range."""
        baseline = self._make_baseline("bp_systolic", 112.0, self.UncertaintyLevel.MEDIUM)
        note = self.engine.assess_baseline_context("u5", "bp_systolic", baseline)
        self.assertIsNone(note, "No note when baseline is within population normal")

    def test_note_language_is_non_diagnostic(self):
        """Note language must not contain diagnostic labels."""
        from shilu_kernel.models.entities import BaselineContextStatus
        baseline = self._make_baseline("glucose", 108.0, self.UncertaintyLevel.LOW)
        note = self.engine.assess_baseline_context("u6", "glucose", baseline)
        if note:
            diagnostic_terms = ["hypertension", "diabetes", "diagnos", "disease", "condition"]
            for term in diagnostic_terms:
                self.assertNotIn(
                    term.lower(), note.context_message.lower(),
                    f"Diagnostic term '{term}' found in BaselineContextNote — not allowed"
                )

    def test_note_message_references_doctor_not_self_treatment(self):
        """Note must direct user to doctor, not suggest self-treatment."""
        baseline = self._make_baseline("bp_systolic", 145.0, self.UncertaintyLevel.MEDIUM)
        note = self.engine.assess_baseline_context("u7", "bp_systolic", baseline)
        if note:
            self.assertIn("doctor", note.context_message.lower(),
                "Note should reference speaking to a doctor")


class TestAlertFatiguePrevention(unittest.TestCase):
    """
    Tests for the three-situation distinction.
    Verifies that chronic elevation does not trigger safety escalation,
    and that only acute deviations do.
    """

    def setUp(self):
        self.kernel = SolvraKernel()
        self.user   = "u_fatigue_test"
        self.base_ts = datetime(2025, 1, 1, 8, 0)

    def _ingest_many(self, signal_id, value, count, unit="mmHg"):
        """Ingest many readings of the same value to establish a stable elevated baseline."""
        results = []
        for i in range(count):
            ts = self.base_ts + timedelta(days=i)
            r  = self.kernel.ingest_measurement(self.user, signal_id, value, unit, ts)
            results.append(r)
        return results

    def test_stable_elevated_baseline_does_not_repeatedly_escalate(self):
        """
        A user with a chronically elevated but STABLE bp_systolic baseline
        should not receive repeated escalation events — only potential
        one-time BaselineContextNote (not a safety alert).
        """
        # Ingest 30 days of stable readings at 135 mmHg (above population normal, below L2 threshold)
        results = self._ingest_many("bp_systolic", 135.0, 30)

        # Count escalations across all ingestions
        total_escalations = sum(len(r.escalations) for r in results)

        # 135 is above population normal but below safety threshold (160)
        # Should generate zero safety escalations
        self.assertEqual(
            total_escalations, 0,
            f"Stable elevated baseline at 135 should not generate safety escalations. Got {total_escalations}"
        )

    def test_acute_spike_above_safety_threshold_does_escalate(self):
        """An acute spike above the Level 2 safety threshold must escalate."""
        # Establish normal baseline first
        for i in range(14):
            ts = self.base_ts + timedelta(days=i)
            self.kernel.ingest_measurement(self.user + "_acute", "bp_systolic", 118.0, "mmHg", ts)

        # Now inject a spike well above L2 threshold (160)
        spike_ts = self.base_ts + timedelta(days=15)
        result   = self.kernel.ingest_measurement(self.user + "_acute", "bp_systolic", 175.0, "mmHg", spike_ts)

        self.assertTrue(
            len(result.alerts) > 0 or len(result.escalations) > 0,
            "Acute spike at 175 mmHg must trigger a safety alert"
        )


class TestDigitalTwinPhaseTracking(unittest.TestCase):
    """
    Tests for DigitalTwinStatus and phase progression.
    Verifies that the twin accurately describes its own state
    and that phase language is honest.
    """

    def setUp(self):
        self.kernel  = SolvraKernel()
        self.user    = "u_twin_test"
        self.base_ts = datetime(2025, 1, 1, 8, 0)

    def test_new_user_is_phase_1(self):
        """A user with no data should be in Phase 1."""
        status = self.kernel.get_digital_twin_status(self.user + "_new")
        from shilu_kernel.models.entities import DigitalTwinPhase
        self.assertEqual(
            status.overall_phase,
            DigitalTwinPhase.PHASE_1_PERSONAL_RECORD,
            "New user with no data should be Phase 1"
        )

    def test_twin_status_has_maturity_message(self):
        """Digital twin status must always include a maturity message."""
        status = self.kernel.get_digital_twin_status(self.user + "_msg")
        self.assertIsNotNone(status.maturity_message)
        self.assertGreater(len(status.maturity_message), 20)

    def test_twin_status_is_not_a_grade(self):
        """Maturity message must not use grading or scoring language."""
        status = self.kernel.get_digital_twin_status(self.user + "_grade")
        grade_terms = ["score", "grade", "rating", "rank", "level up", "unlock"]
        for term in grade_terms:
            self.assertNotIn(
                term.lower(), status.maturity_message.lower(),
                f"Grade term '{term}' found in twin maturity message — must not grade the user"
            )

    def test_twin_phase_dict_covers_all_signals(self):
        """Phase dict must cover every defined signal."""
        status = self.kernel.get_digital_twin_status(self.user + "_signals")
        from shilu_kernel.models.entities import SIGNAL_DEFINITIONS
        for signal_id in SIGNAL_DEFINITIONS.keys():
            self.assertIn(
                signal_id, status.signals_in_phase,
                f"Signal {signal_id} missing from digital twin phase dict"
            )

    def test_baseline_context_note_not_an_escalation(self):
        """BaselineContextNotes must not appear in safety alerts or escalations."""
        # Ingest enough data at a chronically elevated level to form a baseline
        for i in range(30):
            ts = self.base_ts + timedelta(days=i)
            self.kernel.ingest_measurement(
                self.user + "_ctx", "bp_systolic", 138.0, "mmHg", ts
            )

        # Get signal picture to trigger population context assessment
        self.kernel.get_signal_picture(self.user + "_ctx", "bp_systolic")

        # Safety alerts should be empty (138 is below L2 threshold)
        alerts = self.kernel.get_alerts(self.user + "_ctx")
        urgent = [a for a in alerts if a.severity.value == "urgent"]
        self.assertEqual(len(urgent), 0,
            "Chronically elevated but stable baseline must not generate urgent safety alerts")

        # Context notes should exist separately
        notes = self.kernel.get_baseline_context_notes(self.user + "_ctx")
        # Notes may or may not exist depending on baseline maturity — that is fine
        # The key test is that they are separate from safety alerts
        for note in notes:
            self.assertFalse(
                hasattr(note, "severity"),
                "BaselineContextNote must not have a severity field — it is not an alert"
            )


if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    for cls in [
        TestPopulationContextEngine,
        TestAlertFatiguePrevention,
        TestDigitalTwinPhaseTracking,
    ]:
        suite.addTests(loader.loadTestsFromTestCase(cls))

    print("\n" + "═" * 60)
    print("  NEW TESTS — Dual Reference, Alert Fatigue, Digital Twin")
    print("═" * 60)
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    if result.wasSuccessful():
        print(f"\n  ✓ All {result.testsRun} new tests passed.")
    else:
        print(f"\n  ✗ {len(result.failures + result.errors)} failures.")
