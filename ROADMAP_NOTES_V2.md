# ROADMAP_NOTES_V2.md
# Shilu — Living Roadmap and Feature Backlog
# Version: 2.0
# Maintained by: Matthew Miller (Founder)
# Last updated: March 2026 — comprehensive update, all phases documented

---

## Purpose

This file captures decisions, future features, architectural intentions, and items deferred from the current build. It is the single source of truth for what is planned, what is deferred, and why. It lives in the repository so engineers, clinical advisors, and future team members can read the founder's intent directly.

---

## Phase 1 — Proof of Concept (Current)

### Locked Decisions

- **Tech stack:** Python kernel + Streamlit frontend (v0.1 proof of concept only). Migration to React + FastAPI + Supabase planned for Phase 2.
- **Signals tracked:** Cardiovascular (BP systolic/diastolic, heart rate, HRV), Body (weight, waist circumference, BMI), Sleep (duration, quality, efficiency), Activity & Wellbeing (steps, activity level, stress, mood, energy), Optional (SpO2, respiratory rate, temperature), Notes.
- **Units:** US standard — weight in lbs, waist in inches, temperature in °F.
- **Age:** Dropdown (18–100) on Log Data page. Saved with every entry. Required for population reference range calibration.
- **Baseline period:** Minimum 14 days, recommended 2–3 readings per week.
- **Dual reference architecture:** Personal baseline (what is normal for this individual) AND population reference ranges (clinical norms for age/sex cohort) run simultaneously. The kernel flags deviation from personal baseline AND contextualizes against population norms. This prevents the "unhealthy normal" problem where a user's compromised baseline is mistaken for their true healthy state.
- **Alert fatigue prevention:** Three-situation framework — (1) acute deviation from personal baseline triggers escalation, (2) chronic elevation above population norms receives a one-time calm Baseline Context Note (not repeated escalation), (3) consistent improvement is affirmed. No alert flooding.
- **Notes field:** Plain language, user-owned, not analyzed by the kernel in Phase 1. Framed as a companion, not a health record. Language is warm and non-clinical. Tooltip explains value without creating a chilling effect.
- **No default values:** All measurement inputs start blank. Users must enter a value or explicitly skip. Sliders use skip checkboxes. This ensures baselines are built from real data only.
- **Auto-timestamp:** Each log entry is stamped at the time of submission. Per-signal timestamping (for users who take different measurements on different days) is deferred to Phase 2.

### Deferred to Phase 2

- **Per-signal timestamping:** Currently all signals in a session share one timestamp. Full per-signal date/time input requires a cleaner UX solution. Documented and deferred.
- **Child profiles:** Requires parental account structure, age-appropriate signal suppression, pediatric reference ranges, COPPA consideration, and clinical advisor review. Full scoping deferred to Phase 2.
- **Biological sex input:** Required for accurate population reference ranges (many norms are sex-differentiated). Currently absent. Must be added with appropriate sensitivity — framed as biological sex for clinical purposes, distinct from gender identity. Deferred to Phase 2 user profile build.
- **Device source tracking:** Knowing whether BP came from a cuff vs. a watch affects clinical weight of the signal. Deferred to Phase 2.
- **Per-signal save UX:** Currently all signals save together as one session. Better UX allows saving each category independently so partial sessions are not lost. Phase 2.
- **Blood pressure equipment guidance:** Most users do not own a BP cuff. Phase 2 will include first-time onboarding guidance for BP measurement, equipment recommendations (Omron home cuff), and wearable clarification (standard smartwatches cannot measure BP; Samsung Galaxy Watch is a limited US-unavailable exception).

---

## Phase 2 — User Profile, Persistent Storage, React Migration

### Goals

- Migrate frontend from Streamlit to React + FastAPI
- Implement Supabase persistent storage (replace in-memory stores)
- Build persisted user profile: age, biological sex, device source, communication preferences
- Implement Row Level Security (RLS) once authentication is in place
- Per-signal save UX redesign
- Child profile architecture (parental accounts, pediatric signals, COPPA review)
- Per-signal timestamping
- Habits module connected to signal interpretation (smoking, alcohol, diet patterns feed into explanation context)

