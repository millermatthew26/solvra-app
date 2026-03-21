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

---

## PHASE 3–4 FEATURES

---

### Scientific Knowledge Base — Evidence-Grounded Intelligence Layer

**Origin:** Security advisor observation (February 2026) — Solvra should
download and store relevant scientific journals and publications to learn
users faster based on scientific evidence, surfacing insights that clinicians
may not think to discuss during initial patient conversations.

**Why the idea is right:**
The gap between what clinical science knows and what reaches routine patient
care averages 17 years. A patient's longitudinal data becomes dramatically
more powerful when cross-referenced against current peer-reviewed evidence.
Solvra can surface connections — e.g. declining HRV correlating with early
autonomic dysfunction patterns documented in the literature — that a
15-minute appointment would almost never produce.

**The correct technical approach — Retrieval-Augmented Generation (RAG):**
Rather than downloading and storing raw journal content (which faces
licensing, volume, and quality-weighting problems), Solvra builds a curated,
indexed knowledge base of the most clinically relevant findings, organized
by signal domain, evidence quality tier, and recency — and queries it
dynamically when generating explanations and context notes.

**Primary data source:**
PubMed Central (PMC) — the NIH's free full-text archive of over 9 million
peer-reviewed articles, freely accessible via public API. No licensing cost.
Highest-quality, most clinically relevant scientific literature database
in existence. This is the anchor source.

Secondary sources to evaluate:
- ClinicalTrials.gov (registered trial outcomes)
- Cochrane Library (systematic reviews — highest evidence tier)
- CDC and NIH clinical guidelines
- WHO technical reports
- Preprint servers (medRxiv, bioRxiv) — lower evidence tier, clearly labeled

**Architecture design:**

1. Knowledge Indexer (background service):
   - Queries PMC API on a defined update cadence (weekly or monthly)
   - Filters by signal-relevant MeSH terms (blood pressure, HRV, sleep,
     metabolic syndrome, etc.)
   - Assigns evidence tier based on study type:
     - Tier 1: Systematic reviews, meta-analyses, clinical guidelines
     - Tier 2: RCTs with >500 participants
     - Tier 3: Observational studies, cohort studies
     - Tier 4: Single small studies, case reports (used with caution only)
   - Indexes findings by signal domain, population characteristics,
     recency, and citation count
   - Clinical advisor reviews and approves new evidence domains before
     they influence patient-facing outputs

2. Evidence Query Engine:
   - When the explanation generator produces an output, it queries the
     knowledge base for relevant evidence in that signal domain
   - Returns the highest-tier, most recent, most relevant evidence
     that supports or contextualizes the pattern being explained
   - Handles conflicting evidence honestly — if studies disagree,
     the output discloses the disagreement rather than cherry-picking

3. Evidence-Enhanced Explanation Generator:
   - Default output stays plain and clean — no evidence citations in the
     primary explanation. Consumer-facing language remains: "Research supports
     a connection between this pattern and cardiovascular health. Mention it
     to your doctor." Simple. Trusted. Actionable.
   - Optional expandable detail layer — a small "See the evidence" or
     "Learn more" element the user can tap if they want to go deeper.
     This layer shows: study type, sample size, year, key finding, and
     a link to the source. Serves the curious minority without burdening
     the majority who just want the signal and the next step.
   - Evidence tier governs the default language confidence only:
     - Tier 1: "Research consistently shows..."
     - Tier 2: "Research supports..."
     - Tier 3: "Some research suggests..."
     - Tier 4: Not used in patient-facing outputs without clinical advisor approval
   - The expansion layer is clearly labeled as supplementary scientific
     context — not a Solvra clinical claim. This separation reduces
     regulatory risk while preserving the evidence layer for those who want it.
   - Secondary clinical value: when a user brings their Solvra export to
     a clinical appointment and the physician asks "what is this based on,"
     the patient can open the detail layer and show the specific peer-reviewed
     evidence. That is a fundamentally different clinical conversation than
     "my app told me."
   - All evidence citations are logged in the Evidence Ledger with the
     output that referenced them — full provenance regardless of whether
     the user expanded the detail layer or not

