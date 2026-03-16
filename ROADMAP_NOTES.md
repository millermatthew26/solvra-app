# Solvra — Product Roadmap Notes
## Founder Observations & Feature Concepts for Future Phases

This file captures feature ideas, founder observations, and product decisions
that are intentionally deferred from Phase 1. Nothing here is lost — these are
the right ideas at the wrong time. Each entry includes the reasoning for deferral
and what needs to be true before it can be built correctly.

---

## PHASE 2 FEATURES

---

### Child Profiles & Multi-User Account Structure

**Origin:** Founder observation — a morbidly obese patient being tracked by
their PCP, or a parent wanting to create a health profile for their child,
both require a profile model that the current system does not support.

**The Concept:**
Allow a parent or guardian to create and manage child health profiles within
their Solvra account. The system should:

- Ask at profile creation: "Is this profile for you or for someone in your care?"
- If for a child, collect the child's age and adjust the signal set accordingly
- Suppress irrelevant signals based on age (e.g. no fasting glucose, waist
  circumference, HRV, or habit variables for young children)
- Surface age-appropriate signals instead (height, weight-for-age percentile,
  sleep duration appropriate for age group)
- Use pediatric population reference ranges — these are age-banded in narrow
  increments and are completely different from adult norms
- Position the parent as the data custodian with a defined age of autonomy
  at which the profile transitions to the individual's own control
- Language and explanations should be written for a parent reading about
  their child, not for the individual themselves

**Age-banded signal suppression (approximate):**

| Age Range    | Suppress                                        | Add / Keep                          |
|-------------|--------------------------------------------------|--------------------------------------|
| 0–5 years   | BP, glucose, waist, HRV, habits, stress         | Weight, sleep, activity, height      |
| 6–11 years  | Glucose, HRV, habits (smoking/alcohol), waist   | BP, weight, sleep, activity, height  |
| 12–17 years | HRV (unless wearable), glucose (unless diabetic)| Most signals, age-adjusted ranges   |
| 18+         | None — full signal set                          | All signals                          |

**Why deferred to Phase 2:**
- Requires authentication and multi-profile account structure (not yet built)
- Requires pediatric clinical reference ranges (clinical advisor sign-off needed)
- Requires age-aware explanation generator language
- COPPA compliance required if collecting data on users under 13
- Requires data model changes: profile type, age, custodian relationship,
  age-of-autonomy transition logic

**What needs to be true before building:**
1. Authentication system in place (Supabase Auth)
2. Clinical advisor has reviewed and signed off on pediatric reference ranges
3. Regulatory counsel has reviewed COPPA obligations
4. Explanation generator supports parent-facing output mode
5. Data model supports multiple profiles under one account

---

### Lab Results Tab

**Origin:** Founder observation — fasting glucose is already in the system
as an optional field requiring a lab or glucometer. A dedicated lab results
tab would allow users to log periodic bloodwork in a structured way.

**The Concept:**
A separate tab clearly labeled as periodic rather than regular input.
Designed around the natural cadence of annual bloodwork — not daily logging.

Signals to include (pending clinical advisor sign-off on reference ranges):
- Fasting glucose (already in system — move here or duplicate)
- HbA1c (3-month glucose average — stronger metabolic signal than single glucose)
- Total cholesterol, LDL, HDL, triglycerides (lipid panel)
- TSH (thyroid — increasingly common in preventive panels)
- Vitamin D (very common deficiency, tracked longitudinally)
- Iron / ferritin (fatigue correlation)
- eGFR / creatinine (kidney function — relevant for longitudinal tracking)
- CRP / hs-CRP (inflammation marker — emerging preventive signal)

**UX design notes:**
- Date of test is required (not today's date by default — lab results are often
  entered days or weeks after the test)
- Lab name / ordering physician optional but useful for provenance
- Reference range from the lab report should be capturable alongside the value
- Uncertainty disclosure: lab results are point-in-time snapshots, not daily signals
- The system should surface trends across lab visits over months and years —
  this is where longitudinal lab tracking becomes genuinely powerful

**Why deferred:**
- Clinical advisor must define safe language for lab value interpretation
- Reference ranges for lab values require more careful clinical governance
  than wearable signals — the diagnostic stakes are higher
- Should not be built until Phase 1 signal set is stable and tested

---

### Structured Context Tags (Notes Enhancement)

**Origin:** Notes field currently stores free text that the kernel does not
analyze. The right evolution is structured context tags the kernel can use.

**The Concept:**
Replace or augment the free-text notes field with selectable context tags
that the kernel can factor into quality weighting and explanation generation.

Example tag categories:
- Physical context: after exercise, feeling ill, injured, sore
- Sleep context: poor sleep, late night, napped, jet-lagged
- Food context: fasted, ate late, heavy meal, alcohol, skipped meals
- Emotional context: high stress, anxious, calm, grieving, excited
- Life events: travel, major life change, work deadline, family event
- Medication context: started new medication, missed dose, changed dosage

**Why this matters:**
A blood pressure reading of 145 tagged "just exercised, high stress day"
carries different weight than the same reading tagged "rested, normal day."
Structured tags allow the kernel to apply quality adjustments and produce
more accurate baseline calculations and explanations.

**Why deferred:**
- Requires kernel update to ingestion service (context tag processing)
- Requires clinical advisor input on how tags should affect quality weighting
- Free text notes preserved in the meantime for user value

---

### Correlation Engine (Digital Twin Phase 4)

**Origin:** Core architecture — defined in the Digital Twin Framework document
and the Final Governing Strategy.

**The Concept:**
Cross-signal statistical relationship modeling specific to the individual.
The system identifies correlations in the user's own longitudinal data —
e.g. sleep quality correlating with next-day blood pressure, stress level
correlating with HRV, activity minutes correlating with energy level.

**Prerequisites before building:**
- Minimum 6–12 months of consistent longitudinal data per user
- Clinical advisor review of correlation output language
- Minimum data threshold enforcement before any correlation is surfaced
- Uncertainty disclosure framework for correlation outputs
- False positive rate testing — spurious correlations are a real risk
  with small personal datasets

**Why deferred:**
Phase 4 of the digital twin. Requires data depth that Phase 1 users
will not have for months. Build the foundation now. Build this later.

---

## DESIGN NOTES (For When Design Phase Begins)

- Welcome screen currently uses Streamlit HTML — should be rebuilt in React
  with proper animation, typography, and visual hierarchy
- Signal input form should eventually support voice input for accessibility
- Mobile-first redesign needed before founding cohort launch
- Dark mode support should be optional, not default
- Export should produce a designed PDF summary, not just raw JSON

---

## NOTES ON NAMING & LANGUAGE

- "Digital twin" is the internal architectural term. User-facing language
  should use "your health picture" or "your personal baseline" in early phases
  and introduce "your health model" or "your twin" gradually as capability grows
- Never use "diagnose," "treat," "medical advice," or "disease" in any output
- "Companion" framing approved for notes and onboarding language
- Uncertainty language must always be present — never suppress confidence levels

---

*This file is maintained by the founder and updated as new observations arise.
It is not a commitment — it is a memory. Review it when scoping Phase 2.*