### UI/Kernel Interface Discipline

When the engineer joins, enforce a strict interface contract:
- All kernel method calls in app.py must be validated against the actual kernel API before use
- No methods called that do not exist in the kernel (e.g., `get_digital_twin_status`, `get_baseline_context_notes`, `get_digital_twin_phase` were removed from Phase 1 — do not reintroduce without kernel implementation)
- Correct method names: `get_alerts()` not `get_active_alerts()`
- DigitalTwinPhase import removed — phase derived from data volume directly

---

## Device Integration Roadmap — Data Import and Wearable Connectivity

### Origin

Manual entry is the correct approach for Phase 1 proof of concept — it forces intentional logging and validates that the kernel processes data correctly. However, manual entry fatigue is a real adoption risk at scale. The long-term vision requires that Shilu can receive data from any source a user already uses — wearables, health apps, lab platforms — and ingest it automatically into the kernel with appropriate source weighting.

---

### Why Source Tracking Matters to the Architecture

Not all data is equal. A Polar H10 chest strap HRV reading is clinically more reliable than a wrist-based optical reading. A fasting glucose from a lab result carries more weight than an estimate. The kernel's `device_source` field — already present in `storage.py` — exists precisely for this reason. Every imported reading must carry its source so the baseline engine can apply appropriate confidence weighting. The engineer must understand this from Day 1.

**Source confidence tiers (to be formally defined with clinical advisor):**
- **Tier A — Medical grade:** Validated BP cuff, lab results, Polar H10 chest strap, ECG patch
- **Tier B — Consumer wearable:** Apple Watch, Garmin, Oura Ring, Whoop, Fitbit
- **Tier C — App-reported:** Welltory, third-party HRV apps, manual app entry
- **Tier D — User estimate:** Any value the user marks as approximate

---

### Tier 1 — File Import (Phase 2, highest priority)

**What it is:** Allow users to upload a data export file from an existing health app or wearable and have it automatically parsed and bulk-ingested into the kernel.

**Why it is the highest priority:**
- Solves manual entry fatigue immediately for early users
- Allows users to onboard with historical data — Shilu builds their baseline instantly rather than waiting 14 days from scratch
- No API agreements or developer partnerships required
- Buildable by one engineer in 1–2 days per supported format

**Target formats for Phase 2:**
- **Apple Health XML export** — highest leverage target. Apple Health aggregates data from virtually every health app and wearable on iOS. One Apple Health import covers heart rate, HRV, sleep, steps, weight, SpO2, and more from all connected apps simultaneously. This is the single most impactful integration Shilu can build.
- **Welltory CSV export** — HRV (RMSSD), stress, energy, heart rate. Directly relevant to current founder testing.
- **Garmin CSV export** — heart rate, sleep, stress, steps, body battery.
- **Fitbit CSV export** — sleep, heart rate, steps, weight.
- **Generic Shilu CSV template** — a Shilu-defined template any user can fill in for bulk historical entry.

**Engineering requirements:**
- Parser must handle column mapping, unit normalization, and timestamp normalization per source format
- Each parsed record tagged with `device_source` matching the source app or device
- Duplicate detection required — re-importing the same file must not create duplicate records
- User shown a preview of what will be imported before confirmation
- Failed rows reported clearly, not silently dropped
- Import event logged in the Evidence Ledger with source, record count, and timestamp

**First engineer task — Apple Health XML import scope:**
1. Parse Apple Health `export.xml` format
2. Map Apple Health data types to Shilu signal IDs
3. Normalize units to Shilu standard (lbs, inches, °F, ms, etc.)
4. Tag each record with `device_source = "apple_health"`
5. Deduplicate against existing records using timestamp + signal_id + value hash
6. Show user a preview table before import confirmation
7. Report results: X records imported, Y duplicates skipped, Z failed with reasons

This single feature eliminates manual entry fatigue for all iOS users and enables historical data onboarding at signup — transforming the cold start experience entirely.

---

### Tier 2 — Direct API Integration (Phase 2–3)

**What it is:** Shilu connects directly to a health platform's API and pulls data automatically on a schedule.

**Priority order:**

