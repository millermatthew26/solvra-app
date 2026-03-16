"""
Solvra Kernel — Threshold Configuration
=========================================
Versioned, clinician-reviewable threshold definitions.
Spec Section 14 — Calibration Layer.
Spec Section 13.2 — Safety Threshold Policy.

CRITICAL: All thresholds marked PLACEHOLDER must be reviewed and
signed off by a qualified clinical advisor before production use.
These values are structural placeholders only — they demonstrate
the architecture but must not be used clinically without review.

Every threshold change must:
  1. Increment the config version
  2. Include a rationale note
  3. Receive clinical advisor sign-off
  4. Generate an AuditEvent
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime


CONFIG_VERSION = "0.1.0-placeholder"
CONFIG_DATE    = "2026-02-01"
CONFIG_AUTHOR  = "Solvra Kernel Team"
CONFIG_STATUS  = "PLACEHOLDER — REQUIRES CLINICAL ADVISOR SIGN-OFF BEFORE PRODUCTION"


# ─── CALIBRATION THRESHOLDS ──────────────────────────────────────────────────
# Uncertainty tier boundaries per signal.
# Format: (high_medium_boundary, medium_low_boundary)
# Expressed as confidence interval width as % of baseline value.
# PLACEHOLDER — clinical advisor must define actual values.

CALIBRATION_THRESHOLDS = {
    # signal_id: (high→medium boundary CI%, medium→low boundary CI%)
    "bp_systolic":   (0.20, 0.10),   # PLACEHOLDER
    "bp_diastolic":  (0.20, 0.10),   # PLACEHOLDER
    "heart_rate":    (0.25, 0.12),   # PLACEHOLDER
    "weight":        (0.15, 0.08),   # PLACEHOLDER
    "waist_circ":    (0.15, 0.08),   # PLACEHOLDER
    "sleep_hours":   (0.30, 0.15),   # PLACEHOLDER
    "sleep_quality": (0.40, 0.20),   # PLACEHOLDER — subjective scale
    "activity_mins": (0.35, 0.18),   # PLACEHOLDER
    "stress_level":  (0.40, 0.20),   # PLACEHOLDER — subjective scale
    "glucose":       (0.20, 0.10),   # PLACEHOLDER

    # v0.2 signals
    "body_temp":     (0.02, 0.01),   # PLACEHOLDER — narrow range by nature
    "spo2":          (0.03, 0.015),  # PLACEHOLDER — narrow range, high sensitivity
    "hrv":           (0.35, 0.18),   # PLACEHOLDER — high natural variability
    "energy_level":  (0.40, 0.20),   # PLACEHOLDER — subjective scale
}


# ─── SAFETY THRESHOLDS ───────────────────────────────────────────────────────
# Non-bypassable escalation triggers.
# Spec Section 13 — Safety & Escalation Engine.
# PLACEHOLDER — ALL values require clinical advisor sign-off.

@dataclass(frozen=True)
class SafetyThreshold:
    signal_id:       str
    level_3_value:   Optional[float]   # single reading → Level 3 URGENT
    level_2_value:   Optional[float]   # single reading → Level 2 PROMPT ACTION
    level_2_sustained_days: int = 14   # sustained readings → Level 2
    rationale:       str = ""
    clinical_ref:    str = ""          # citation or guideline reference
    placeholder:     bool = True       # must be False after clinical sign-off


SAFETY_THRESHOLDS = {
    # Systolic BP
    "bp_systolic_high": SafetyThreshold(
        signal_id      = "bp_systolic",
        level_3_value  = 180.0,      # PLACEHOLDER — example only
        level_2_value  = 160.0,      # PLACEHOLDER — example only
        level_2_sustained_days = 14,
        rationale      = "Severely elevated systolic BP associated with hypertensive crisis risk",
        clinical_ref   = "PLACEHOLDER — requires clinical citation",
        placeholder    = True,
    ),
    # Diastolic BP
    "bp_diastolic_high": SafetyThreshold(
        signal_id      = "bp_diastolic",
        level_3_value  = 120.0,      # PLACEHOLDER
        level_2_value  = 100.0,      # PLACEHOLDER
        level_2_sustained_days = 14,
        rationale      = "Elevated diastolic BP — sustained pattern warrants evaluation",
        clinical_ref   = "PLACEHOLDER — requires clinical citation",
        placeholder    = True,
    ),
    # Heart rate extremes
    "heart_rate_high": SafetyThreshold(
        signal_id      = "heart_rate",
        level_3_value  = 150.0,      # PLACEHOLDER — resting only
        level_2_value  = 120.0,      # PLACEHOLDER — resting only
        rationale      = "Elevated resting heart rate",
        clinical_ref   = "PLACEHOLDER",
        placeholder    = True,
    ),
    "heart_rate_low": SafetyThreshold(
        signal_id      = "heart_rate",
        level_3_value  = 40.0,       # PLACEHOLDER
        level_2_value  = 50.0,       # PLACEHOLDER
        rationale      = "Low resting heart rate — bradycardia range",
        clinical_ref   = "PLACEHOLDER",
        placeholder    = True,
    ),
    # Glucose
    "glucose_high": SafetyThreshold(
        signal_id      = "glucose",
        level_3_value  = 400.0,      # PLACEHOLDER
        level_2_value  = 200.0,      # PLACEHOLDER
        rationale      = "Elevated fasting glucose",
        clinical_ref   = "PLACEHOLDER",
        placeholder    = True,
    ),

    # SpO2 — low oxygen saturation
    "spo2_low": SafetyThreshold(
        signal_id      = "spo2",
        level_3_value  = 90.0,       # PLACEHOLDER — below 90% is medical concern
        level_2_value  = 94.0,       # PLACEHOLDER — below 95% warrants attention
        rationale      = "Low blood oxygen saturation",
        clinical_ref   = "PLACEHOLDER — WHO hypoxemia guidelines",
        placeholder    = True,
    ),

    # Body temperature — fever
    "body_temp_high": SafetyThreshold(
        signal_id      = "body_temp",
        level_3_value  = 103.0,      # PLACEHOLDER — high fever
        level_2_value  = 100.4,      # PLACEHOLDER — clinical fever threshold
        rationale      = "Elevated body temperature indicating fever",
        clinical_ref   = "PLACEHOLDER — CDC fever definition",
        placeholder    = True,
    ),

    # Body temperature — hypothermia
    "body_temp_low": SafetyThreshold(
        signal_id      = "body_temp",
        level_3_value  = 95.0,       # PLACEHOLDER — hypothermia threshold
        level_2_value  = 96.5,       # PLACEHOLDER
        rationale      = "Low body temperature",
        clinical_ref   = "PLACEHOLDER",
        placeholder    = True,
    ),
}


# ─── MVL THRESHOLDS ──────────────────────────────────────────────────────────
# Minimum Viable Longitudinal — when personal baselines replace population priors.
# Spec Section 12 — MVL Thresholds (v0.1.1).

@dataclass(frozen=True)
class MVLThreshold:
    signal_id:       str
    min_readings:    int          # minimum number of measurements
    min_days:        int          # across at least this many days
    description:     str


MVL_THRESHOLDS = {
    "bp_systolic":   MVLThreshold("bp_systolic",   6,  14, "6–10 readings across 2–3 weeks"),
    "bp_diastolic":  MVLThreshold("bp_diastolic",  6,  14, "6–10 readings across 2–3 weeks"),
    "weight":        MVLThreshold("weight",         4,  21, "Weekly entries across 3–4 weeks"),
    "waist_circ":    MVLThreshold("waist_circ",     3,  21, "Weekly entries across 3–4 weeks"),
    "sleep_hours":   MVLThreshold("sleep_hours",    3,  14, "3–5 entries across 2 weeks"),
    "sleep_quality": MVLThreshold("sleep_quality",  3,  14, "3–5 entries across 2 weeks"),
    "activity_mins": MVLThreshold("activity_mins",  4,  21, "Weekly check-ins across 3–4 weeks"),
    "stress_level":  MVLThreshold("stress_level",   4,  21, "Weekly check-ins across 3–4 weeks"),
    "glucose":       MVLThreshold("glucose",        3,  21, "3 readings across 3 weeks"),

    # v0.2 signals
    "body_temp":     MVLThreshold("body_temp",      5,  14, "5 readings across 2 weeks"),
    "spo2":          MVLThreshold("spo2",           5,  14, "5 readings across 2 weeks"),
    "hrv":           MVLThreshold("hrv",            5,  21, "5 readings across 3 weeks — wearable recommended"),
    "energy_level":  MVLThreshold("energy_level",   5,  14, "5 entries across 2 weeks"),
}


# ─── BASELINE ENGINE PARAMETERS ──────────────────────────────────────────────
# Spec Section 18 — Baseline Engine.

BASELINE_MIN_MEASUREMENTS = 5     # minimum before any baseline is computed
BASELINE_MIN_DAYS         = 14    # must span at least 14 days
BASELINE_SHORT_WINDOW_DAYS = 30   # short-term baseline window
BASELINE_LONG_WINDOW_DAYS  = 90   # long-term baseline window


# ─── CHANGE DETECTION PARAMETERS ─────────────────────────────────────────────
# Spec Section 19 — Change Detection.
# These are statistical defaults — clinical advisor may adjust per signal.

SPIKE_THRESHOLD_MAD_MULTIPLIER   = 3.0    # reading > median + 3×MAD = spike candidate
DRIFT_THRESHOLD_PERCENT          = 0.10   # 10% shift from long to short baseline = drift
DRIFT_MIN_DAYS                   = 7      # sustained drift must persist this many days
VOLATILITY_INCREASE_THRESHOLD    = 1.5    # MAD increases by this factor = volatility finding
COVERAGE_RISK_MAX_GAP_DAYS       = 21     # no readings for this long = coverage risk finding


# ─── POPULATION REFERENCE RANGES ─────────────────────────────────────────────
# Used by the dual-reference architecture to contextualise personal baselines.
# These are NOT safety thresholds — they do not trigger escalation.
# They generate a one-time calm BaselineContextNote when a personal baseline
# is established outside the normal range.
#
# PLACEHOLDER — All values require clinical advisor sign-off.
# Sources listed are the intended citation targets, not confirmed values.
# Format: list of PopulationReference objects per signal.
# Multiple entries per signal for age/sex stratification.

from solvra_kernel.models.entities import PopulationReference

POPULATION_REFERENCES = {
    "bp_systolic": [
        PopulationReference(
            signal_id        = "bp_systolic",
            age_range        = "all",
            sex              = "all",
            normal_low       = 90.0,
            normal_high      = 120.0,   # PLACEHOLDER — AHA optimal <120
            concern_low      = None,
            concern_high     = 130.0,   # PLACEHOLDER — AHA elevated starts at 130
            unit             = "mmHg",
            guideline_source = "PLACEHOLDER — AHA/ACC 2017 Hypertension Guidelines",
            debate_note      = "Guidelines differ: some define normal as <130, others <140. Clinical context matters.",
            placeholder      = True,
        ),
    ],
    "bp_diastolic": [
        PopulationReference(
            signal_id        = "bp_diastolic",
            age_range        = "all",
            sex              = "all",
            normal_low       = 60.0,
            normal_high      = 80.0,    # PLACEHOLDER
            concern_low      = None,
            concern_high     = 80.0,    # PLACEHOLDER
            unit             = "mmHg",
            guideline_source = "PLACEHOLDER — AHA/ACC 2017",
            debate_note      = "Isolated diastolic elevation is interpreted differently across guidelines.",
            placeholder      = True,
        ),
    ],
    "heart_rate": [
        PopulationReference(
            signal_id        = "heart_rate",
            age_range        = "all",
            sex              = "all",
            normal_low       = 60.0,
            normal_high      = 80.0,    # PLACEHOLDER — typical resting range
            concern_low      = 50.0,    # PLACEHOLDER — below 50 worth noting for non-athletes
            concern_high     = 90.0,    # PLACEHOLDER — resting HR >90 often cited
            unit             = "bpm",
            guideline_source = "PLACEHOLDER — clinical consensus, varies by fitness level",
            debate_note      = "Athletes may have resting HR of 40–50 which is normal for them. Fitness context required.",
            placeholder      = True,
        ),
    ],
    "glucose": [
        PopulationReference(
            signal_id        = "glucose",
            age_range        = "all",
            sex              = "all",
            normal_low       = 70.0,
            normal_high      = 99.0,    # PLACEHOLDER — ADA fasting normal <100
            concern_low      = None,
            concern_high     = 100.0,   # PLACEHOLDER — ADA pre-diabetic range 100-125
            unit             = "mg/dL",
            guideline_source = "PLACEHOLDER — ADA Standards of Medical Care 2024",
            debate_note      = "Pre-diabetic range (100-125) is well-established. Context of fasting vs non-fasting critical.",
            placeholder      = True,
        ),
    ],
    "sleep_hours": [
        PopulationReference(
            signal_id        = "sleep_hours",
            age_range        = "adult",
            sex              = "all",
            normal_low       = 7.0,
            normal_high      = 9.0,
            concern_low      = 6.0,
            concern_high     = None,
            unit             = "hours",
            guideline_source = "PLACEHOLDER — CDC Sleep Guidelines / Sleep Foundation",
            debate_note      = "Individual sleep needs vary. Some people function well on 6 hrs. Consistency matters more than absolute hours.",
            placeholder      = True,
        ),
    ],
    "body_temp": [
        PopulationReference(
            signal_id        = "body_temp",
            age_range        = "all",
            sex              = "all",
            normal_low       = 97.0,
            normal_high      = 99.0,    # PLACEHOLDER — typical resting oral temp range
            concern_low      = 96.0,
            concern_high     = 99.5,
            unit             = "°F",
            guideline_source = "PLACEHOLDER — clinical consensus",
            debate_note      = "Normal range varies by measurement method and time of day. Trends matter more than single readings.",
            placeholder      = True,
        ),
    ],
    "spo2": [
        PopulationReference(
            signal_id        = "spo2",
            age_range        = "all",
            sex              = "all",
            normal_low       = 95.0,
            normal_high      = 100.0,   # PLACEHOLDER
            concern_low      = 94.0,
            concern_high     = None,
            unit             = "%",
            guideline_source = "PLACEHOLDER — WHO / clinical consensus",
            debate_note      = "Readings below 95% warrant attention. Below 90% is a medical concern. Altitude affects baseline.",
            placeholder      = True,
        ),
    ],
    "hrv": [
        PopulationReference(
            signal_id        = "hrv",
            age_range        = "all",
            sex              = "all",
            normal_low       = 20.0,
            normal_high      = 100.0,   # PLACEHOLDER — wide range, highly individual
            concern_low      = 15.0,
            concern_high     = None,
            unit             = "ms",
            guideline_source = "PLACEHOLDER — research consensus varies widely",
            debate_note      = "HRV is highly individual. Personal trend is far more meaningful than population comparison. Athletes often have much higher HRV.",
            placeholder      = True,
        ),
    ],
}


# ─── POPULATION REFERENCE ENGINE PARAMETERS ──────────────────────────────────
# Controls when and how BaselineContextNotes are generated.

# How far outside population range before a note is generated
# Expressed as % beyond the concern threshold
POPULATION_CONTEXT_NOTE_BUFFER = 0.0    # any exceedance triggers a note

# Minimum baseline maturity before population comparison is run
# Only compare once the personal baseline has reasonable stability
POPULATION_CONTEXT_MIN_UNCERTAINTY = "medium"   # HIGH uncertainty → no comparison yet

# How much the baseline must shift before a dormant note is re-activated
POPULATION_CONTEXT_REACTIVATION_SHIFT = 0.10   # 10% shift from original comparison point