4. Evidence Ledger Extension:
   - Each Evidence Ledger entry that references scientific literature
     includes: PMC ID, evidence tier, study characteristics, retrieval date
   - This means every patient-facing claim that references science can
     be traced to the specific study that supported it
   - Retracted studies are automatically flagged and removed from the
     knowledge base on the next update cycle

**Governance requirements before building:**
- Clinical advisor defines admissible evidence tiers per signal domain
- Clinical advisor reviews and approves the evidence quality weighting logic
- Knowledge Governance Framework document created (see below)
- Retraction monitoring process in place (Retraction Watch API or equivalent)
- Update cadence and staleness policy defined (e.g. findings >10 years old
  require clinical advisor review before continued use)
- Language rules for citing conflicting evidence documented

**The Knowledge Governance Framework document:**
A dedicated governance document should be created alongside the clinical
advisor covering:
- Evidence tier definitions and weighting
- Admissible sources by signal domain
- Update cadence and staleness policy
- Retraction monitoring and removal process
- Language rules for evidence citation in patient-facing outputs
- Clinical advisor sign-off process for new evidence domains
- How conflicting evidence is handled and disclosed

**Why this is a significant differentiator:**
Most health apps that cite "research" do so loosely and without transparency
about evidence quality. Solvra's architecture cites the specific study,
discloses the evidence tier, acknowledges when the science is contested, and
logs the evidence reference in the audit chain. This is the same honest,
uncertainty-aware communication standard that governs every other kernel
output — applied to the scientific evidence layer.

For institutional buyers — health systems, DPC networks, RPM vendors — the
ability to say that Solvra's explanations are grounded in peer-reviewed
evidence with disclosed quality tiers is a significant clinical credibility
and compliance asset.

**Why deferred to Phase 3–4:**
- Adds complexity without proportionate benefit at Phase 1
- Requires the explanation generator to be mature and stable first
- Requires clinical advisor to be in place and governing the evidence tiers
- The correlation engine (Phase 4) is where scientific literature
  cross-referencing becomes most powerful — personal correlations
  validated against population-level research findings
- Foundational data infrastructure must be solid before adding the
  knowledge layer on top

**What needs to be true before building:**
1. Clinical advisor in place and governing evidence quality standards
2. Explanation generator stable and tested with real founding cohort data
3. Knowledge Governance Framework document completed and signed
4. PMC API integration prototyped and rate limits understood
5. Retraction monitoring process defined
6. Evidence Ledger extended to support citation provenance
7. Correlation engine (Phase 4) design finalized — the two features
   should be designed together as complementary capabilities

---

---

## PHASE 3–4 FEATURES (CONTINUED)

---

### Dual-Output Architecture — Consumer Mode and Clinical Mode

**Origin:** Founder observation (February 2026) — Solvra needs a clinically
oriented output layer that health systems like Epic can integrate with,
giving clinicians a robust, clinical-ready view of their patient's Solvra
data with patient permission via a controlled access token.

**The Core Insight:**
This is not two separate products. It is one intelligence system — the same
kernel, the same Evidence Ledger, the same safety architecture — with two
output modes governed by who is asking and what permission they have.
The kernel produces the intelligence once. The rendering layer and access
scope determine how it is presented.

**Consumer Mode (already built):**
- Warm, plain language, five-section explanations
- Progressive disclosure — detail available on tap
- Companion framing, uncertainty in approachable terms
- Designed for general health literacy
- Example: "Your blood pressure has been trending higher than your personal
  normal for the past six weeks. This is worth mentioning to your doctor."

**Clinical Mode (Phase 3–4):**
- Structured, precise, evidence-referenced outputs
- FHIR-formatted observation bundles
- Full confidence intervals, quality weights, audit chain references
- Designed for clinical workflow integration
- Example: "Patient baseline 118/74 mmHg established over 94 days,
  47 readings, quality weight 0.89. Short-window baseline (30-day)
  currently 131/82 mmHg. Sustained drift finding: 11.0% systolic
  deviation from long-window baseline over 38 days, confidence 0.81,
  uncertainty level medium. Audit reference: EVL-2026-0847."