**1. Apple HealthKit (iOS SDK)**
The single most important integration. HealthKit aggregates virtually all health and fitness data on iOS. A HealthKit integration means Shilu automatically receives data from every app the user already uses on their iPhone. Requires iOS app development (React Native or native Swift), Apple developer program enrollment ($99/year), and HealthKit entitlement approval from Apple.

**2. Google Health Connect (Android)**
The unified Android health data platform replacing Google Fit. Same strategic value as HealthKit for Android users. Requires Android development and Google Play developer enrollment.

**3. Oura Ring API**
Oura provides one of the most clinically relevant consumer datasets — sleep stages, HRV, resting heart rate, body temperature, activity. REST API with OAuth. High data quality, well-documented. Priority target for Oura device owners.

**4. Whoop API**
HRV, sleep, recovery scores, and strain data. REST API with OAuth. Strong user base among exactly Shilu's target audience.

**5. Garmin Health API**
Wide range of signals from Garmin devices. Requires partnership application.

**6. Fitbit Web API (now Google)**
Being integrated into Health Connect. REST API available covering sleep, heart rate, steps, weight.

**Engineering requirements for all API integrations:**
- OAuth 2.0 authentication for all — user grants permission, Shilu stores refresh tokens securely
- Incremental sync only — pull new data since last sync, not full history each time
- Rate limits respected per platform
- All pulled data tagged with platform source in `device_source` field
- User can disconnect any integration at any time
- Data from a disconnected source clearly identifiable in the user's record

---

### Tier 3 — Real-Time Wearable Streaming (Phase 3–4)

**What it is:** Direct hardware SDK integration for continuous passive data collection — real-time streaming rather than periodic sync.

**Why it matters:**
Daily API sync captures snapshots. Real-time streaming captures the continuous signal — resting heart rate trending across a day, HRV dropping in response to stress, sleep architecture changing over weeks. This is the data resolution that makes the Phase 4 correlation engine and Phase 6 digital twin genuinely powerful.

**Target integrations:**
- **Polar SDK** — real-time HRV streaming from H10 and Verity Sense. H10 is the gold standard for consumer HRV measurement. Shilu's highest priority Tier 3 target for cardiovascular signal quality.
- **Oura SDK** — real-time temperature, heart rate, and movement streaming via partner SDK.
- **Withings SDK** — Withings makes FDA-cleared consumer devices including connected BP monitors, smart scales, and sleep trackers. A Withings integration would give Shilu Tier A source confidence BP readings from a validated medical-grade device.
- **Continuous glucose monitors (CGM) — Phase 4+ consideration** — Dexterity, Abbott LibreLink, and Levels Health all have API access in various states of openness. CGM data would be transformative for the metabolic signal layer. Worth tracking as the consumer CGM market expands.

---

### Integration Governance

All device integrations must comply with Shilu's three pillars:

- **Personal Ownership** — user controls which integrations are active, can disconnect any source at any time, and can see exactly which data came from which source
- **Safety Before Autonomy** — imported data is subject to the same safety threshold checks as manually entered data. A dangerous reading from a wearable triggers the same alert as a manually entered one.
- **Trust Through Verifiable Integrity** — every imported record is permanently tagged with its source, import timestamp, and source confidence tier. The audit ledger records the import event. Nothing is silently ingested.

---

## Phase 3–4 — Scientific Knowledge Base (RAG Architecture)

### Origin

Suggested by security advisor (cybersecurity professional, healthcare background). Core insight: Shilu can close the 17-year gap between clinical research publication and clinical practice application by building a curated, continuously updated scientific knowledge base that informs signal interpretation in real time.

### Architecture

**Four components:**

1. **Knowledge Indexer** — automated pipeline that ingests peer-reviewed literature from PubMed Central (open access), processes and chunks articles, embeds them into a vector store, and indexes by signal type, condition, population, and evidence tier. Runs on a scheduled update cycle. Monitors for retractions and removes invalidated findings automatically.

2. **Evidence Query Engine** — when the kernel generates a signal interpretation or explanation, it queries the knowledge base for literature relevant to this specific user's profile and the specific pattern detected. Returns ranked results by evidence tier and recency.

