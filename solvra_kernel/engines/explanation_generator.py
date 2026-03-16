"""
Solvra Kernel — Explanation Generator
=======================================
Produces plain-language user-facing interpretations of kernel findings.
Spec Section 22 — Explanation Generator.
Spec Appendix A — Regulatory-Safe Language Rules (Section 25).

All outputs follow the mandatory five-section template:
  1. What changed (objective)
  2. Why it might matter (contextual)
  3. How confident we are (uncertainty + reasons)
  4. What information is missing (actionable)
  5. Safest next step

NEVER produces:
  - Disease labels (hypertension, diabetes, etc.)
  - Treatment directives
  - False certainty
  - Engagement-driving urgency language
"""

from dataclasses import dataclass
from typing import List, Optional, Dict

from solvra_kernel.models.entities import (
    Finding, RiskFlag, DerivedFeature, UncertaintyLevel,
    FindingType, RiskBand, SIGNAL_DEFINITIONS
)


@dataclass
class Explanation:
    """Structured output of the Explanation Generator."""
    signal_id:           str
    signal_name:         str
    what_changed:        str    # Section 1 — objective
    why_it_might_matter: str    # Section 2 — contextual, non-diagnostic
    confidence_statement: str   # Section 3 — uncertainty label + reasons
    what_is_missing:     str    # Section 4 — actionable data gaps
    safest_next_step:    str    # Section 5 — monitor / confirm / seek evaluation
    uncertainty:         UncertaintyLevel
    risk_band:           Optional[RiskBand] = None
    full_text:           str = ""   # assembled narrative

    def __post_init__(self):
        self.full_text = self._assemble()

    def _assemble(self) -> str:
        return (
            f"WHAT CHANGED\n{self.what_changed}\n\n"
            f"WHY IT MIGHT MATTER\n{self.why_it_might_matter}\n\n"
            f"HOW CONFIDENT WE ARE\n{self.confidence_statement}\n\n"
            f"WHAT WOULD HELP\n{self.what_is_missing}\n\n"
            f"SAFEST NEXT STEP\n{self.safest_next_step}"
        )