**The Access Model — Patient-Controlled Authorization Token:**
The patient logs into Solvra and generates a time-limited or scope-limited
access token. They share it with their provider or health system. The
provider uses that token to pull the clinical-grade output layer for that
patient. The patient can revoke it at any time. No token, no access.
This is the patient-permission model the founder described — structurally
identical to how SMART on FHIR works, which Epic already supports.

Token scope options:
- Read-only access to structured output bundle (most common)
- Time-limited: expires after 30, 60, or 90 days
- Signal-scoped: provider can request access to specific signals only
  (e.g. cardiovascular signals only for a cardiologist)
- Full history vs. recent window (e.g. last 90 days only)
- Revocable at any time by the patient with immediate effect

**Epic Integration Path:**
Epic supports SMART on FHIR — a standardized API framework allowing
third-party applications to connect to Epic's ecosystem with patient
authorization. Two integration paths:

Path A (near-term, Phase 3): Patient-initiated. Patient generates a
Solvra token, provider receives a FHIR-formatted Solvra output bundle
that imports into Epic as a structured document. No Epic certification
required. Works with any FHIR-compatible EHR.

Path B (long-term, Phase 4+): Epic App Orchard certification — formal
deep integration with Epic's ecosystem. Requires compliance documentation,
testing, and Epic review process. Significant milestone. Deferred until
founding cohort data validates output quality and clinical advisor has
signed off on FHIR output formats.

**Revenue connection:**
The clinical output layer — the Trust API — is the IaaS revenue stream
made concrete. Consumer layer = individual subscription revenue.
Clinical layer = institutional partner revenue. Same kernel. Two audiences.
Two revenue streams. One architecture.

**FHIR Output Resources to support (Phase 3):**
- Observation: longitudinal measurements with timestamps and quality flags
- DiagnosticReport: findings and pattern detections with evidence references
- RiskAssessment: safety engine outputs with escalation levels
- Patient: demographic context (age range, relevant profile data)
- Provenance: Evidence Ledger references for every output resource

**Governance requirements before building:**
- Clinical advisor reviews and approves FHIR output format and field mapping
- Legal counsel reviews patient-controlled token terms and liability scope
- HIPAA Business Associate Agreement framework defined for clinical partners
- Regulatory counsel reviews whether clinical output layer triggers SaMD
  classification under FDA PCCP guidance
- Token revocation architecture tested before any clinical partner goes live

**What needs to be true before building:**
1. Consumer output layer stable and validated with founding cohort
2. Clinical advisor in place and governing output language
3. FastAPI backend production-ready with authentication
4. FHIR output format reviewed by clinical advisor and regulatory counsel
5. Patient-controlled token system designed and security-reviewed
6. At least one clinical partner identified and willing to pilot Path A

---


### Per-Signal Timestamping (Log Data Enhancement)

**Origin:** Founder observation — a single date field for a multi-signal log
entry is a false solution. Blood pressure may have been taken yesterday,
a lab result may be from four days ago, and sleep was last night. One date
field implies all measurements were taken simultaneously which is rarely true.

**Current state:** Auto-timestamp at time of saving. Clean and honest for
the proof of concept stage.

**The right solution (Phase 2):**
Each signal should have its own optional "when was this actually taken"
field — collapsed by default, expandable per signal. A user logging blood
pressure can optionally set it to yesterday. A user entering a glucose
result can set it to the lab date four days ago. All other signals default
to now.

This requires a per-signal UX pattern rather than a single date field at
the top of the form. The design challenge is making it accessible without
cluttering the primary logging experience.

**Why deferred:** The UX problem needs a clean solution before building.
A collapsed optional timestamp per signal row is the most likely approach
but needs to be designed and tested with real users first.

---

### Persisted User Profile — Age, Sex, Device Source, Measurement Quality

**Origin:** ChatGPT stress test (March 2026) — age is currently session-only
in the prototype. A durable user profile that persists across sessions is
required before any real user data is collected.

**The Concept:**
A lightweight user profile stored in Supabase alongside measurements:
- Age (currently collected per-session, needs to persist)
- Biological sex (affects reference ranges for multiple signals)
- Primary device sources (wearable, home cuff, glucometer, manual)
- Measurement quality context (which signals are measured vs estimated)
- Cold start profile completion status