3. **Evidence-Enhanced Explanation Generator** — integrates literature findings into user-facing explanations. Does NOT expose raw citations to users by default. Uses calibrated plain language: "Research consistently shows..." (Tier 1) vs. "Some research suggests..." (Tier 3). Full citation detail available via optional expandable section for users who want it (progressive disclosure UX).

4. **Evidence Ledger Extension** — every explanation with a literature basis logs the source, evidence tier, and retrieval date in the user's audit ledger. Verifiable, transparent, user-owned.

### Evidence Tiers

- **Tier 1:** Systematic reviews and meta-analyses, large RCTs (n > 1,000)
- **Tier 2:** Well-designed RCTs, large prospective cohort studies
- **Tier 3:** Observational studies, smaller cohorts, case series
- **Tier 4:** Expert opinion, consensus guidelines, emerging research

### UX Principle — Progressive Disclosure

Default output is plain language calibrated to evidence tier. No information overload. Full citations, study details, and population data available on demand via expandable "Learn more" section. Most users will never need the detail. Users who want it can always access it. This applies to all evidence presentation throughout the system.

### Prerequisites Before Building

- Clinical advisor must review and approve the evidence tier framework and the language calibration for each tier
- Knowledge Governance Framework document to be created with clinical advisor input
- Correlation engine (Phase 4) and knowledge base should be designed together — they are most powerful in combination

---

## Phase 4 — Correlation Engine

### Goal

Move from single-signal interpretation to cross-signal pattern recognition. Identify correlations between lifestyle inputs and health outcomes specific to this individual over time.

Examples:
- Poor sleep quality on nights following high stress days
- Resting heart rate elevation correlating with reduced activity 3 days prior
- Waist circumference trend correlating with mood score patterns

### Data Requirement

Meaningful correlation detection requires sufficient longitudinal data — minimum 60–90 days of reasonably consistent logging across multiple signal categories. Phase 4 should not activate until this threshold is met for a given user.

---

## Phase 5 — Dual-Output Architecture (Trust API)

### Goal

Establish two distinct output streams from the Shilu kernel:

1. **Consumer output** — plain language, personalized, uncertainty-disclosed, designed for the individual user. The Shilu experience they interact with daily.

2. **Clinical output (Trust API)** — structured, standards-compliant (HL7 FHIR where applicable), exportable record suitable for sharing with physicians, specialists, and eventually integration with EHR systems (Epic, Cerner). Activated only with explicit user consent.

### Clinical Integration Vision

The Trust API enables Shilu to plug into healthcare systems. A physician who has a patient using Shilu can, with that patient's permission, access years of verified longitudinal observation — not as anecdote but as structured, auditable data. This dramatically reduces onboarding time, improves continuity of care, and gives the physician a picture of the patient they have never had before.

Epic integration is the long-term target. The pathway is through HL7 FHIR compliance and Epic's App Orchard program. This requires clinical advisor guidance and regulatory awareness throughout.

---

## Phase 6 — 3D Anatomical Digital Twin

### Goal

A dynamic 3D representation of the individual that responds to their health data in real time. Not a static model — a living visualization that changes as the user's signals change.

Examples:
- Cardiovascular system visualization reflects blood pressure trends
- Sleep architecture visualization responds to sleep quality patterns
- Metabolic visualization responds to weight, waist, and activity trends

### Technical Requirements

- 3D rendering engine (Three.js for web, native for mobile)
- Anatomical model library — requires partnership with medical visualization providers (BioDigital, Visible Body, or equivalent)
- Signal-to-visualization mapping layer — connects kernel outputs to anatomical model states
- Clinical advisor review of all anatomical representations for accuracy

### AI Integration

Phase 6 is where large language model and generative AI integration becomes appropriate — specifically for generating personalized anatomical visualizations and for powering the narrative layer that explains what the user is seeing in their body.

---

## Phase 7 — Jarvis Layer (Conversational Health Intelligence)

### Goal

A fully conversational health companion that knows the user completely — not because it was programmed to, but because it has learned them over years of real data. Responds to natural language. Anticipates needs. Explains the user's health in their own context, using their own history.

### Name

