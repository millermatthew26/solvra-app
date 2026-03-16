"""
Solvra — Personal Health Intelligence
========================================
Streamlit interface for the Solvra Kernel v2.

Run locally:
    streamlit run app.py

Sections:
    1. Log Data       — enter today's health measurements
    2. My Baselines   — personal baseline per signal with uncertainty
    3. Trends         — Plotly charts showing trajectory over time
    4. Signals        — active findings, alerts, and context notes
    5. My Twin        — digital twin phase status across all signals
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from datetime import datetime, timedelta
from typing import Optional
import plotly.graph_objects as go

from solvra_kernel.core.kernel import SolvraKernel
from solvra_kernel.models.entities import (
    SIGNAL_DEFINITIONS, UncertaintyLevel, AlertSeverity,
    DigitalTwinPhase, RiskBand
)
from storage import SupabaseStore

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title    = "Solvra",
    page_icon     = "🧬",
    layout        = "wide",
    initial_sidebar_state = "expanded",
)

# ── STYLES ────────────────────────────────────────────────────────────────────

st.markdown("""
<style>
    .main-header {
        font-size: 2rem; font-weight: 800;
        color: #1B3A5C; margin-bottom: 0;
    }
    .sub-header {
        font-size: 1rem; color: #555;
        margin-top: 0; margin-bottom: 1.5rem;
    }
    .metric-card {
        background: #F0F6FF; border-radius: 8px;
        padding: 1rem; border-left: 4px solid #2E75B6;
        margin-bottom: 0.5rem;
    }
    .alert-urgent {
        background: #FFF3F3; border-radius: 8px;
        padding: 1rem; border-left: 4px solid #C00000;
        margin-bottom: 0.5rem;
    }
    .alert-monitor {
        background: #FFFDF0; border-radius: 8px;
        padding: 1rem; border-left: 4px solid #BF6900;
        margin-bottom: 0.5rem;
    }
    .context-note {
        background: #EBF7EF; border-radius: 8px;
        padding: 1rem; border-left: 4px solid #1F6B3A;
        margin-bottom: 0.5rem;
    }
    .twin-phase {
        background: #F5EEF8; border-radius: 8px;
        padding: 1rem; border-left: 4px solid #4A235A;
        margin-bottom: 0.5rem;
    }
    .uncertainty-high   { color: #C00000; font-weight: 600; }
    .uncertainty-medium { color: #BF6900; font-weight: 600; }
    .uncertainty-low    { color: #1F6B3A; font-weight: 600; }
    .section-divider { margin: 1.5rem 0; border-top: 2px solid #E0E0E0; }
</style>
""", unsafe_allow_html=True)

# ── SESSION STATE ─────────────────────────────────────────────────────────────

def get_kernel() -> SolvraKernel:
    if "kernel" not in st.session_state:
        st.session_state.kernel = SolvraKernel()
    return st.session_state.kernel

def get_store() -> SupabaseStore:
    if "store" not in st.session_state:
        st.session_state.store = SupabaseStore()
    return st.session_state.store

def get_onboarded() -> bool:
    """Returns True if the user has passed the welcome screen."""
    return st.session_state.get("onboarded", False)

def get_user_id() -> str:
    """For prototype: simple session user ID. Replace with auth in production."""
    if "user_id" not in st.session_state:
        st.session_state.user_id = "demo_user"
    return st.session_state.user_id

# ── HELPERS ───────────────────────────────────────────────────────────────────

SIGNAL_LABELS = {
    "bp_systolic":   ("Systolic BP", "mmHg", 60.0, 200.0, 120.0),
    "bp_diastolic":  ("Diastolic BP", "mmHg", 40.0, 130.0, 80.0),
    "heart_rate":    ("Heart Rate", "bpm", 35.0, 180.0, 70.0),
    "weight":        ("Weight", "lbs", 10.0, 800.0, 165.0),
    "waist_circ":    ("Waist Circumference", "inches", 20.0, 80.0, 34.0),
    "sleep_hours":   ("Sleep Duration", "hours", 0.0, 16.0, 7.5),
    "sleep_quality": ("Sleep Quality", "1-5", 1.0, 5.0, 3.0),
    "activity_mins": ("Activity", "minutes", 0.0, 300.0, 30.0),
    "stress_level":  ("Stress Level", "1-5", 1.0, 5.0, 3.0),
    "glucose":       ("Fasting Glucose (optional — from blood test or glucometer)", "mg/dL", 50.0, 400.0, 95.0),

    # v0.2 signals
    "body_temp":     ("Body Temperature", "°F", 95.0, 105.0, 98.6),
    "spo2":          ("Oxygen Saturation (SpO2)", "%", 70.0, 100.0, 98.0),
    "hrv":           ("Heart Rate Variability (optional — wearable)", "ms", 0.0, 250.0, 50.0),
    "energy_level":  ("Energy Level", "1-5", 1.0, 5.0, 3.0),
}

SIGNAL_HELP = {
    "bp_systolic":   "The top number in a blood pressure reading (e.g. 120 in 120/80). Measures pressure in your arteries when your heart beats. Use a home blood pressure cuff — take it while seated and rested.",
    "bp_diastolic":  "The bottom number in a blood pressure reading (e.g. 80 in 120/80). Measures pressure between heartbeats. Take alongside systolic using the same home BP cuff.",
    "heart_rate":    "Your resting pulse — beats per minute when you are sitting still and relaxed. Measure it first thing in the morning before getting up, or use a wearable device.",
    "weight":        "Your body weight in pounds. Weigh yourself at the same time each day for consistency — ideally in the morning after using the restroom.",
    "waist_circ":    "Measure around your midsection at the level of your belly button, relaxed and not sucking in. Use a soft tape measure. This is a stronger metabolic signal than weight alone.",
    "sleep_hours":   "Total hours of sleep from when you fell asleep to when you woke up. Include naps if they were more than 30 minutes.",
    "sleep_quality": "How rested you feel when you wake up, on a scale of 1 (very poor) to 5 (excellent). Rate it within the first 10 minutes of waking before the feeling fades.",
    "activity_mins": "Minutes of intentional physical activity today — walking, exercise, sport, anything that raised your heart rate. A 20-minute walk counts. Incidental movement like housework does not.",
    "stress_level":  "Your overall stress level today on a scale of 1 (very low) to 5 (very high). Rate your average across the day, not just the worst moment.",
    "energy_level":  "How energetic you felt today on a scale of 1 (exhausted) to 5 (full energy). Rate your overall level across the day, not just right now.",
    "glucose":       "Fasting blood glucose in mg/dL. This requires either a home glucometer (a small device that tests a drop of blood from your fingertip) or a recent lab result from your doctor. Only log when you have an actual reading — do not estimate.",
    "body_temp":     "Your resting body temperature in Fahrenheit. Use an oral thermometer when you are not exercising or ill for your baseline. Note: temperature is most useful for detecting changes from your personal normal.",
    "spo2":          "Blood oxygen saturation — the percentage of your red blood cells carrying oxygen. Measured with a pulse oximeter, a small clip device that fits on your fingertip. Available at pharmacies for under 0, or captured by Apple Watch, Garmin, and similar wearables.",
    "hrv":           "Heart Rate Variability — the variation in time between heartbeats in milliseconds. A higher HRV generally indicates better recovery and cardiovascular health. Requires a wearable device: Apple Watch, Garmin, Whoop, Oura Ring, or Polar chest strap. Find it in your device's companion app — look for HRV, recovery score, or readiness score.",
}

# ── HABITS DATA ──────────────────────────────────────────────────────────────

ONGOING_HABITS = {
    "smoking":        ("Smoking", "🚬", "Do you currently smoke cigarettes, cigars, or a pipe?"),
    "vaping":         ("Vaping / E-cigarettes", "💨", "Do you currently vape or use e-cigarettes?"),
    "alcohol":        ("Alcohol", "🍷", "How many drinks per week on average?"),
    "caffeine":       ("Caffeine", "☕", "How many caffeinated drinks per day on average?"),
    "recreational":   ("Recreational substances", "⚠️", "Do you use any recreational substances? (cannabis, etc.)"),
    "prescription":   ("Prescription medications", "💊", "Are you currently taking any prescription medications?"),
    "supplements":    ("Supplements / vitamins", "🧪", "Are you taking any supplements, vitamins, or OTC medications?"),
    "sedentary_work": ("Sedentary work", "🖥️", "Do you have a desk job or spend most of your day sitting?"),
    "night_shift":    ("Night shift work", "🌙", "Do you work nights or rotating shifts?"),
}

HABIT_CATEGORIES = [
    "Exercise & Movement",
    "Diet & Nutrition",
    "Sleep",
    "Stress & Mental Health",
    "Substances",
    "Medications & Supplements",
    "Other",
]

UNCERTAINTY_COLOR = {
    UncertaintyLevel.HIGH:   ("#C00000", "🔴"),
    UncertaintyLevel.MEDIUM: ("#BF6900", "🟡"),
    UncertaintyLevel.LOW:    ("#1F6B3A", "🟢"),
}

TWIN_PHASE_LABELS = {
    DigitalTwinPhase.PHASE_1_PERSONAL_RECORD:  ("Phase 1 — Personal Record",  "📋"),
    DigitalTwinPhase.PHASE_2_BASELINE_MODEL:   ("Phase 2 — Baseline Model",   "📊"),
    DigitalTwinPhase.PHASE_3_TRAJECTORY_MODEL: ("Phase 3 — Trajectory Model", "📈"),
    DigitalTwinPhase.PHASE_4_CORRELATION:      ("Phase 4 — Correlation",      "🔗"),
    DigitalTwinPhase.PHASE_5_SIMULATION:       ("Phase 5 — Simulation",       "🧬"),
}

def load_measurements_into_kernel(kernel: SolvraKernel, store: SupabaseStore, user_id: str):
    """Load persisted measurements from storage back into the kernel's ingestion store."""
    measurements = store.load_measurements(user_id)
    for m in measurements:
        # Re-ingest into kernel memory without re-saving
        kernel.ingestion._store.setdefault(user_id, {}).setdefault(m.signal_id, [])
        existing_ids = {x.id for x in kernel.ingestion._store[user_id][m.signal_id]}
        if m.id not in existing_ids:
            kernel.ingestion._store[user_id][m.signal_id].append(m)

def uncertainty_badge(level: UncertaintyLevel) -> str:
    color, icon = UNCERTAINTY_COLOR.get(level, ("#555", "⚪"))
    return f"{icon} {level.value.replace('_', ' ').title()}"

# ── WELCOME SCREEN ───────────────────────────────────────────────────────────

def render_welcome():
    """Full-screen welcome experience shown on first open."""

    # Hide the sidebar on the welcome screen
    st.markdown("""
    <style>
        [data-testid="stSidebar"] { display: none; }
        .welcome-hero {
            text-align: center;
            padding: 3rem 2rem 1rem 2rem;
        }
        .welcome-title {
            font-size: 4rem;
            font-weight: 900;
            color: #1B3A5C;
            letter-spacing: -1px;
            margin-bottom: 0.25rem;
        }
        .welcome-tagline {
            font-size: 1.4rem;
            color: #2E75B6;
            font-style: italic;
            margin-bottom: 2.5rem;
        }
        .welcome-body {
            font-size: 1.05rem;
            color: #333;
            line-height: 1.8;
            max-width: 680px;
            margin: 0 auto;
        }
        .pillar-card {
            background: #F0F6FF;
            border-radius: 12px;
            padding: 1.2rem 1.5rem;
            border-left: 5px solid #2E75B6;
            margin-bottom: 1rem;
            text-align: left;
        }
        .pillar-title {
            font-weight: 700;
            color: #1B3A5C;
            font-size: 1rem;
            margin-bottom: 0.3rem;
        }
        .pillar-body {
            color: #444;
            font-size: 0.95rem;
            line-height: 1.6;
        }
        .welcome-disclaimer {
            font-size: 0.8rem;
            color: #999;
            margin-top: 1.5rem;
            font-style: italic;
        }
    </style>
    """, unsafe_allow_html=True)

    # Hero
    st.markdown("""
    <div class="welcome-hero">
        <div class="welcome-title">🧬 Solvra</div>
        <div class="welcome-tagline">Your personal health intelligence — for life.</div>
    </div>
    """, unsafe_allow_html=True)

    # Opening statement
    _, center, _ = st.columns([1, 3, 1])
    with center:
        st.markdown("""
        <div class="welcome-body">
            Most health systems see you once a year, compare you to population averages,
            and hand you a number that means nothing without context.<br><br>
            <strong>Solvra is different.</strong> It builds a picture of <em>you</em> — your personal
            baselines, your patterns, your trajectory. Not what a 45-year-old looks like on average.
            What <em>you</em> look like when you are at your normal.<br><br>
            Over time, it learns what is stable, what is drifting, and what matters for your body
            specifically. It notices the slow changes that no single appointment ever catches.
            It gives you honest, plain-language explanations of what it sees — and it is always
            transparent about what it does not yet know.<br><br>
            This is not a wellness app. It is not a diagnostic tool. It is the health intelligence
            infrastructure you carry with you for life — and it starts building the moment
            you log your first measurement.
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("### Three things Solvra promises you")

        st.markdown("""
        <div class="pillar-card">
            <div class="pillar-title">🔒 Your data belongs to you. Always.</div>
            <div class="pillar-body">
                Everything you log is yours. You can export it, take it with you, or delete it at any time.
                Solvra will never sell it, share it, or use it for anything other than building your
                personal health picture. Your notes are private. Your record is portable.
            </div>
        </div>
        <div class="pillar-card">
            <div class="pillar-title">🛡️ Safety comes before everything else.</div>
            <div class="pillar-body">
                If your data shows something that warrants attention, Solvra will tell you clearly —
                and it will never let that alert be hidden or ignored. It will also always tell you
                what it does not know yet, and it will never pretend to be more certain than it is.
            </div>
        </div>
        <div class="pillar-card">
            <div class="pillar-title">🔍 You can always see why.</div>
            <div class="pillar-body">
                Every insight Solvra surfaces comes with an explanation — what data it is based on,
                how confident the system is, and what would make the picture clearer. No black box.
                No confident claims without evidence. Just honest intelligence you can actually use.
            </div>
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown("""
        <div class="welcome-body" style="text-align:center;">
            <strong>Your twin starts building the moment you log your first measurement.</strong><br>
            It will be simple at first — a record, then a baseline, then a trajectory.<br>
            The longer you use it, the more personal and capable it becomes.<br><br>
            It belongs to no one else. It never leaves you.
        </div>
        """, unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            if st.button("→  Enter Solvra", use_container_width=True, type="primary"):
                st.session_state.onboarded = True
                st.rerun()

        st.markdown("""
        <div class="welcome-disclaimer" style="text-align:center;">
            Solvra is not a medical device and does not diagnose or treat any condition.
            All outputs are for personal awareness only. Always consult a qualified healthcare
            provider for medical decisions.
        </div>
        """, unsafe_allow_html=True)


# ── SIDEBAR ───────────────────────────────────────────────────────────────────

def render_sidebar(kernel: SolvraKernel, store: SupabaseStore, user_id: str):
    st.sidebar.markdown("## 🧬 Solvra")
    st.sidebar.markdown("*Personal Health Intelligence*")
    st.sidebar.markdown("---")

    if store.connected:
        st.sidebar.success("✓ Connected to Supabase")
    else:
        st.sidebar.warning("⚡ Local mode — data not persisted\nAdd SUPABASE_URL and SUPABASE_KEY to enable persistence.")

    st.sidebar.markdown("---")
    st.sidebar.markdown("**Navigation**")
    page = st.sidebar.radio(
        "Go to",
        ["📥 Log Data", "📊 My Baselines", "📈 Trends", "🔔 Signals & Alerts", "🧬 My Twin", "🌱 Habits", "ℹ️ About Solvra"],
        label_visibility="collapsed"
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Solvra is not a medical device. It does not diagnose, "
        "treat, or replace clinical care. All outputs are for "
        "personal awareness only."
    )
    return page

# ── SECTION 1: LOG DATA ───────────────────────────────────────────────────────

def render_log_data(kernel: SolvraKernel, store: SupabaseStore, user_id: str):
    st.markdown('<p class="main-header">Log Today\'s Data</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Enter your measurements below. Each one contributes to your personal baseline.</p>', unsafe_allow_html=True)

    st.info(
        "📅 **Building your baseline:** Log 2–3 times per week for at least 14 days to establish "
        "your personal normal. You do not need to log every day — consistency over time matters "
        "more than frequency. Different signals have different natural rhythms: blood pressure and "
        "sleep can be logged daily, weight is best weekly, and fasting glucose only needs to be "
        "logged when you have a recent lab result or glucometer reading."
    )

    col1, col2 = st.columns(2)

    signals_left  = ["bp_systolic", "bp_diastolic", "heart_rate", "weight", "waist_circ", "spo2", "body_temp"]
    signals_right = ["sleep_hours", "sleep_quality", "activity_mins", "stress_level", "energy_level", "hrv", "glucose"]

    values = {}

    with col1:
        st.markdown("**Cardiovascular & Metabolic**")
        for sig in signals_left:
            label, unit, mn, mx, default = SIGNAL_LABELS[sig]
            help_text = SIGNAL_HELP.get(sig, "")
            if sig in ["sleep_quality", "stress_level", "energy_level"]:
                val = st.slider(f"{label} ({unit})", min_value=int(mn), max_value=int(mx), value=int(default), key=f"input_{sig}", help=help_text)
            else:
                val = st.number_input(f"{label} ({unit})", min_value=mn, max_value=mx, value=default, step=0.1, key=f"input_{sig}", help=help_text)
            values[sig] = (val, unit)

    with col2:
        st.markdown("**Sleep, Activity & Stress**")
        for sig in signals_right:
            label, unit, mn, mx, default = SIGNAL_LABELS[sig]
            help_text = SIGNAL_HELP.get(sig, "")
            if sig in ["sleep_quality", "stress_level", "energy_level"]:
                val = st.slider(f"{label} ({unit})", min_value=int(mn), max_value=int(mx), value=int(default), key=f"input_{sig}", help=help_text)
            else:
                val = st.number_input(f"{label} ({unit})", min_value=mn, max_value=mx, value=default, step=0.1, key=f"input_{sig}", help=help_text)
            values[sig] = (val, unit)

    st.markdown("---")
    notes = st.text_area(
        "Notes (optional)",
        placeholder="e.g. High stress this week, skipped exercise, ate late most nights...",
        height=80,
        help=(
            "These notes are yours — they are never shared with anyone unless you choose to share them. "
            "Use them whenever something is worth capturing — a stressful period, a lifestyle change, "
            "an illness, a life event, or anything that might explain why your readings look the way they do. "
            "The more honestly you describe what was going on, the better Solvra can understand "
            "the story behind your numbers over time. "
            "Useful context includes: emotional state (stressed, anxious, calm), sleep patterns (poor sleep, "
            "irregular schedule), food and drink (eating late, skipping meals, alcohol), physical state "
            "(illness, injury, new exercise routine), and life context (work pressure, relationship stress, travel). "
            "There is no judgment here. The more honest you are, the more useful your companion becomes."
        )
    )
    approximate = st.checkbox("Mark all as approximate", value=False,
        help="Check this if any of these values are estimates rather than direct measurements. Approximate readings are stored but given reduced weight in your baseline calculations.")

    col_btn, col_msg = st.columns([1, 3])
    with col_btn:
        if st.button("💾 Save Today's Data", use_container_width=True, type="primary"):
            ts = datetime.utcnow()
            saved   = 0
            alerts  = []

            for sig, (val, unit) in values.items():
                try:
                    result = kernel.ingest_measurement(
                        user_id     = user_id,
                        signal_id   = sig,
                        value       = float(val),
                        unit        = unit,
                        timestamp   = ts,
                        notes       = notes if notes else None,
                        approximate = approximate,
                    )
                    store.save_measurement(user_id, result.measurement)
                    for a in result.alerts:
                        store.save_alert(user_id, a)
                        alerts.append(a)
                    saved += 1
                except Exception as e:
                    st.warning(f"Could not save {sig}: {e}")

            if saved > 0:
                st.success(f"✓ {saved} measurements saved — {ts.strftime('%b %d, %Y %H:%M')} UTC")
                if alerts:
                    for a in alerts:
                        if a.severity == AlertSeverity.URGENT:
                            st.error(f"🚨 **{a.title}**\n\n{a.message}\n\n**{a.safe_next_step}**")
                        else:
                            st.warning(f"⚠️ **{a.title}**\n\n{a.message}")
                st.rerun()

# ── SECTION 2: MY BASELINES ───────────────────────────────────────────────────

def render_baselines(kernel: SolvraKernel, store: SupabaseStore, user_id: str):
    st.markdown('<p class="main-header">My Baselines</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Your personal normal — built from your own data, not population averages.</p>', unsafe_allow_html=True)

    load_measurements_into_kernel(kernel, store, user_id)

    any_baseline = False
    cols = st.columns(2)
    col_idx = 0

    for sig in SIGNAL_DEFINITIONS:
        measurements = kernel.ingestion.get_measurements(user_id, signal_id=sig)
        if not measurements:
            continue

        baselines = kernel.baseline.compute_baselines(user_id, sig, measurements)
        short_b   = baselines.get("short")
        mvl       = kernel.baseline.mvl_status(user_id, sig, measurements)
        label, unit, *_ = SIGNAL_LABELS.get(sig, (sig, "", 0, 0, 0))

        with cols[col_idx % 2]:
            if short_b:
                any_baseline = True
                color, icon = UNCERTAINTY_COLOR.get(short_b.uncertainty, ("#555", "⚪"))
                st.markdown(f"""
                <div class="metric-card">
                    <strong>{label}</strong><br/>
                    <span style="font-size:1.6rem; font-weight:800; color:#1B3A5C">
                        {short_b.value:.1f}
                    </span>
                    <span style="color:#555"> {unit}</span><br/>
                    <span style="color:{color}; font-size:0.85rem">
                        {icon} Uncertainty: {short_b.uncertainty.value.title()}
                    </span><br/>
                    <span style="font-size:0.8rem; color:#777">
                        Based on {short_b.measurement_count} readings over
                        {(short_b.window_end - short_b.window_start).days} days
                    </span>
                </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
                <div style="background:#F9F9F9; border-radius:8px; padding:1rem;
                            border-left:4px solid #CCCCCC; margin-bottom:0.5rem;">
                    <strong>{label}</strong><br/>
                    <span style="color:#888; font-size:0.9rem">
                        Building baseline...
                        {mvl.get('readings_have', 0)}/{mvl.get('readings_needed', '?')} readings,
                        {mvl.get('days_have', 0)}/{mvl.get('days_needed', '?')} days
                    </span>
                </div>
                """, unsafe_allow_html=True)
            col_idx += 1

    if not any_baseline:
        st.info("No baselines yet. Log data for at least 2 weeks to see your personal baselines.")

    # Context notes
    context_notes = kernel.get_baseline_context_notes(user_id)
    if context_notes:
        st.markdown("---")
        st.markdown("### 📋 Baseline Context")
        st.caption("These are one-time informational notes. They are not alerts or diagnoses.")
        for note in context_notes:
            st.markdown(f"""
            <div class="context-note">
                <strong>{note.signal_name}</strong><br/>
                {note.context_message}<br/>
                <span style="font-size:0.8rem; color:#555">
                    Source: {note.guideline_source}
                </span>
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"✓ Understood — {note.signal_name}", key=f"ack_note_{note.signal_id}"):
                kernel.acknowledge_baseline_context_note(user_id, note.signal_id)
                store.save_context_note(user_id, note)
                st.rerun()

# ── SECTION 3: TRENDS ─────────────────────────────────────────────────────────

def render_trends(kernel: SolvraKernel, store: SupabaseStore, user_id: str):
    st.markdown('<p class="main-header">Trends</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Your trajectory over time — personal baseline vs recent readings.</p>', unsafe_allow_html=True)

    load_measurements_into_kernel(kernel, store, user_id)

    available = []
    for sig in SIGNAL_DEFINITIONS:
        measurements = kernel.ingestion.get_measurements(user_id, signal_id=sig)
        if len(measurements) >= 2:
            available.append(sig)

    if not available:
        st.info("Log data for at least a few days to see trends.")
        return

    selected = st.selectbox(
        "Select signal",
        available,
        format_func=lambda s: SIGNAL_LABELS.get(s, (s,))[0]
    )

    measurements = kernel.ingestion.get_measurements(user_id, signal_id=selected)
    baselines    = kernel.baseline.compute_baselines(user_id, selected, measurements)
    short_b      = baselines.get("short")
    long_b       = baselines.get("long")
    label, unit, *_ = SIGNAL_LABELS.get(selected, (selected, "", 0, 0, 0))

    dates  = [m.timestamp for m in measurements if not m.is_deleted]
    values = [m.value     for m in measurements if not m.is_deleted]

    if not dates:
        st.info("No valid measurements for this signal.")
        return

    fig = go.Figure()

    # Raw readings
    fig.add_trace(go.Scatter(
        x=dates, y=values,
        mode="lines+markers",
        name="Your readings",
        line=dict(color="#2E75B6", width=2),
        marker=dict(size=6),
    ))

    # Rolling 7-day average
    if len(values) >= 3:
        window = 7
        rolling = []
        for i in range(len(values)):
            start = max(0, i - window + 1)
            rolling.append(sum(values[start:i+1]) / (i - start + 1))
        fig.add_trace(go.Scatter(
            x=dates, y=rolling,
            mode="lines",
            name="7-day average",
            line=dict(color="#1B3A5C", width=2, dash="dash"),
        ))

    # Baseline reference lines
    if short_b:
        fig.add_hline(
            y=short_b.value,
            line_dash="dot",
            line_color="#1F6B3A",
            annotation_text=f"Your baseline: {short_b.value:.1f}",
            annotation_position="bottom right",
        )

    if long_b and long_b.value != (short_b.value if short_b else 0):
        fig.add_hline(
            y=long_b.value,
            line_dash="dot",
            line_color="#BF6900",
            annotation_text=f"Long-term baseline: {long_b.value:.1f}",
            annotation_position="top right",
        )

    fig.update_layout(
        title=f"{label} over time",
        xaxis_title="Date",
        yaxis_title=f"{label} ({unit})",
        height=400,
        plot_bgcolor="white",
        paper_bgcolor="white",
        font=dict(family="Arial", size=13),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        margin=dict(l=40, r=40, t=60, b=40),
    )
    fig.update_xaxes(showgrid=True, gridcolor="#F0F0F0")
    fig.update_yaxes(showgrid=True, gridcolor="#F0F0F0")

    st.plotly_chart(fig, use_container_width=True)

    # Findings summary for this signal
    picture = kernel.get_signal_picture(user_id, selected)
    if picture.findings:
        st.markdown("**Detected patterns for this signal**")
        for f in picture.findings:
            icon = {"spike": "⚡", "sustained_drift": "📉", "volatility_shift": "〰️", "coverage_risk": "📭"}.get(f.finding_type.value, "•")
            confidence_pct = int(f.confidence * 100)
            st.markdown(f"""
            <div style="background:#F5F5F5; border-radius:6px; padding:0.75rem;
                        border-left:3px solid #2E75B6; margin-bottom:0.4rem;">
                {icon} <strong>{f.finding_type.value.replace('_', ' ').title()}</strong>
                <span style="font-size:0.8rem; color:#888;"> — {confidence_pct}% confidence</span><br/>
                <span style="font-size:0.9rem;">{f.description}</span>
            </div>
            """, unsafe_allow_html=True)

    # Plain-language explanation
    if picture.explanation:
        with st.expander("📄 Full explanation"):
            st.markdown(f"**What changed**\n{picture.explanation.what_changed}")
            st.markdown(f"**Why it might matter**\n{picture.explanation.why_it_might_matter}")
            st.markdown(f"**How confident we are**\n{picture.explanation.confidence_statement}")
            st.markdown(f"**What would help**\n{picture.explanation.what_is_missing}")
            st.markdown(f"**Safest next step**\n{picture.explanation.safest_next_step}")

# ── SECTION 4: SIGNALS & ALERTS ───────────────────────────────────────────────

def render_signals(kernel: SolvraKernel, store: SupabaseStore, user_id: str):
    st.markdown('<p class="main-header">Signals & Alerts</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Active alerts and detected patterns across all signals.</p>', unsafe_allow_html=True)

    load_measurements_into_kernel(kernel, store, user_id)

    alerts = kernel.get_alerts(user_id, include_acknowledged=False)

    if not alerts:
        st.success("✓ No active alerts. Everything looks stable.")
    else:
        urgent  = [a for a in alerts if a.severity == AlertSeverity.URGENT]
        monitor = [a for a in alerts if a.severity != AlertSeverity.URGENT]

        if urgent:
            st.markdown("### 🚨 Urgent Alerts")
            st.caption("These require your attention before continuing.")
            for a in urgent:
                st.markdown(f"""
                <div class="alert-urgent">
                    <strong>{a.title}</strong><br/>
                    {a.message}<br/><br/>
                    <strong>Next step:</strong> {a.safe_next_step}
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"✓ I have read this — {a.id[:8]}", key=f"ack_{a.id}"):
                    kernel.acknowledge_alert(user_id, a.id)
                    store.acknowledge_alert(user_id, a.id)
                    st.rerun()

        if monitor:
            st.markdown("### ⚠️ Monitor")
            for a in monitor:
                st.markdown(f"""
                <div class="alert-monitor">
                    <strong>{a.title}</strong><br/>
                    {a.message}<br/><br/>
                    <strong>Recommendation:</strong> {a.safe_next_step}
                </div>
                """, unsafe_allow_html=True)
                if st.button(f"✓ Noted — {a.id[:8]}", key=f"ack_{a.id}"):
                    kernel.acknowledge_alert(user_id, a.id)
                    store.acknowledge_alert(user_id, a.id)
                    st.rerun()

    # Cross-signal overview
    st.markdown("---")
    st.markdown("### All Signals — Current State")

    any_data = False
    for sig in SIGNAL_DEFINITIONS:
        measurements = kernel.ingestion.get_measurements(user_id, signal_id=sig)
        if not measurements:
            continue
        any_data = True
        picture = kernel.get_signal_picture(user_id, sig)
        label   = SIGNAL_LABELS.get(sig, (sig,))[0]

        band_color = {
            RiskBand.LOW_CONCERN:      "#1F6B3A",
            RiskBand.MONITOR:          "#BF6900",
            RiskBand.ELEVATED_CONCERN: "#C05000",
            RiskBand.HIGH_CONCERN:     "#C00000",
        }.get(picture.risk_band, "#555555")

        band_label = picture.risk_band.value.replace("_", " ").title() if picture.risk_band else "Monitoring"
        finding_count = len(picture.findings)

        st.markdown(f"""
        <div style="display:flex; align-items:center; padding:0.5rem 0;
                    border-bottom:1px solid #F0F0F0;">
            <div style="width:180px; font-weight:600;">{label}</div>
            <div style="width:160px; color:{band_color}; font-size:0.9rem;">● {band_label}</div>
            <div style="color:#777; font-size:0.85rem;">
                {f'{finding_count} pattern{"s" if finding_count != 1 else ""} detected' if finding_count else 'No patterns detected'}
            </div>
        </div>
        """, unsafe_allow_html=True)

    if not any_data:
        st.info("No data logged yet. Log measurements to see signal status.")

# ── SECTION 5: MY TWIN ────────────────────────────────────────────────────────

def render_twin(kernel: SolvraKernel, store: SupabaseStore, user_id: str):
    st.markdown('<p class="main-header">My Digital Twin</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Your personal health model — building from Day 1, growing more capable over time.</p>', unsafe_allow_html=True)

    load_measurements_into_kernel(kernel, store, user_id)
    status = kernel.get_digital_twin_status(user_id)

    phase_label, phase_icon = TWIN_PHASE_LABELS.get(
        status.overall_phase, ("Phase 1 — Personal Record", "📋")
    )

    st.markdown(f"""
    <div class="twin-phase">
        <span style="font-size:1.5rem;">{phase_icon}</span>
        <strong style="font-size:1.2rem; color:#4A235A;"> {phase_label}</strong><br/><br/>
        {status.maturity_message}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Phase by Signal")
    st.caption("Each signal builds independently. Your twin advances as data accumulates.")

    cols = st.columns(2)
    for i, (sig, phase) in enumerate(status.signals_in_phase.items()):
        label = SIGNAL_LABELS.get(sig, (sig,))[0]
        p_label, p_icon = TWIN_PHASE_LABELS.get(phase, ("Phase 1", "📋"))
        measurements = kernel.ingestion.get_measurements(user_id, signal_id=sig)
        count = len([m for m in measurements if not m.is_deleted])

        with cols[i % 2]:
            phase_color = {
                DigitalTwinPhase.PHASE_1_PERSONAL_RECORD:  "#888888",
                DigitalTwinPhase.PHASE_2_BASELINE_MODEL:   "#2E75B6",
                DigitalTwinPhase.PHASE_3_TRAJECTORY_MODEL: "#1F6B3A",
            }.get(phase, "#888888")

            st.markdown(f"""
            <div style="padding:0.6rem; border-radius:6px; border-left:3px solid {phase_color};
                        background:#FAFAFA; margin-bottom:0.4rem;">
                <strong>{label}</strong>
                <span style="float:right; color:{phase_color}; font-size:0.85rem;">
                    {p_icon} {p_label.split(' — ')[1]}
                </span><br/>
                <span style="font-size:0.8rem; color:#777;">
                    {count} reading{"s" if count != 1 else ""} logged
                </span>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### What Your Twin Is")
    st.markdown("""
    Your digital twin is not a feature — it is what Solvra is building from your first measurement.

    It starts as a personal record. As data accumulates it builds your personal baselines.
    As baselines mature it detects trajectories and meaningful changes.
    Eventually it will model the connections between your signals specific to you.

    Every measurement you log adds permanently to your twin — whether you log daily, weekly, or
    whenever you have a reading available. There is no obligation or schedule. Your twin accumulates
    your history at whatever pace fits your life.
    It belongs to you — completely and permanently.
    """)

    with st.expander("📤 Export my full health record"):
        if st.button("Generate export", key="export_btn"):
            export = kernel.export_state(user_id)
            st.json(export)
            st.caption("This is your complete portable health record. Download it, share it with your doctor, or transfer it.")

# ── SECTION 6: HABITS ────────────────────────────────────────────────────────

def render_habits(kernel, store, user_id: str):
    st.markdown('<p class="main-header">Habits</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Your lifestyle context — the background factors that shape what your numbers mean.</p>', unsafe_allow_html=True)

    st.info(
        "🧩 **Why habits matter:** Numbers alone do not tell the full story. A resting heart rate of 80 "
        "means something different for someone who smokes and works night shifts versus someone who exercises "
        "daily and sleeps well. Logging your habits gives Solvra the context to interpret your signals more "
        "accurately — and will power the correlation engine that connects your lifestyle choices to your "
        "health patterns over time."
    )

    tab1, tab2 = st.tabs(["📋 My Ongoing Habits", "🧪 Habit Experiments"])

    # ── TAB 1: ONGOING HABITS ─────────────────────────────────────────────────
    with tab1:
        st.markdown("### Current Lifestyle Habits")
        st.caption("Log your baseline lifestyle. Update this whenever something changes. This is not judged — it is context.")

        if "habits" not in st.session_state:
            st.session_state.habits = {}

        col1, col2 = st.columns(2)
        habit_keys = list(ONGOING_HABITS.keys())
        left_habits  = habit_keys[:len(habit_keys)//2 + 1]
        right_habits = habit_keys[len(habit_keys)//2 + 1:]

        with col1:
            for key in left_habits:
                label, icon, description = ONGOING_HABITS[key]
                if key in ["alcohol", "caffeine"]:
                    val = st.number_input(
                        f"{icon} {label}",
                        min_value=0, max_value=50 if key == "alcohol" else 20,
                        value=st.session_state.habits.get(key, 0),
                        help=description,
                        key=f"habit_{key}"
                    )
                elif key in ["smoking", "vaping", "recreational", "sedentary_work", "night_shift"]:
                    val = st.selectbox(
                        f"{icon} {label}",
                        ["No", "Yes", "Occasionally"],
                        index=["No", "Yes", "Occasionally"].index(st.session_state.habits.get(key, "No")),
                        help=description,
                        key=f"habit_{key}"
                    )
                else:
                    val = st.text_input(
                        f"{icon} {label}",
                        value=st.session_state.habits.get(key, ""),
                        help=description,
                        placeholder="Describe briefly...",
                        key=f"habit_{key}"
                    )
                st.session_state.habits[key] = val

        with col2:
            for key in right_habits:
                label, icon, description = ONGOING_HABITS[key]
                if key in ["alcohol", "caffeine"]:
                    val = st.number_input(
                        f"{icon} {label}",
                        min_value=0, max_value=50 if key == "alcohol" else 20,
                        value=st.session_state.habits.get(key, 0),
                        help=description,
                        key=f"habit_{key}"
                    )
                elif key in ["smoking", "vaping", "recreational", "sedentary_work", "night_shift"]:
                    val = st.selectbox(
                        f"{icon} {label}",
                        ["No", "Yes", "Occasionally"],
                        index=["No", "Yes", "Occasionally"].index(st.session_state.habits.get(key, "No")),
                        help=description,
                        key=f"habit_{key}"
                    )
                else:
                    val = st.text_input(
                        f"{icon} {label}",
                        value=st.session_state.habits.get(key, ""),
                        help=description,
                        placeholder="Describe briefly...",
                        key=f"habit_{key}"
                    )
                st.session_state.habits[key] = val

        st.markdown("---")
        additional = st.text_area(
            "Anything else worth noting about your lifestyle?",
            placeholder="e.g. Work from home, high-stress job, caregiver for a family member, recently moved, training for a race...",
            height=80,
            help="Any context about your daily life that might influence your health signals. The more honest context you provide, the more meaningful your health picture becomes over time."
        )

        if st.button("💾 Save Habit Profile", type="primary"):
            st.success("✓ Habit profile saved. This context will inform your health picture going forward.")

    # ── TAB 2: HABIT EXPERIMENTS ─────────────────────────────────────────────
    with tab2:
        st.markdown("### Habit Experiments")
        st.caption(
            "Start or stop a habit and let Solvra track what happens to your signals before and after. "
            "This is one of the most powerful features of longitudinal health tracking — seeing your own "
            "body's response to a specific change, in your own data."
        )

        st.markdown("#### Log a New Experiment")

        exp_col1, exp_col2 = st.columns(2)

        with exp_col1:
            exp_name = st.text_input(
                "What habit are you changing?",
                placeholder="e.g. Started walking 20 minutes daily",
                help="Be specific. 'Started exercising' is less useful than 'Started 20-minute morning walk before breakfast'.",
            )
            exp_type = st.selectbox(
                "Type of change",
                ["Starting a new habit", "Stopping an existing habit", "Modifying an existing habit"],
                help="Starting something new, stopping something, or changing how you do something you already do."
            )
            exp_category = st.selectbox("Category", HABIT_CATEGORIES)

        with exp_col2:
            exp_start = st.date_input(
                "Start date",
                value=datetime.utcnow().date(),
                help="When did you start or plan to start this change?"
            )
            exp_signals = st.multiselect(
                "Which signals do you expect this to affect?",
                options=list(SIGNAL_LABELS.keys()),
                format_func=lambda s: SIGNAL_LABELS.get(s, (s,))[0],
                help="Select the signals you think this habit change might influence. Solvra will pay attention to these signals in the weeks after your start date."
            )
            exp_notes = st.text_area(
                "Why are you making this change?",
                placeholder="e.g. My doctor mentioned my blood pressure has been creeping up. Trying to see if daily walks help.",
                height=80,
                help="Your intention and motivation. This becomes part of your permanent health record and gives context to whatever your data shows."
            )

        if st.button("🧪 Log This Experiment", type="primary"):
            if exp_name:
                if "experiments" not in st.session_state:
                    st.session_state.experiments = []

                experiment = {
                    "name":       exp_name,
                    "type":       exp_type,
                    "category":   exp_category,
                    "start_date": str(exp_start),
                    "signals":    exp_signals,
                    "notes":      exp_notes,
                    "logged_at":  datetime.utcnow().isoformat(),
                }
                st.session_state.experiments.append(experiment)
                st.success(f"✓ Experiment logged: {exp_name} starting {exp_start}. Keep logging your measurements — the pattern will become visible in your Trends over time.")
            else:
                st.warning("Please describe the habit you are changing.")

        # Show existing experiments
        if "experiments" in st.session_state and st.session_state.experiments:
            st.markdown("---")
            st.markdown("#### Active Experiments")
            for exp in reversed(st.session_state.experiments):
                signals_str = ", ".join([SIGNAL_LABELS.get(s,(s,))[0] for s in exp.get("signals", [])])
                st.markdown(f"""
                <div style="background:#F0F6FF; border-radius:8px; padding:1rem;
                            border-left:4px solid #2E75B6; margin-bottom:0.5rem;">
                    <strong>🧪 {exp['name']}</strong>
                    <span style="float:right; color:#777; font-size:0.85rem;">Started {exp['start_date']}</span><br/>
                    <span style="font-size:0.85rem; color:#555;">{exp['type']} · {exp['category']}</span><br/>
                    {f'<span style="font-size:0.85rem; color:#2E75B6;">Watching: {signals_str}</span><br/>' if signals_str else ""}
                    {f'<span style="font-size:0.85rem; color:#777;">{exp["notes"]}</span>' if exp.get("notes") else ""}
                </div>
                """, unsafe_allow_html=True)


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    kernel  = get_kernel()
    store   = get_store()
    user_id = get_user_id()

    # Show welcome screen until user clicks through
    if not get_onboarded():
        render_welcome()
        return

    # Load persisted data into kernel on each session start
    if "data_loaded" not in st.session_state:
        load_measurements_into_kernel(kernel, store, user_id)
        st.session_state.data_loaded = True

    page = render_sidebar(kernel, store, user_id)

    if page == "📥 Log Data":
        render_log_data(kernel, store, user_id)
    elif page == "📊 My Baselines":
        render_baselines(kernel, store, user_id)
    elif page == "📈 Trends":
        render_trends(kernel, store, user_id)
    elif page == "🔔 Signals & Alerts":
        render_signals(kernel, store, user_id)
    elif page == "🧬 My Twin":
        render_twin(kernel, store, user_id)
    elif page == "🌱 Habits":
        render_habits(kernel, store, user_id)
    elif page == "ℹ️ About Solvra":
        st.session_state.onboarded = False
        st.rerun()

if __name__ == "__main__":
    main()