**Why it matters:**
Without a persisted user profile, the kernel cannot apply age-adjusted or
sex-adjusted reference ranges consistently across sessions. Every session
currently starts from scratch. This directly undermines the longitudinal
integrity the system depends on.

**What needs to be true before building:**
1. Supabase Auth in place — user identity must be stable across sessions
2. User profile schema defined and approved by clinical advisor
3. HIPAA posture clarified for what profile data constitutes PHI

**Why deferred:**
Requires auth system which requires HIPAA and security review first.
Demographic data — especially age and sex — may constitute PHI depending
on context. Do not build this until the legal and security framework is clear.

---

### Per-Signal Save — Partial Logging UX

**Origin:** ChatGPT stress test (March 2026) and founder observation.
Mass-saving all signals in one batch encourages false completeness.
Users rarely have all signals measured at the same time.

**Current state:** Save button skips None values — only measured signals
are saved. This is the correct interim behavior.

**The right solution (Phase 2):**
Each signal category (Cardiovascular, Body, Sleep, etc) should have its
own save button. A user who only took blood pressure today saves only
the Cardiovascular section. A user who only slept and wants to rate it
saves only the Sleep section.

This requires:
- Per-category save buttons in the Log Data UI
- Kernel ingestion handles partial signal sets gracefully (already does)
- UX design that makes partial logging feel natural, not incomplete
- Progress indicator showing which categories have been logged today

**Why deferred:**
Requires UX redesign of the Log Data page. The interim solution
(skip None values on save) is sufficient for the proof of concept stage.

---

### Habits Feeding Interpretation — Lifestyle Context Integration

**Origin:** ChatGPT stress test (March 2026) — habits currently sit beside
the analytical engine rather than feeding into it.

**The Concept:**
Habit data should materially affect how the kernel interprets signals:
- A resting heart rate of 80 means something different for someone who
  smokes versus someone who exercises daily
- Sleep quality context should affect how HRV drift is interpreted
- Caffeine intake should affect blood pressure interpretation
- Night shift work should affect all circadian-dependent signals

**Phase 3-4 implementation:**
- Habit profile becomes an input to the baseline engine
- Context tags from habits feed quality weighting in ingestion
- Correlation engine links habit changes to signal changes over time
- Explanation generator references habit context in plain-language output

**Why deferred:**
Requires correlation engine (Phase 4) and a richer ingestion context
model. The habit data being collected now is the right foundation —
it just is not yet wired into interpretation.

---

### UI/Kernel Interface Discipline — Engineering Note for Incoming Engineer

**Origin:** ChatGPT stress test (March 2026) — the app layer was
directly mutating kernel internal storage via kernel.ingestion._store
in load_measurements_into_kernel(). This is a code smell that creates
fragility at scale.

**The principle:**
The UI layer should never access kernel internals directly. All
communication between the app and the kernel should go through
documented public methods on the kernel interface.

**Current state:** The direct _store access remains in
load_measurements_into_kernel() as a known shortcut for the prototype.

**What needs to change before production:**
- Kernel exposes a public load_from_store(user_id, measurements) method
- App calls that method rather than mutating _store directly
- All kernel methods the app uses are documented in the kernel interface
- Any new kernel capability is exposed via public method, never via
  internal attribute access from the UI layer

**Why it matters:**
Once a second engineer joins, undocumented internal access becomes
invisible technical debt. The incoming kernel engineer should be briefed
on this pattern and tasked with creating the clean interface boundary
as one of their first contributions.

---
## DESIGN NOTES (For When Design Phase Begins)

- Welcome screen currently uses Streamlit HTML — should be rebuilt in React
  with proper animation, typography, and visual hierarchy
- Signal input form should eventually support voice input for accessibility
- Mobile-first redesign needed before founding cohort launch
- Dark mode support should be optional, not default
- Export should produce a designed PDF summary, not just raw JSON
- Evidence layer uses progressive disclosure — default output is always
  plain and clean, expandable detail layer available on tap for users
  who want to go deeper. This principle applies broadly: never show
  everything Solvra knows in the primary view. Surface the signal.
  Let the curious dig deeper. Protect the majority from information overload
  while serving the minority who want full context.
- The "See the evidence" expansion pattern should be consistent across
  all explanation outputs — one interaction model the user learns once
  and applies everywhere

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