class ExplanationGenerator:

    def generate(
        self,
        user_id:        str,
        signal_id:      str,
        findings:       List[Finding],
        short_baseline: Optional[DerivedFeature],
        long_baseline:  Optional[DerivedFeature],
        risk_flag:      Optional[RiskFlag],
        mvl_status:     Dict,
    ) -> Explanation:
        """
        Generate a complete five-section explanation for a signal's current state.
        If no findings, generates a 'no significant change' explanation with appropriate uncertainty.
        """
        sig = SIGNAL_DEFINITIONS.get(signal_id)
        sig_name = sig.name if sig else signal_id.replace("_", " ").title()

        # Determine dominant finding (most clinically significant)
        dominant = self._dominant_finding(findings)
        uncertainty = self._resolve_uncertainty(short_baseline, long_baseline, findings)

        what_changed     = self._build_what_changed(sig_name, dominant, short_baseline, long_baseline)
        why_it_matters   = self._build_why_it_matters(sig_name, signal_id, dominant, risk_flag)
        confidence_stmt  = self._build_confidence_statement(uncertainty, short_baseline, findings, mvl_status)
        what_is_missing  = self._build_what_is_missing(signal_id, mvl_status, short_baseline, findings)
        safest_next_step = self._build_next_step(dominant, risk_flag, uncertainty)

        return Explanation(
            signal_id            = signal_id,
            signal_name          = sig_name,
            what_changed         = what_changed,
            why_it_might_matter  = why_it_matters,
            confidence_statement = confidence_stmt,
            what_is_missing      = what_is_missing,
            safest_next_step     = safest_next_step,
            uncertainty          = uncertainty,
            risk_band            = risk_flag.band if risk_flag else None,
        )

    # ── SECTION BUILDERS ──────────────────────────────────────────────────────

    def _build_what_changed(
        self,
        sig_name:       str,
        dominant:       Optional[Finding],
        short_baseline: Optional[DerivedFeature],
        long_baseline:  Optional[DerivedFeature],
    ) -> str:
        if dominant is None:
            if short_baseline:
                return (
                    f"Your {sig_name} readings have been relatively stable. "
                    f"Your recent average is {short_baseline.value:.1f} {short_baseline.signal_id and SIGNAL_DEFINITIONS.get(short_baseline.signal_id, type('',(),{'unit':''})()).unit}."
                )
            return f"Solvra does not yet have enough {sig_name} readings to identify a pattern."

        if dominant.finding_type == FindingType.SPIKE:
            return dominant.description

        if dominant.finding_type == FindingType.SUSTAINED_DRIFT:
            return dominant.description

        if dominant.finding_type == FindingType.VOLATILITY_SHIFT:
            return dominant.description

        if dominant.finding_type == FindingType.COVERAGE_RISK:
            return dominant.description

        return dominant.description

    def _build_why_it_matters(
        self,
        sig_name:  str,
        signal_id: str,
        dominant:  Optional[Finding],
        risk_flag: Optional[RiskFlag],
    ) -> str:
        # Contextual explanation — never disease labels, never diagnostic
        context_map = {
            "bp_systolic":   "Blood pressure patterns over time are one of several signals that can give you a more complete picture of cardiovascular health. Changes in your pattern — not any single reading — are what Solvra watches for.",
            "bp_diastolic":  "Diastolic pressure reflects what happens between heartbeats. Like systolic pressure, sustained patterns matter more than individual readings.",
            "heart_rate":    "Resting heart rate trends can reflect changes in fitness, recovery, stress, or other factors. Context matters greatly in interpreting these patterns.",
            "weight":        "Gradual weight trend changes over weeks, rather than daily fluctuations, are more meaningful. Daily weight is influenced by hydration, meals, and other factors that are entirely normal.",
            "sleep_hours":   "Sleep duration is one input into a broader picture of how rest may be affecting how you feel and function. Solvra looks at patterns rather than individual nights.",
            "sleep_quality": "Subjective sleep quality, while not a clinical measure, can reflect important patterns over time when combined with other signals.",
            "activity_mins": "Activity patterns over weeks and months, rather than single days, tend to be the more meaningful signal for understanding your lifestyle trends.",
            "stress_level":  "Stress patterns over time can interact with other health signals. Solvra looks for sustained patterns, not day-to-day variation which is entirely normal.",
            "glucose":       "Fasting glucose readings, when tracked over time, can show trends that are worth discussing with a healthcare provider in the context of your full health picture.",
        }

        base = context_map.get(signal_id, f"Changes in your {sig_name} pattern may be worth understanding in the context of your overall health picture.")

        if dominant and dominant.finding_type == FindingType.COVERAGE_RISK:
            return f"Without recent {sig_name} readings, Solvra cannot give you a current picture. Previous insights may not reflect where things stand today."

        if risk_flag and risk_flag.band in (RiskBand.ELEVATED_CONCERN, RiskBand.HIGH_CONCERN):
            return base + " The pattern Solvra has detected suggests it may be worth bringing to a healthcare provider's attention."

        return base

    def _build_confidence_statement(
        self,
        uncertainty:    UncertaintyLevel,
        short_baseline: Optional[DerivedFeature],
        findings:       List[Finding],
        mvl_status:     Dict,
    ) -> str:
        # Transparency about uncertainty — Pillar 3
        base_statements = {
            UncertaintyLevel.HIGH: (
                "Solvra's confidence in this interpretation is limited. "
                "There is not yet enough data to give you a clear, reliable picture for this signal."
            ),
            UncertaintyLevel.MEDIUM: (
                "Solvra has moderate confidence in this interpretation. "
                "The pattern is present in your data, but more readings over more time would strengthen the picture."
            ),
            UncertaintyLevel.LOW: (
                "Solvra has good confidence in this interpretation, based on a consistent pattern "
                "across multiple readings over an adequate time window."
            ),
        }

        stmt = base_statements[uncertainty]

        if short_baseline:
            stmt += f" This is based on {short_baseline.measurement_count} readings spanning {(short_baseline.window_end - short_baseline.window_start).days} days."

        if mvl_status.get("applicable") and not mvl_status.get("threshold_met"):
            have, need = mvl_status.get("readings_have", 0), mvl_status.get("readings_needed", 0)
            stmt += f" Adding more readings ({have} of {need} minimum reached) will meaningfully improve Solvra's picture."

        return stmt

    def _build_what_is_missing(
        self,
        signal_id:  str,
        mvl_status: Dict,
        baseline:   Optional[DerivedFeature],
        findings:   List[Finding],
    ) -> str:
        gaps = []

        if mvl_status.get("applicable") and not mvl_status.get("threshold_met"):
            readings_gap = mvl_status.get("readings_needed", 0) - mvl_status.get("readings_have", 0)
            days_gap     = mvl_status.get("days_needed", 0) - mvl_status.get("days_have", 0)
            if readings_gap > 0:
                gaps.append(f"about {readings_gap} more readings")
            if days_gap > 0:
                gaps.append(f"readings spread over {days_gap} more days")

        if any(f.finding_type == FindingType.VOLATILITY_SHIFT for f in findings):
            gaps.append("more consistent measurement timing and conditions")

        if any(f.finding_type == FindingType.COVERAGE_RISK for f in findings):
            gaps.append("a recent reading to restore currency")

        if not gaps:
            return "No specific data gaps for this signal at this time. Continuing regular readings will keep the picture current."

        return "To reduce uncertainty, Solvra would benefit from: " + ", and ".join(gaps) + ". None of these are required — Solvra works with what you provide."

    def _build_next_step(
        self,
        dominant:  Optional[Finding],
        risk_flag: Optional[RiskFlag],
        uncertainty: UncertaintyLevel,
    ) -> str:
        if risk_flag:
            if risk_flag.band == RiskBand.HIGH_CONCERN:
                return "Schedule a timely conversation with your healthcare provider and share this report."
            if risk_flag.band == RiskBand.ELEVATED_CONCERN:
                return "Consider discussing this pattern with your healthcare provider at your next visit."
            if risk_flag.band == RiskBand.MONITOR:
                return "Continue monitoring. If the pattern continues or worsens, discuss it with your healthcare provider."

        if dominant and dominant.finding_type == FindingType.SPIKE:
            return "Take a follow-up reading to confirm. A single reading can reflect many factors. If the reading repeats, discuss with your doctor."

        if dominant and dominant.finding_type == FindingType.COVERAGE_RISK:
            return "Take a new reading when you are able. No urgency implied — just to restore Solvra's current picture."

        if uncertainty == UncertaintyLevel.HIGH:
            return "Continue logging readings. Solvra will give you a clearer picture as more data accumulates."

        return "Continue your regular monitoring. No specific action indicated at this time."

    # ── HELPERS ───────────────────────────────────────────────────────────────

    def _dominant_finding(self, findings: List[Finding]) -> Optional[Finding]:
        """Return the most significant finding by type priority."""
        priority = [FindingType.SUSTAINED_DRIFT, FindingType.SPIKE, FindingType.VOLATILITY_SHIFT, FindingType.COVERAGE_RISK]
        for p in priority:
            match = next((f for f in findings if f.finding_type == p), None)
            if match:
                return match
        return None

    def _resolve_uncertainty(
        self,
        short_baseline: Optional[DerivedFeature],
        long_baseline:  Optional[DerivedFeature],
        findings:       List[Finding],
    ) -> UncertaintyLevel:
        if short_baseline is None:
            return UncertaintyLevel.HIGH

        levels = [b.uncertainty for b in [short_baseline, long_baseline] if b is not None]
        # If any finding has high uncertainty, elevate
        if any(f.uncertainty == UncertaintyLevel.HIGH for f in findings):
            levels.append(UncertaintyLevel.HIGH)

        order = [UncertaintyLevel.HIGH, UncertaintyLevel.MEDIUM, UncertaintyLevel.LOW]
        return min(levels, key=lambda l: order.index(l))