The Shilu companion name — the "JARVIS" equivalent — is TBD. The founder is developing an acronym-based name that describes what the system does and can also serve as the companion's identity (similar to how JARVIS = Just A Rather Very Intelligent System). To be locked in before Phase 7 branding.

### Interaction Principles

- Never prescribes. Never diagnoses. Never replaces clinical judgment.
- Always explains uncertainty honestly.
- Uses the user's communication preferences, language level, and history to calibrate every response.
- Evidence-backed where relevant (Phase 3 knowledge base feeds Phase 7 responses).
- Safety escalation built in — knows when to say "this warrants talking to your doctor" and says it clearly.

---

## Phase 8 — Embodied Intelligence (Humanoid Companion)

### Vision Statement

Phase 8 is the long-term destination of everything Shilu is building: the transfer of Shilu's longitudinal intelligence into a physical, humanoid robotic form that lives in the user's home. The robot does not arrive as a general-purpose device. It arrives already knowing its person — because the relationship has been built over years through every preceding phase.

This is the fundamental distinction from every existing humanoid robot product (Tesla Optimus, Figure, Agility Robotics, Boston Dynamics): **Shilu builds the intelligence first, and gives it a body last.** The intelligence precedes the body. The relationship precedes the presence.

### The Inversion Principle

Every major humanoid robot company builds the body first and hopes intelligence catches up. The result is a general-purpose machine with no meaningful relationship to the individual it serves. Shilu inverts this entirely. By the time the companion takes physical form, it will have accumulated years of the most intimate, verified, longitudinal personal health data ever assembled for a single individual. The physical presence is the final expression of a relationship that already exists.

### What the Companion Does

**Passive continuous monitoring** — integrated biometric sensors (optical, acoustic, thermal, motion) observe the user without requiring active input. Every observation cross-referenced against the user's personal baseline — not population averages. Ambient health monitoring that never asks the user to do anything.

**Active intervention** — calibrated to the user's established preferences and communication style:
- Notices sedentary patterns and correlates with the user's personal sleep-activity baseline
- Detects stress indicators in voice and cross-references with the user's cortisol-sleep correlation model
- Observes meal patterns against the user's metabolic baseline
- Detects subtle physical changes (gait, posture, movement quality) weeks before the user notices anything

**Emergency response** — because it knows the user's baseline completely, it distinguishes genuine emergencies from normal variation with precision no general-purpose system can approach. Fall detection with context. Cardiac monitoring. Stroke indicator detection. Medication adherence.

**Companion, not caretaker** — the language, interaction style, and nature of every intervention must feel like a trusted friend who happens to know your health deeply — not a surveillance device or a medical monitor. A user should not feel watched. They should feel accompanied.

### Hardware Strategy

Shilu will not manufacture hardware. Phase 8 is built on a licensing and integration model — Shilu's intelligence layer licensed to hardware partners who manufacture the physical companion. The alternative outcome: Shilu becomes the intelligence standard that the best robot manufacturer in the world chooses to integrate, because no other health intelligence system has the longitudinal depth, trust architecture, and clinical integration framework Shilu has built.

Hardware partners must commit to:
- Personal ownership architecture — all companion-generated data belongs to the user
- Safety-before-autonomy constraints — companion operates within defined limits with clinical oversight
- Shilu's security architecture standards
- Full audit transparency — every action logged in the user's Evidence Ledger
- No third-party data sharing without explicit, granular, user-granted consent

### Trust Architecture Requirements

- **Physical off switch** — hardware-level deactivation, immediate, visible, verifiable, no software mediation
- **Local processing option** — user can operate with all data stored locally, no cloud transmission, auditable
- **Audit access** — every observation, inference, and action accessible to the user in plain language at any time
- **Consent architecture** — no new monitoring capabilities without explicit, informed, renewed consent
- **The chilling effect problem** — a user who feels watched behaves differently, which biases their health data. The companion must feel present without feeling observational. This is an interaction design, language design, and physical design challenge that must be solved before Phase 8 ships.

### Competitive Context

