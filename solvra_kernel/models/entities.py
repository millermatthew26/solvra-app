"""
Solvra Kernel — Canonical Data Models
======================================
Implements all core entities from Master Kernel Specification Section 7.
These are the semantic definitions. Storage implementation may vary.

Pillar alignment:
  - Every entity carries provenance (Pillar 3 — Trust Through Verifiable Integrity)
  - Measurements are immutable once written (Pillar 1 — Personal Ownership)
  - Safety events are never silently erasable (Pillar 2 — Safety Before Autonomy)
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, List, Dict
import uuid


# ─── ENUMERATIONS ────────────────────────────────────────────────────────────

class SourceType(str, Enum):
    MANUAL_ENTRY    = "manual_entry"       # v0.1 — primary source
    EXTERNAL_IMPORT = "external_import"    # reserved for future phases
    CLINICIAN_ENTRY = "clinician_entry"    # reserved for future phases


class QualityFlag(str, Enum):
    SELF_REPORTED      = "self_reported"
    UNCERTAIN          = "uncertain"
    DEVICE_CALIBRATED  = "device_calibrated"   # reserved
    OUTLIER_SUSPECTED  = "outlier_suspected"
    MISSING_CONTEXT    = "missing_context"
    BATCH_ENTERED      = "batch_entered"        # logged retrospectively, not in real time
    APPROXIMATE        = "approximate"          # user-flagged as approximate


class UncertaintyLevel(str, Enum):
    HIGH   = "high"
    MEDIUM = "medium"
    LOW    = "low"


class RiskBand(str, Enum):
    LOW_CONCERN      = "low_concern"
    MONITOR          = "monitor"
    ELEVATED_CONCERN = "elevated_concern"
    HIGH_CONCERN     = "high_concern"     # escalation likely


class AlertSeverity(str, Enum):
    INFO    = "info"
    MONITOR = "monitor"
    URGENT  = "urgent"     # non-suppressible


class FindingType(str, Enum):
    SPIKE            = "spike"
    SUSTAINED_DRIFT  = "sustained_drift"
    VOLATILITY_SHIFT = "volatility_shift"
    COVERAGE_RISK    = "coverage_risk"


class EscalationLevel(str, Enum):
    LEVEL_1_AWARENESS     = "level_1_awareness"      # informational, dismissible
    LEVEL_2_PROMPT_ACTION = "level_2_prompt_action"  # requires acknowledgment
    LEVEL_3_URGENT        = "level_3_urgent"         # non-dismissible until acknowledged


class AuditEventType(str, Enum):
    CREATE_MEASUREMENT   = "create_measurement"
    SUPERSEDE_MEASUREMENT = "supersede_measurement"
    DELETE_REQUEST       = "delete_request"
    BASELINE_UPDATE      = "baseline_update"
    FINDING_CREATED      = "finding_created"
    RISKFLAG_CREATED     = "riskflag_created"
    ALERT_ISSUED         = "alert_issued"
    ESCALATION_TRIGGERED = "escalation_triggered"
    EXPORT_GENERATED     = "export_generated"
    THRESHOLD_TRIGGERED  = "threshold_triggered"


class Actor(str, Enum):
    USER   = "user"
    SYSTEM = "system"
    ADMIN  = "admin"    # reserved


# ─── SIGNAL DEFINITIONS ──────────────────────────────────────────────────────

@dataclass(frozen=True)
class SignalDefinition:
    """
    Canonical definition of a measurable health variable.
    Spec Section 7.1 — SignalDefinition entity.
    """
    signal_id:   str
    name:        str
    description: str
    unit:        str
    valid_min:   float
    valid_max:   float
    domain:      str        # "cardiovascular", "metabolic", "behavioral"


# Initial signal set — Spec Section 8
SIGNAL_DEFINITIONS = {
    "bp_systolic":   SignalDefinition("bp_systolic",   "Systolic Blood Pressure",  "Upper BP number",          "mmHg",    60,  260, "cardiovascular"),
    "bp_diastolic":  SignalDefinition("bp_diastolic",  "Diastolic Blood Pressure", "Lower BP number",          "mmHg",    30,  160, "cardiovascular"),
    "heart_rate":    SignalDefinition("heart_rate",    "Heart Rate",               "Beats per minute",         "bpm",     30,  220, "cardiovascular"),
    "weight":        SignalDefinition("weight",        "Body Weight",              "Body weight in lbs",       "lbs",     10,  800, "metabolic"),
    "waist_circ":    SignalDefinition("waist_circ",    "Waist Circumference",      "Waist measurement in inches", "inches", 16, 100, "metabolic"),
    "sleep_hours":   SignalDefinition("sleep_hours",   "Sleep Duration",           "Hours of sleep",           "hours",   0,   24,  "behavioral"),
    "sleep_quality": SignalDefinition("sleep_quality", "Sleep Quality",            "Subjective quality 1–5",   "1-5",     1,   5,   "behavioral"),
    "activity_mins": SignalDefinition("activity_mins", "Activity",                 "Active minutes per day",   "minutes", 0,   1440,"behavioral"),
    "stress_level":  SignalDefinition("stress_level",  "Stress Level",             "Subjective stress 1–5",    "1-5",     1,   5,   "behavioral"),
    "glucose":       SignalDefinition("glucose",       "Fasting Glucose",          "Fasting blood glucose",    "mg/dL",   40,  600, "metabolic"),

    # v0.2 signals — non-invasive, no lab test required
    "body_temp":     SignalDefinition("body_temp",     "Body Temperature",         "Resting body temperature", "°F",      95,  105, "physiological"),
    "spo2":          SignalDefinition("spo2",          "Oxygen Saturation",        "Blood oxygen level (SpO2)","%",       70,  100, "physiological"),
    "hrv":           SignalDefinition("hrv",           "Heart Rate Variability",   "HRV in milliseconds",      "ms",       0,  250, "cardiovascular"),
    "energy_level":  SignalDefinition("energy_level",  "Energy Level",             "Subjective energy 1–5",    "1-5",      1,    5, "behavioral"),
}


# ─── CORE ENTITIES ───────────────────────────────────────────────────────────

@dataclass
class Measurement:
    """
    A time-stamped value for a signal.
    Spec Section 7.1 — Measurement entity.
    Spec Section 7.2 — Schema requirements.

    IMMUTABILITY RULE: Once written, measurements are never modified.
    Corrections are new measurements with supersedes_id set.
    """
    user_id:       str
    signal_id:     str
    value:         float
    unit:          str
    timestamp:     datetime
    source_type:   SourceType
    entry_method:  str                         # "web_form", "api", etc.
    quality_flags: List[QualityFlag] = field(default_factory=list)
    notes:         Optional[str] = None
    supersedes_id: Optional[str] = None       # links correction to original
    id:            str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at:    datetime = field(default_factory=datetime.utcnow)
    is_deleted:    bool = False                # logical delete only — never physical

    def quality_weight(self) -> float:
        """
        Compute weight for baseline calculations.
        Flagged measurements receive reduced weight.
        Spec Section 7.2 — Quality Weighting.
        """
        weight = 1.0
        if QualityFlag.UNCERTAIN       in self.quality_flags: weight *= 0.6
        if QualityFlag.OUTLIER_SUSPECTED in self.quality_flags: weight *= 0.4
        if QualityFlag.SELF_REPORTED   in self.quality_flags: weight *= 0.85
        if QualityFlag.BATCH_ENTERED   in self.quality_flags: weight *= 0.75
        if QualityFlag.APPROXIMATE     in self.quality_flags: weight *= 0.70
        return max(weight, 0.1)   # floor weight — never zero


@dataclass
class Context:
    """
    Non-measurement contextual input (nutrition tags, lifestyle patterns).
    Spec Section 7.1 — Context entity.
    """
    user_id:    str
    timestamp:  datetime
    tags:       List[str]       # e.g. ["high_sugar_day", "late_night_eating"]
    notes:      Optional[str] = None
    id:         str = field(default_factory=lambda: str(uuid.uuid4()))


@dataclass
class DerivedFeature:
    """
    A computed value derived from measurements.
    Carries full provenance — window, method, count used.
    Spec Section 7.1 — DerivedFeature entity.
    """
    user_id:          str
    signal_id:        str
    feature_type:     str          # "rolling_median", "baseline_short", "baseline_long", "mad", "iqr"
    value:            float
    window_start:     datetime
    window_end:       datetime
    measurement_count: int
    method:           str          # description of computation method
    quality_weight_sum: float      # sum of weights used — for audit
    uncertainty:      UncertaintyLevel
    version:          int = 1
    id:               str = field(default_factory=lambda: str(uuid.uuid4()))
    computed_at:      datetime = field(default_factory=datetime.utcnow)


@dataclass
class Finding:
    """
    A detected change event.
    Spec Section 7.1 — Finding entity.
    Spec Section 9 — Change Detection.
    """
    user_id:          str
    signal_id:        str
    finding_type:     FindingType
    description:      str
    evidence_window_start: datetime
    evidence_window_end:   datetime
    confidence:       float        # 0.0 to 1.0
    uncertainty:      UncertaintyLevel
    supporting_measurement_ids: List[str] = field(default_factory=list)
    baseline_ref_id:  Optional[str] = None
    id:               str = field(default_factory=lambda: str(uuid.uuid4()))
    detected_at:      datetime = field(default_factory=datetime.utcnow)


@dataclass
class RiskFlag:
    """
    A non-diagnostic, conservative risk band summary.
    Must not label diseases. Describes domains of concern.
    Spec Section 7.1 — RiskFlag entity.
    Spec Section 10 — Risk Flagging.
    """
    user_id:         str
    domain:          str          # "cardiovascular", "metabolic", "behavioral"
    band:            RiskBand
    uncertainty:     UncertaintyLevel
    rationale:       str          # plain language explanation
    finding_ids:     List[str] = field(default_factory=list)
    id:              str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at:      datetime = field(default_factory=datetime.utcnow)


@dataclass
class Alert:
    """
    A user-visible safety message.
    URGENT alerts are non-suppressible.
    Spec Section 7.1 — Alert entity.
    Spec Section 13.3 — Alert Rules.
    """
    user_id:           str
    severity:          AlertSeverity
    title:             str
    message:           str
    safe_next_step:    str
    uncertainty:       UncertaintyLevel
    escalation_level:  Optional[EscalationLevel] = None
    acknowledged:      bool = False
    acknowledged_at:   Optional[datetime] = None
    suppressible:      bool = True     # URGENT alerts set this to False
    id:                str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at:        datetime = field(default_factory=datetime.utcnow)

    def __post_init__(self):
        # Enforce: URGENT alerts are never suppressible — Pillar 2
        if self.severity == AlertSeverity.URGENT:
            self.suppressible = False


@dataclass
class EscalationEvent:
    """
    Recorded event when safety thresholds are crossed.
    These records are preserved even if the triggering measurement is deleted.
    Spec Section 7.1 — EscalationEvent entity.
    """
    user_id:           str
    escalation_level:  EscalationLevel
    recommendation:    str
    evidence_summary:  str
    finding_ids:       List[str] = field(default_factory=list)
    alert_id:          Optional[str] = None
    acknowledged:      bool = False
    acknowledged_at:   Optional[datetime] = None
    id:                str = field(default_factory=lambda: str(uuid.uuid4()))
    triggered_at:      datetime = field(default_factory=datetime.utcnow)


@dataclass
class AuditEvent:
    """
    Immutable record of every significant system action.
    Append-only. Never modified. Hash-chained for tamper evidence.
    Spec Section 7.1 — AuditEvent entity.
    Spec Section 14 — Audit & Integrity.
    """
    event_type:    AuditEventType
    actor:         Actor
    entity_id:     str            # ID of the affected entity
    entity_type:   str            # "measurement", "alert", etc.
    reason_code:   Optional[str] = None
    details:       Optional[str] = None
    previous_hash: Optional[str] = None    # hash of prior AuditEvent for chain
    id:            str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp:     datetime = field(default_factory=datetime.utcnow)
    hash:          Optional[str] = None    # computed after creation


# ─── COLD START PROFILE ──────────────────────────────────────────────────────

@dataclass
class ColdStartProfile:
    """
    Structured intake for initializing health intelligence before longitudinal data.
    Spec Section 10 — Cold Start Profile (v0.1.1).

    All outputs from CSP are probabilistic priors only.
    No diagnostic labels permitted.
    Skipping inputs must not penalize the user.
    """
    user_id:           str
    age_range:         Optional[str] = None      # "30-40", "40-50", etc.
    height_cm:         Optional[float] = None
    sex_at_birth:      Optional[str] = None      # optional
    weight_kg:         Optional[float] = None
    waist_cm:          Optional[float] = None
    family_history:    List[str] = field(default_factory=list)  # ["cardiovascular", "diabetes"]
    known_conditions:  List[str] = field(default_factory=list)  # optional
    medications:       List[str] = field(default_factory=list)  # optional
    sleep_pattern:     Optional[str] = None      # "good", "poor", "variable"
    activity_level:    Optional[str] = None      # "sedentary", "moderate", "active"
    nutrition_pattern: Optional[str] = None
    stress_level:      Optional[int] = None      # 1–5
    prior_measurements: dict = field(default_factory=dict)  # signal_id → value
    health_goals:      List[str] = field(default_factory=list)  # optional
    id:                str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at:        datetime = field(default_factory=datetime.utcnow)

    def completeness_score(self) -> float:
        """
        Returns 0.0–1.0 indicating how complete the profile is.
        Used to calibrate initial uncertainty level.
        A low score does NOT penalize the user — it only informs uncertainty disclosure.
        """
        fields_present = sum([
            self.age_range is not None,
            self.height_cm is not None,
            self.weight_kg is not None,
            len(self.family_history) > 0,
            self.sleep_pattern is not None,
            self.activity_level is not None,
            self.stress_level is not None,
        ])
        return fields_present / 7.0


# ─── POPULATION REFERENCE ────────────────────────────────────────────────────

@dataclass(frozen=True)
class PopulationReference:
    """
    Population-level reference range for a signal.
    Used to contextualise personal baselines — not to override them.

    These ranges are:
      - Age/sex-stratified where clinically appropriate
      - Sourced from published clinical guidelines (cited in thresholds.py)
      - NEVER used to diagnose — only to provide context
      - Accompanied by explicit uncertainty and guideline debate notes

    Dual-reference architecture:
      Personal baseline  → detects change for THIS individual
      Population reference → contextualises WHERE the baseline sits
    Both run simultaneously. Neither replaces the other.
    """
    signal_id:       str
    age_range:       str          # e.g. "30-40", "all"
    sex:             str          # "male", "female", "all"
    normal_low:      float        # lower bound of typical range
    normal_high:     float        # upper bound of typical range
    concern_low:     Optional[float]   # below this = worth noting
    concern_high:    Optional[float]   # above this = worth noting
    unit:            str
    guideline_source: str         # e.g. "AHA 2023", "PLACEHOLDER"
    debate_note:     str = ""     # honest note if guidelines disagree
    placeholder:     bool = True  # must be False after clinical advisor sign-off


class BaselineContextStatus(str, Enum):
    """
    How the personal baseline sits relative to population reference.
    This is NOT a diagnosis — it is a position description.
    """
    WITHIN_RANGE      = "within_range"       # personal baseline within population normal
    BORDERLINE        = "borderline"         # near boundary — genuine clinical uncertainty
    OUTSIDE_RANGE     = "outside_range"      # personal baseline outside population normal
    INSUFFICIENT_DATA = "insufficient_data"  # not enough data to assess yet
    NOT_APPLICABLE    = "not_applicable"     # no population reference available


@dataclass
class BaselineContextNote:
    """
    A one-time, calm, informational note surfaced when a personal baseline
    is established and contextualised against population reference ranges.

    KEY DESIGN RULES (alert fatigue prevention):
      - Generated ONCE when baseline first matures past MVL threshold
      - Requires user acknowledgment — then goes DORMANT
      - Does NOT re-surface unless the baseline shifts materially
      - Is NOT an escalation — does not trigger safety engine
      - Language is calm, informational, non-diagnostic

    Addresses the 'unhealthy baseline' problem:
      A user whose personal normal is itself outside population norms
      needs to know this — once, calmly — not repeatedly alarmed about it.
    """
    user_id:          str
    signal_id:        str
    signal_name:      str
    personal_baseline: float
    personal_baseline_unit: str
    population_normal_low:  float
    population_normal_high: float
    status:           BaselineContextStatus
    context_message:  str     # calm, non-diagnostic explanation
    guideline_source: str
    debate_note:      str     # honest disclosure of guideline uncertainty
    acknowledged:     bool = False
    acknowledged_at:  Optional[datetime] = None
    dormant:          bool = False    # True after acknowledgment — won't re-surface
    id:               str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at:       datetime = field(default_factory=datetime.utcnow)


# ─── DIGITAL TWIN PHASE ──────────────────────────────────────────────────────

class DigitalTwinPhase(str, Enum):
    """
    The current capability phase of the user's digital twin.
    The twin exists from Day 1 and grows in capability as data accumulates.
    This is not a product feature — it is the kernel's self-description
    of how well it currently knows this individual.

    Phase 1 — Personal Record:     data is being collected, twin is forming
    Phase 2 — Baseline Model:      personal baselines established (MVL met)
    Phase 3 — Trajectory Model:    drift and change detection active
    Phase 4 — Correlation Model:   cross-signal relationships emerging (future)
    Phase 5 — Simulation Model:    trajectory projection possible (future)
    """
    PHASE_1_PERSONAL_RECORD  = "phase_1_personal_record"
    PHASE_2_BASELINE_MODEL   = "phase_2_baseline_model"
    PHASE_3_TRAJECTORY_MODEL = "phase_3_trajectory_model"
    PHASE_4_CORRELATION      = "phase_4_correlation"      # reserved
    PHASE_5_SIMULATION       = "phase_5_simulation"       # reserved


@dataclass
class DigitalTwinStatus:
    """
    A summary of the user's current digital twin state across all signals.
    Surfaced to the user as transparent progress — not a score or grade.
    """
    user_id:            str
    overall_phase:      DigitalTwinPhase
    signals_in_phase:   Dict[str, DigitalTwinPhase]  # signal_id → phase
    maturity_message:   str    # honest plain-language description of current state
    generated_at:       datetime = field(default_factory=datetime.utcnow)