The humanoid robot market is being built in the wrong direction. Existing players (Optimus, Figure, Agility, Boston Dynamics) are solving general-purpose labor replacement with no meaningful relationship to any individual user. The moat they are building — hardware capability — commoditizes. The moat Shilu is building — years of personal longitudinal health data, a trust relationship, and a proven clinical intelligence layer — cannot be replicated by any company that starts with the body.

Phase 8 is not necessarily a competitive landscape. It is a partnership landscape. The companies building humanoid bodies will eventually need intelligence layers that make those robots genuinely valuable to specific individuals. Shilu's framework is positioned to become that intelligence standard.

### Prerequisites Before Phase 8 Begins

**Intelligence prerequisites:**
- Phase 7 Jarvis layer fully operational and clinically validated
- Longitudinal data from a meaningful user cohort validated against real-world clinical outcomes
- Adversarial testing of intelligence layer in home environments completed

**Trust prerequisites:**
- Shilu's non-negotiable pillars publicly documented, independently audited, recognized as an industry standard
- Track record of at least five years of user data governance demonstrating pillars in practice
- Regulatory engagement established with FDA, FTC, and relevant international bodies

**Partnership prerequisites:**
- Hardware partner identified and vetted against Shilu's pillar requirements
- Clinical advisor network expanded to include physical medicine, neurology, geriatrics, and occupational therapy
- Legal architecture for companion liability, data ownership in physical spaces, and emergency intervention protocols established

### Full Phase 8 Documentation

See: `Shilu_Digital_Twin_Phase8_Embodied_Intelligence.docx` in the document library.

---

## Business Strategy and Go-To-Market

### Company Identity

**Name:** Shilu
**Origin:** Coined from the founder's parents' nicknames — Shine (father) and Lullubelle (mother). The name carries personal meaning and founding story while reading as a forward tech brand — two syllables, soft consonants, no healthcare connotation.
**Trademark status:** USPTO search confirmed no results in any class as of March 2026. Clear to file.
**Category positioning:** Shilu is a tech company focused on healthcare — not a healthcare company. This distinction matters for valuation, investor conversations, and talent recruitment. Framing as health tech limits multiples and puts Shilu in a box with EHR vendors. Framing as AI/tech infrastructure with a healthcare focus positions it correctly for the long arc.
**Long-term identity:** Personal intelligence infrastructure — the health companion a person carries for life, eventually embodied in Phase 8.

### Three Non-Negotiable Pillars

These are architectural constraints, not marketing claims. Every product decision, every engineering choice, every partnership must be evaluated against all three.

1. **Personal Ownership** — The user's health data belongs to them permanently. Portable, exportable, deletable at any time. Shilu will never sell it, share it without explicit consent, or use it for anything other than building the user's personal health picture.

2. **Safety Before Autonomy** — The safety architecture is non-bypassable. When data warrants attention, Shilu tells the user. Always. The system will never be configured to suppress alerts for engagement, retention, or commercial reasons.

3. **Trust Through Verifiable Integrity** — Every insight is traceable to the specific data that produced it. Full audit chain. No black boxes. No confident claims without evidence. Uncertainty is always disclosed honestly.

### Business Model

**Primary revenue — subscriptions:**
- **Consumer tier (B2C):** Monthly or annual subscription for individual users. Pricing TBD pending market validation but positioned as premium — comparable to a gym membership, not a free app.
- **Institutional tier (B2B / IaaS):** Organizations — employers, insurers, health systems — pay to deploy Shilu's intelligence infrastructure for their population. This is the primary early revenue path. IaaS-first sequencing means B2B revenue funds the platform while the consumer side builds identity and brand.

**IaaS-first sequencing rationale:**
Building a consumer health app requires massive user acquisition spend and a long baseline-building period before the product demonstrates value. IaaS allows Shilu to generate revenue from Day 1 by selling the infrastructure layer to organizations that already have users. The consumer founding cohort runs in parallel as an identity anchor — not the primary revenue source in Years 1–2.

**Revenue will never come from:**
- Selling or licensing user health data to any third party
- Advertising or sponsored content
- Insurance underwriting or risk scoring
- Employer surveillance or productivity monitoring

### Go-To-Market Sequencing

**Phase 1 (current) — Proof of concept:**
Founder-led build. Streamlit prototype. Small founding cohort of personal contacts. Goal: validate the kernel works, surface UX issues, demonstrate the concept is real.

**Phase 2 — Founding cohort + first B2B:**
React migration. Supabase persistence. 50–100 founding consumer users recruited personally. First IaaS conversation with one employer or health system. Clinical advisor signed. Security advisor engaged.

**Phase 3 — IaaS launch:**
First paying institutional client. Consumer waitlist building. Revenue funds engineering team expansion. Clinical validation data accumulating.

**Phase 4+ — Scale:**
Multiple institutional clients. Consumer subscription launches publicly. Series A funding conversation when ARR justifies the valuation.

### Funding Strategy

**Current stance:** Private. Not seeking external funding yet. The quiet building phase is intentional — protect the vision, build the foundation, recruit the right people before exposing the company to competitive attention.

**Grant pathway (exploring):**
NIH SBIR/STTR grants for health technology with preventive or patient-centered angle. PCORI (Patient-Centered Outcomes Research Institute) funds patient-centered health innovation. NSF SBIR for AI and data systems. Grant funding provides runway without dilution and does not require the Delaware C-Corp conversion that VC funding typically demands.

**VC pathway (future):**
When institutional capital is sought, conversion from LLC to Delaware C-Corp is standard and well-documented. Wyoming LLC structure used currently does not complicate this conversion. Series A would follow demonstrated IaaS revenue and a validated consumer cohort with real longitudinal data.

**Hypothetical valuation context:**
At Phase 4 with meaningful IaaS ARR and a validated consumer cohort, Shilu should be valued as an AI infrastructure company, not a health app. Comparable: Function Health raised $298M at $2.5B valuation as a health data platform. Shilu's longitudinal intelligence layer and Phase 8 vision positions it well above that ceiling at scale.

### Business Entity

**Current status:** Decision pending between Wyoming LLC + Tennessee foreign registration vs. Tennessee LLC direct.

**Wyoming + TN Foreign route:**
- Wyoming formation: ~$104
- TN foreign registration: ~$300
- Annual cost: ~$560–$810
- Benefit: Owner name off public records, strongest privacy protection, no state income tax, no franchise tax at Wyoming level, clean conversion path to Delaware C-Corp

**Tennessee direct route:**
- Formation: ~$307
- Annual cost: ~$450–$550
- Benefit: Simpler to manage, one state, one registered agent
- Limitation: Owner name on public record, franchise and excise taxes apply, less favorable for long-term growth

**Key insight:** Tennessee taxes (franchise, excise, gross receipts) apply regardless of where the LLC is formed, because Shilu operates in Tennessee. The cost difference between the two routes narrows significantly once Tennessee taxes are accounted for. The Wyoming route buys privacy at a modest premium — approximately $175–$200/year.

**Decision not yet made.** File before taking first subscription payment or signing any commercial agreements.

**Note on future conversion:** When raising institutional capital (Series A or beyond), conversion to Delaware C-Corp is standard. Both Wyoming and Tennessee LLC structures convert cleanly. This is a well-documented process and does not require starting over.

### Intellectual Property Strategy

**Patent status:** No patents filed as of March 2026.

**Recommendation:** File provisional patent applications on the two strongest novel technical mechanisms before the engineer joins and before the product goes public. Provisional applications cost ~$320 each for a small entity, require no formal claims, and establish a priority date that protects against competitors filing similar applications after your date.

**Priority patent candidates:**
1. **Dual reference architecture** — the specific mechanism by which Shilu simultaneously runs a personal baseline model and a population reference model, cross-references them, and generates a Baseline Context Note as a distinct output type separate from escalation. Solves the "unhealthy normal" problem. Novel, technically specific, practically implemented.
2. **Three-situation alert framework** — the specific logic distinguishing acute personal deviation, chronic population-level elevation, and improvement — generating categorically different outputs for each. Novel process architecture.

**Patent category:** Utility patents under CPC classification G16H (ICT for health informatics). Specifically G16H50/30 (medical data mining and diagnosis) and G16H10/60 (handling patient-related medical data).

**What is not patentable:** The broad concept of "longitudinal health intelligence." Too abstract. The narrow, technically specific process implementations described above are what survive USPTO scrutiny.

**Timeline:** File provisionals before public launch or engineer recruitment. Full utility applications after revenue justifies the $15,000–$30,000 attorney investment.

---

## Clinical Advisor Strategy

### Role

The clinical advisor is not a figurehead. They are a structural requirement for Shilu to operate with integrity. The threshold file (`thresholds.py`) has `placeholder = True` on every entry for a reason — those values are architectural demonstrations, not clinically validated numbers. Before Shilu is used by anyone other than the founder, a qualified clinician must review and sign off on every threshold, every population reference range, and every safety escalation trigger.

### Current Status

Active search underway. Founder has access to clinicians through personal network. Approach: lead with the problem (health amnesia, longitudinal intelligence gap), not with "will you be my advisor." Let clinicians who see the same gap in their practice self-select.

### Compensation Options (placeholder — to be negotiated)

- Equity (advisory shares, typically 0.1–0.5% with vesting)
- Monthly retainer
- Per-hour consultation fee
- Hybrid equity + small retainer

Clinical Advisor Agreement template created and ready for execution. See document library.

### Clinical Advisor Responsibilities

- Review and sign off all safety thresholds in `thresholds.py`
- Review and approve population reference ranges
- Review and approve the evidence tier framework for the Phase 3 knowledge base
- Provide clinical language review for all user-facing output from the explanation generator
- Serve as clinical credibility in institutional sales conversations
- Advise on regulatory pathway (FDA, HIPAA, clinical claims)

### Clinical Advisor Expansion (Phase 3+)

As Shilu expands into correlation engine and digital twin phases, additional advisors needed:
- Cardiologist (cardiovascular signal interpretation)
- Endocrinologist (glucose, metabolic signals)
- Sleep medicine specialist (sleep architecture analysis)
- Physical medicine / occupational therapy (Phase 8 physical companion)
- Geriatrician (aging population, Phase 8 home companion safety)

---

## Security Architecture

### Security Advisor

Cybersecurity professional, healthcare background, personal friend of founder. Advisory role, currently pro bono. Suggested the Scientific Knowledge Base / RAG architecture — demonstrating genuine strategic engagement with the product.

### Core Principles Already in Architecture

- **Evidence Ledger** — append-only audit trail, tamper-evident, every action logged
- **User isolation** — each user's data is completely isolated; no cross-user data access
- **No monetization architecture** — system is not architected to sell or share user data; this cannot be accidentally enabled
- **Source tagging** — every data point carries its origin permanently

### Phase 2 Security Priorities

To be formally scoped with security advisor before Phase 2 launch:
- Row Level Security (RLS) in Supabase — prevents any user from accessing another user's data even if API is compromised
- Authentication architecture — secure login, session management, token handling
- API key management — secure storage of Supabase keys, no keys in source code
- Penetration testing protocol — structured before public beta launch
- HIPAA readiness assessment — required if clinical output / Trust API activates

### HIPAA Consideration

Shilu's consumer product in Phase 1–2 is not a covered entity under HIPAA because it is not a healthcare provider, health plan, or healthcare clearinghouse, and it does not transmit health information on behalf of a covered entity. However the moment the Trust API activates and Shilu exchanges data with a physician or health system, Business Associate Agreement (BAA) obligations likely apply. Security advisor and healthcare attorney must review before Trust API goes live.

---

## Ongoing — UX Principles (Apply Across All Phases)

- **Progressive disclosure:** Show the minimum necessary. Make detail available on demand. Never overwhelm.
- **Companion language:** Warm, non-clinical, never alarmist. The system is a companion, not a monitor.
- **Trust language:** Avoid words that suggest surveillance, permanence of sensitive notes, or institutional oversight. Users must feel their data is theirs.
- **Honest uncertainty:** When the kernel is uncertain, say so. Confidence inflation is a non-negotiable violation of Shilu's pillars.
- **Safety escalation:** Know when to tell the user to see a doctor. Say it clearly, warmly, and without panic.

---

*This document is a living record. Update it whenever a decision is made, a feature is deferred, or a new idea needs to be captured. Nothing that matters should live only in someone's head.*
