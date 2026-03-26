"""
Shilu — Personal Health Intelligence
========================================
Streamlit interface for the Shilu Kernel v2.

Run locally:
    streamlit run app.py

Sections:
    1. Log Data       — enter today's health measurements
    2. My Baselines   — personal baseline per signal with uncertainty
    3. Trends         — charts showing trajectory over time
    4. Signals        — active findings, alerts, and context notes
    5. My Twin        — digital twin phase status across all signals
    6. Habits         — lifestyle context and habit experiments
    7. About Shilu    — what this system is and is not
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import streamlit as st
from datetime import datetime, timedelta
from typing import Optional
import plotly.graph_objects as go

from shilu_kernel.core.kernel import SolvraKernel
from shilu_kernel.models.entities import (
    SIGNAL_DEFINITIONS, UncertaintyLevel, AlertSeverity,
    RiskBand
)
from storage import SupabaseStore

# ── PAGE CONFIG ───────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Shilu",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="expanded",
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
        padding: 1rem; border-left: 4px solid #2ECC71;
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
    .stButton > button[kind="primary"] {
        background-color: #2ECC71;
        border-color: #2ECC71;
    }
    .stButton > button[kind="primary"]:hover {
        background-color: #27AE60;
        border-color: #27AE60;
    }
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
    return st.session_state.get("onboarded", False)

def get_user_id() -> str:
    if "user_id" not in st.session_state:
        st.session_state.user_id = "demo_user"
    return st.session_state.user_id

# ── SIGNAL DEFINITIONS ────────────────────────────────────────────────────────

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
    "glucose":       "Fasting blood glucose in mg/dL. This requires either a home glucometer or a recent lab result from your doctor. Only log when you have an actual reading — do not estimate.",
    "body_temp":     "Your resting body temperature in Fahrenheit. Use an oral thermometer when you are not exercising or ill for your baseline. Temperature is most useful for detecting changes from your personal normal.",
    "spo2":          "Blood oxygen saturation — the percentage of your red blood cells carrying oxygen. Measured with a pulse oximeter, a small clip device that fits on your fingertip. Available at pharmacies, or captured by Apple Watch, Garmin, and similar wearables.",
    "hrv":           "Heart Rate Variability (RMSSD) — the variation in time between heartbeats, measured in milliseconds (ms). Log the RMSSD value specifically — not a percentage score or wellness index. A higher number generally indicates better recovery and cardiovascular health. Compatible apps and devices: Welltory (find RMSSD in the detailed reading), Apple Watch, Garmin, Whoop, Oura Ring, or Polar chest strap. Take readings at the same time each day, ideally first thing in the morning before getting up.",
}

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

# Digital twin phases — derived from measurement counts per signal
TWIN_PHASE_LABELS = [
    ("Phase 1 — Personal Record",  "📋", 1),
    ("Phase 2 — Baseline Model",   "📊", 14),
    ("Phase 3 — Trajectory Model", "📈", 30),
    ("Phase 4 — Correlation",      "🔗", 90),
    ("Phase 5 — Simulation",       "🧬", 365),
]

def load_measurements_into_kernel(kernel: SolvraKernel, store: SupabaseStore, user_id: str):
    measurements = store.load_measurements(user_id)
    for m in measurements:
        kernel.ingestion._store.setdefault(user_id, {}).setdefault(m.signal_id, [])
        existing_ids = {x.id for x in kernel.ingestion._store[user_id][m.signal_id]}
        if m.id not in existing_ids:
            kernel.ingestion._store[user_id][m.signal_id].append(m)

def uncertainty_badge(level: UncertaintyLevel) -> str:
    color, icon = UNCERTAINTY_COLOR.get(level, ("#555", "⚪"))
    return f"{icon} {level.value.replace('_', ' ').title()}"

# ── WELCOME SCREEN ────────────────────────────────────────────────────────────

def render_welcome():
    st.markdown("""
    <style>
        [data-testid="stSidebar"] { display: none; }
        .welcome-hero { text-align: center; padding: 3rem 2rem 1rem 2rem; }
        .welcome-title {
            font-size: 4rem; font-weight: 900;
            color: #1A1A1A; letter-spacing: -1px; margin-bottom: 0.25rem;
        }
        .welcome-title span.dot { color: #2ECC71; }
        .welcome-tagline {
            font-size: 1.4rem; color: #2ECC71;
            font-style: italic; margin-bottom: 2.5rem;
        }
        .welcome-body {
            font-size: 1.05rem; color: #333;
            line-height: 1.8; max-width: 680px; margin: 0 auto;
        }
        .pillar-card {
            background: #F0F6FF; border-radius: 12px;
            padding: 1.2rem 1.5rem; border-left: 5px solid #2ECC71;
            margin-bottom: 1rem; text-align: left;
        }
        .pillar-title { font-weight: 700; color: #1B3A5C; font-size: 1rem; margin-bottom: 0.3rem; }
        .pillar-body { color: #444; font-size: 0.95rem; line-height: 1.6; }
        .welcome-disclaimer { font-size: 0.8rem; color: #999; margin-top: 1.5rem; font-style: italic; }
    </style>
    """, unsafe_allow_html=True)

    st.markdown("""
    <div class="welcome-hero">
        <div class="welcome-title">Sh<span class="dot">i</span>lu</div>
        <div class="welcome-tagline">Your personal health intelligence — for life.</div>
    </div>
    """, unsafe_allow_html=True)

    _, center, _ = st.columns([1, 3, 1])
    with center:
        st.markdown("""
        <div class="welcome-body">
            Most health systems see you once a year, compare you to population averages,
            and hand you a number that means nothing without context.<br><br>
            <strong>Shilu is different.</strong> It builds a picture of <em>you</em> — your personal
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
        st.markdown("### Three things Shilu promises you")

        st.markdown("""
        <div class="pillar-card">
            <div class="pillar-title">🔒 Your data belongs to you. Always.</div>
            <div class="pillar-body">
                Everything you log is yours. You can export it, take it with you, or delete it at any time.
                Shilu will never sell it, share it, or use it for anything other than building your
                personal health picture. Your notes are private. Your record is portable.
            </div>
        </div>
        <div class="pillar-card">
            <div class="pillar-title">🛡️ Safety comes before everything else.</div>
            <div class="pillar-body">
                If your data shows something that warrants attention, Shilu will tell you clearly —
                and it will never let that alert be hidden or ignored. It will also always tell you
                what it does not know yet, and it will never pretend to be more certain than it is.
            </div>
        </div>
        <div class="pillar-card">
            <div class="pillar-title">🔍 You can always see why.</div>
            <div class="pillar-body">
                Every insight Shilu surfaces comes with an explanation — what data it is based on,
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
            if st.button("→  Enter Shilu", use_container_width=True, type="primary"):
                st.session_state.onboarded = True
                st.rerun()

        st.markdown("""
        <div class="welcome-disclaimer" style="text-align:center;">
            Shilu is not a medical device and does not diagnose or treat any condition.
            All outputs are for personal awareness only. Always consult a qualified healthcare
            provider for medical decisions.
        </div>
        """, unsafe_allow_html=True)


# ── SIDEBAR ───────────────────────────────────────────────────────────────────

def render_sidebar(kernel: SolvraKernel, store: SupabaseStore, user_id: str):
    st.sidebar.markdown("## 🌿 Shilu")
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
        ["📥 Log Data", "📊 My Baselines", "📈 Trends", "🔔 Signals & Alerts", "🧬 My Twin", "🌱 Habits", "ℹ️ About Shilu"],
        label_visibility="collapsed"
    )

    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Shilu is not a medical device. It does not diagnose, "
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

    # ── AGE — set once, locked in for the session ─────────────────────────────
    if "profile_age" not in st.session_state:
        # First time — show setup prompt
        st.markdown("**👤 First, tell us your age**")
        st.caption("You only need to set this once. It will be remembered for every log entry this session.")
        age_setup_col1, age_setup_col2 = st.columns([1, 3])
        with age_setup_col1:
            age_input = st.selectbox(
                "Your age",
                options=list(range(18, 101)),
                index=12,
                label_visibility="collapsed",
                help="Your age helps Shilu apply the correct population reference ranges for your signals."
            )
        with age_setup_col2:
            st.markdown("<div style='padding-top:4px;'></div>", unsafe_allow_html=True)
            if st.button("✓ Set My Age", type="primary"):
                st.session_state.profile_age = age_input
                st.rerun()
        st.stop()  # Don't render the rest of the form until age is set

    else:
        # Age is locked in — show it with a small change link
        age = st.session_state.profile_age
        age_col1, age_col2 = st.columns([3, 1])
        with age_col1:
            st.markdown(
                f"<div style='padding:6px 0; color:#555; font-size:0.9rem;'>"
                f"👤 Age <strong style='color:#1B3A5C; font-size:1rem;'>{age}</strong> "
                f"— reference ranges calibrated for you.</div>",
                unsafe_allow_html=True
            )
        with age_col2:
            if st.button("Change age", type="secondary", use_container_width=True):
                del st.session_state.profile_age
                st.rerun()

    st.divider()
    values = {}

    # ── CARDIOVASCULAR ────────────────────────────────────────────────────────
    st.markdown("**❤️ Cardiovascular**")
    st.caption("Blood pressure, heart rate, oxygen saturation, and HRV.")
    col1, col2, col3 = st.columns(3)
    with col1:
        for sig in ["bp_systolic", "bp_diastolic"]:
            label, unit, mn, mx, default = SIGNAL_LABELS[sig]
            val = st.number_input(f"{label} ({unit})", min_value=mn, max_value=mx, value=None, step=0.1, key=f"input_{sig}", help=SIGNAL_HELP.get(sig, ""))
            values[sig] = (val, unit)
    with col2:
        for sig in ["heart_rate", "spo2"]:
            label, unit, mn, mx, default = SIGNAL_LABELS[sig]
            val = st.number_input(f"{label} ({unit})", min_value=mn, max_value=mx, value=None, step=0.1, key=f"input_{sig}", help=SIGNAL_HELP.get(sig, ""))
            values[sig] = (val, unit)
    with col3:
        label, unit, mn, mx, default = SIGNAL_LABELS["hrv"]
        val = st.number_input(f"{label} ({unit})", min_value=mn, max_value=mx, value=None, step=0.1, key="input_hrv", help=SIGNAL_HELP.get("hrv", ""))
        values["hrv"] = (val, unit)

    st.divider()

    # ── BODY ──────────────────────────────────────────────────────────────────
    st.markdown("**⚖️ Body**")
    st.caption("Weight, waist circumference, and body temperature.")
    col1, col2, col3 = st.columns(3)
    with col1:
        label, unit, mn, mx, default = SIGNAL_LABELS["weight"]
        val = st.number_input(f"{label} ({unit})", min_value=mn, max_value=mx, value=None, step=0.1, key="input_weight", help=SIGNAL_HELP.get("weight", ""))
        values["weight"] = (val, unit)
    with col2:
        label, unit, mn, mx, default = SIGNAL_LABELS["waist_circ"]
        val = st.number_input(f"{label} ({unit})", min_value=mn, max_value=mx, value=None, step=0.1, key="input_waist_circ", help=SIGNAL_HELP.get("waist_circ", ""))
        values["waist_circ"] = (val, unit)
    with col3:
        label, unit, mn, mx, default = SIGNAL_LABELS["body_temp"]
        val = st.number_input(f"{label} ({unit})", min_value=mn, max_value=mx, value=None, step=0.1, key="input_body_temp", help=SIGNAL_HELP.get("body_temp", ""))
        values["body_temp"] = (val, unit)

    st.divider()

    # ── SLEEP ─────────────────────────────────────────────────────────────────
    st.markdown("**😴 Sleep**")
    st.caption("How long and how well you slept.")
    col1, col2 = st.columns(2)
    with col1:
        label, unit, mn, mx, default = SIGNAL_LABELS["sleep_hours"]
        val = st.number_input(f"{label} ({unit})", min_value=mn, max_value=mx, value=None, step=0.1, key="input_sleep_hours", help=SIGNAL_HELP.get("sleep_hours", ""))
        values["sleep_hours"] = (val, unit)
    with col2:
        label, unit, mn, mx, default = SIGNAL_LABELS["sleep_quality"]
        skip_sq = st.checkbox("Did not rate sleep quality today", key="skip_sleep_quality")
        if not skip_sq:
            val = st.slider(f"{label} ({unit})", min_value=int(mn), max_value=int(mx), value=3, key="input_sleep_quality", help=SIGNAL_HELP.get("sleep_quality", ""))
            values["sleep_quality"] = (val, unit)

    st.divider()

    # ── ACTIVITY & STRESS ─────────────────────────────────────────────────────
    st.markdown("**🏃 Activity & Wellbeing**")
    st.caption("Physical activity, stress, and energy levels.")
    col1, col2, col3 = st.columns(3)
    with col1:
        label, unit, mn, mx, default = SIGNAL_LABELS["activity_mins"]
        val = st.number_input(f"{label} ({unit})", min_value=mn, max_value=mx, value=None, step=1.0, key="input_activity_mins", help=SIGNAL_HELP.get("activity_mins", ""))
        values["activity_mins"] = (val, unit)
    with col2:
        label, unit, mn, mx, default = SIGNAL_LABELS["stress_level"]
        skip_sl = st.checkbox("Skip stress rating today", key="skip_stress_level")
        if not skip_sl:
            val = st.slider(f"{label} ({unit})", min_value=int(mn), max_value=int(mx), value=3, key="input_stress_level", help=SIGNAL_HELP.get("stress_level", ""))
            values["stress_level"] = (val, unit)
    with col3:
        label, unit, mn, mx, default = SIGNAL_LABELS["energy_level"]
        skip_el = st.checkbox("Skip energy rating today", key="skip_energy_level")
        if not skip_el:
            val = st.slider(f"{label} ({unit})", min_value=int(mn), max_value=int(mx), value=3, key="input_energy_level", help=SIGNAL_HELP.get("energy_level", ""))
            values["energy_level"] = (val, unit)

    st.divider()

    # ── OPTIONAL ──────────────────────────────────────────────────────────────
    st.markdown("**🔬 Optional**")
    st.caption("Fasting glucose — only log when you have an actual reading from a glucometer or lab result.")
    col1, _ = st.columns([1, 2])
    with col1:
        label, unit, mn, mx, default = SIGNAL_LABELS["glucose"]
        val = st.number_input(f"{label} ({unit})", min_value=mn, max_value=mx, value=None, step=0.1, key="input_glucose", help=SIGNAL_HELP.get("glucose", ""))
        values["glucose"] = (val, unit)

    st.divider()

    # ── NOTES ─────────────────────────────────────────────────────────────────
    st.markdown("**📝 Notes**")
    notes = st.text_area(
        "Notes (optional)",
        placeholder="e.g. High stress this week, skipped exercise, ate late most nights...",
        height=100,
        help=(
            "These notes are yours — they are never shared with anyone unless you choose to share them. "
            "Use them whenever something is worth capturing — a stressful period, a lifestyle change, "
            "an illness, a life event, or anything that might explain why your readings look the way they do. "
            "Useful context: emotional state, sleep patterns, food and drink, physical state, life context. "
            "There is no judgment here. The more honest you are, the more useful your companion becomes."
        )
    )
    approximate = st.checkbox("Mark all as approximate", value=False,
        help="Check this if any of these values are estimates rather than direct measurements. Approximate readings are stored but given reduced weight in your baseline calculations.")

    st.divider()

    col_btn, _ = st.columns([1, 3])
    with col_btn:
        if st.button("💾 Save Today's Data", use_container_width=True, type="primary"):
            ts = datetime.utcnow()
            saved  = 0
            alerts = []

            for sig, (val, unit) in values.items():
                if val is None:
                    continue  # Skip signals the user did not measure
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
                # Store log entry in session history
                if "log_history" not in st.session_state:
                    st.session_state.log_history = []
                st.session_state.log_history.append({
                    "date": ts.strftime("%b %d, %Y"),
                    "time": ts.strftime("%H:%M UTC"),
                    "signals_logged": saved,
                    "age": age,
                })
                st.success(f"✅ Saved — {saved} measurement{'s' if saved > 1 else ''} recorded on {ts.strftime('%b %d, %Y at %H:%M UTC')}")
                if alerts:
                    for a in alerts:
                        if a.severity == AlertSeverity.URGENT:
                            st.error(f"🚨 **{a.title}**\n\n{a.message}\n\n**{a.safe_next_step}**")
                        else:
                            st.warning(f"⚠️ **{a.title}**\n\n{a.message}")

    # ── LOG HISTORY ───────────────────────────────────────────────────────────
    st.divider()
    st.markdown("**📋 Log History**")

    log_history = st.session_state.get("log_history", [])

    if not log_history:
        st.caption("No entries logged this session. Your history will appear here after your first save.")
    else:
        # Collapse entries by date — count entries and total signals per date
        from collections import defaultdict
        date_summary = defaultdict(lambda: {"entries": 0, "signals": 0, "times": []})
        for entry in log_history:
            d = entry["date"]
            date_summary[d]["entries"] += 1
            date_summary[d]["signals"] += entry["signals_logged"]
            date_summary[d]["times"].append(entry["time"])

        st.caption(f"{len(log_history)} log session{'s' if len(log_history) != 1 else ''} this session · {sum(e['signals_logged'] for e in log_history)} total measurements recorded")

        # Table header
        col_date, col_sessions, col_signals = st.columns([2, 1, 1])
        col_date.markdown("**Date**")
        col_sessions.markdown("**Sessions**")
        col_signals.markdown("**Measurements**")

        st.markdown("<hr style='margin:4px 0 8px 0; border-color:#E0E0E0;'>", unsafe_allow_html=True)

        for date, summary in sorted(date_summary.items(), reverse=True):
            col_date, col_sessions, col_signals = st.columns([2, 1, 1])
            col_date.markdown(f"📅 {date}")
            sessions_label = f"{summary['entries']}" if summary['entries'] == 1 else f"{summary['entries']} entries"
            col_sessions.markdown(sessions_label)
            col_signals.markdown(f"{summary['signals']}")

    # ── RESET DATA ────────────────────────────────────────────────────────────
    st.divider()
    st.markdown("**🗑️ Reset All Data**")
    st.caption(
        "This clears all measurements, baselines, alerts, and log history from this session. "
        "Since your data is stored in memory only, this is permanent for this session. "
        "Use this to start fresh with clean data."
    )

    confirm_reset = st.checkbox("I understand this will permanently clear all my data for this session", key="confirm_reset")
    if st.button("🗑️ Clear All Data and Start Fresh", disabled=not confirm_reset, type="secondary"):
        # Clear kernel data
        kernel = get_kernel()
        if hasattr(kernel, 'ingestion') and hasattr(kernel.ingestion, '_store'):
            kernel.ingestion._store.clear()
        if hasattr(kernel, 'baseline') and hasattr(kernel.baseline, '_cache'):
            kernel.baseline._cache.clear()

        # Clear store data
        store = get_store()
        if hasattr(store, '_measurements'):
            store._measurements.clear()
        if hasattr(store, '_alerts'):
            store._alerts.clear()

        # Clear all relevant session state
        for key in ["log_history", "experiments", "data_loaded", "confirm_reset", "profile_age"]:
            if key in st.session_state:
                del st.session_state[key]

        st.success("✅ All data cleared. You are starting fresh.")
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


    # Baseline context notes — reserved for Phase 2


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

    fig.add_trace(go.Scatter(
        x=dates, y=values,
        mode="lines+markers",
        name="Your readings",
        line=dict(color="#2ECC71", width=2),
        marker=dict(size=6),
    ))

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

    try:
        picture = kernel.get_signal_picture(user_id, selected)
    except AttributeError:
        picture = None
    if picture.findings:
        st.markdown("**Detected patterns for this signal**")
        for f in picture.findings:
            icon = {"spike": "⚡", "sustained_drift": "📉", "volatility_shift": "〰️", "coverage_risk": "📭"}.get(f.finding_type.value, "•")
            confidence_pct = int(f.confidence * 100)
            st.markdown(f"""
            <div style="background:#F5F5F5; border-radius:6px; padding:0.75rem;
                        border-left:3px solid #2ECC71; margin-bottom:0.4rem;">
                {icon} <strong>{f.finding_type.value.replace('_', ' ').title()}</strong>
                <span style="font-size:0.8rem; color:#888;"> — {confidence_pct}% confidence</span><br/>
                <span style="font-size:0.9rem;">{f.description}</span>
            </div>
            """, unsafe_allow_html=True)

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

    if alerts:
        st.markdown("### 🚨 Active Alerts")
        for a in alerts:
            css_class = "alert-urgent" if a.severity == AlertSeverity.URGENT else "alert-monitor"
            icon = "🚨" if a.severity == AlertSeverity.URGENT else "⚠️"
            st.markdown(f"""
            <div class="{css_class}">
                {icon} <strong>{a.title}</strong><br/>
                {a.message}<br/><br/>
                <strong>Recommendation:</strong> {a.safe_next_step}
            </div>
            """, unsafe_allow_html=True)
            if st.button(f"✓ Noted — {a.id[:8]}", key=f"ack_{a.id}"):
                kernel.acknowledge_alert(user_id, a.id)
                store.acknowledge_alert(user_id, a.id)
                st.rerun()

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

    # Derive twin phase from measurement counts — no kernel method needed
    all_counts = {}
    for sig in SIGNAL_DEFINITIONS:
        measurements = kernel.ingestion.get_measurements(user_id, signal_id=sig)
        all_counts[sig] = len([m for m in measurements if not m.is_deleted])

    total = sum(all_counts.values())
    max_count = max(all_counts.values()) if all_counts else 0

    # Determine overall phase from total readings
    overall_phase = TWIN_PHASE_LABELS[0]
    for phase in TWIN_PHASE_LABELS:
        if total >= phase[2]:
            overall_phase = phase

    phase_label, phase_icon, _ = overall_phase

    if total == 0:
        maturity_message = "Log your first measurement to begin building your twin."
    elif total < 14:
        maturity_message = f"Your twin is in its earliest stage — {total} readings logged. Keep going. Baselines need at least 14 readings across 7 days to begin forming."
    elif total < 30:
        maturity_message = f"Your personal baselines are forming — {total} readings logged. Your twin is learning what is normal for you specifically."
    elif total < 90:
        maturity_message = f"Your trajectory model is building — {total} readings logged. Your twin is beginning to detect meaningful patterns over time."
    else:
        maturity_message = f"Your twin is maturing — {total} readings logged. The longer you log, the more personal and accurate your picture becomes."

    st.markdown(f"""
    <div class="twin-phase">
        <span style="font-size:1.5rem;">{phase_icon}</span>
        <strong style="font-size:1.2rem; color:#4A235A;"> {phase_label}</strong><br/><br/>
        {maturity_message}
    </div>
    """, unsafe_allow_html=True)

    st.markdown("---")
    st.markdown("### Phase by Signal")
    st.caption("Each signal builds independently. Your twin advances as data accumulates.")

    cols = st.columns(2)
    for i, sig in enumerate(SIGNAL_DEFINITIONS):
        count = all_counts.get(sig, 0)
        label = SIGNAL_LABELS.get(sig, (sig,))[0]

        # Determine phase for this signal
        sig_phase = TWIN_PHASE_LABELS[0]
        for phase in TWIN_PHASE_LABELS:
            if count >= phase[2]:
                sig_phase = phase
        p_label, p_icon, _ = sig_phase

        phase_color = "#888888"
        if count >= 30:
            phase_color = "#1F6B3A"
        elif count >= 14:
            phase_color = "#2ECC71"
        elif count >= 1:
            phase_color = "#2E75B6"

        with cols[i % 2]:
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
    Your digital twin is not a feature — it is what Shilu is building from your first measurement.

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

# ── SECTION 6: HABITS ─────────────────────────────────────────────────────────

def render_habits(kernel, store, user_id: str):
    st.markdown('<p class="main-header">Habits</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Your lifestyle context — the background factors that shape what your numbers mean.</p>', unsafe_allow_html=True)

    st.info(
        "🧩 **Why habits matter:** Numbers alone do not tell the full story. A resting heart rate of 80 "
        "means something different for someone who smokes and works night shifts versus someone who exercises "
        "daily and sleeps well. Logging your habits gives Shilu the context to interpret your signals more "
        "accurately — and will power the correlation engine that connects your lifestyle choices to your "
        "health patterns over time."
    )

    tab1, tab2 = st.tabs(["📋 My Ongoing Habits", "🧪 Habit Experiments"])

    with tab1:
        st.markdown("### Current Lifestyle Habits")
        st.caption("Log your baseline lifestyle. Update this whenever something changes. This is not judged — it is context.")

        if "habits" not in st.session_state:
            st.session_state.habits = {}

        col1, col2 = st.columns(2)
        habit_keys   = list(ONGOING_HABITS.keys())
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

    with tab2:
        st.markdown("### Habit Experiments")
        st.caption(
            "Start or stop a habit and let Shilu track what happens to your signals before and after. "
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
                help="Select the signals you think this habit change might influence. Shilu will pay attention to these signals in the weeks after your start date."
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

        if "experiments" in st.session_state and st.session_state.experiments:
            st.markdown("---")
            st.markdown("#### Active Experiments")
            for exp in reversed(st.session_state.experiments):
                signals_str = ", ".join([SIGNAL_LABELS.get(s,(s,))[0] for s in exp.get("signals", [])])
                st.markdown(f"""
                <div style="background:#F0F6FF; border-radius:8px; padding:1rem;
                            border-left:4px solid #2ECC71; margin-bottom:0.5rem;">
                    <strong>🧪 {exp['name']}</strong>
                    <span style="float:right; color:#777; font-size:0.85rem;">Started {exp['start_date']}</span><br/>
                    <span style="font-size:0.85rem; color:#555;">{exp['type']} · {exp['category']}</span><br/>
                    {f'<span style="font-size:0.85rem; color:#2ECC71;">Watching: {signals_str}</span><br/>' if signals_str else ""}
                    {f'<span style="font-size:0.85rem; color:#777;">{exp["notes"]}</span>' if exp.get("notes") else ""}
                </div>
                """, unsafe_allow_html=True)


# ── MAIN ──────────────────────────────────────────────────────────────────────

# ── ABOUT ─────────────────────────────────────────────────────────────────────

def render_about():
    st.markdown('<p class="main-header">About Shilu</p>', unsafe_allow_html=True)
    st.divider()
    st.markdown("""
**Shilu** is a personal health intelligence system built on three non-negotiable pillars:

**🔒 Personal Ownership** — Your health data belongs to you permanently. Portable, exportable,
and yours regardless of what happens to any platform, provider, or insurer.

**🛡️ Safety Before Autonomy** — The safety architecture is non-bypassable. When something in your
data warrants attention, Shilu tells you. Always.

**🔍 Trust Through Verifiable Integrity** — Every insight Shilu produces is traceable to the
specific data that produced it. Full audit chain. No black boxes. No false certainty.

---

**What Shilu is not:**
- Not a diagnostic tool
- Not a replacement for clinical care
- Not a population-average health tracker

**What Shilu is:**
- A longitudinal record of your personal health signals
- A system that learns your normal — not the population's normal
- A companion that watches continuously and speaks honestly

---

*Shilu is a proof of concept. Version 0.1 — Matthew Miller, Founder*
    """)

def main():
    kernel  = get_kernel()
    store   = get_store()
    user_id = get_user_id()

    if not get_onboarded():
        render_welcome()
        return

    if "data_loaded" not in st.session_state:
        load_measurements_into_kernel(kernel, store, user_id)
        st.session_state.data_loaded = True

    # Sidebar — status and disclaimer only
    st.sidebar.markdown("## 🌿 Shilu")
    st.sidebar.markdown("*Personal Health Intelligence*")
    st.sidebar.markdown("---")
    if store.connected:
        st.sidebar.success("✓ Connected to Supabase")
    else:
        st.sidebar.warning("⚡ Local mode — data not persisted\nAdd SUPABASE_URL and SUPABASE_KEY to enable persistence.")
    st.sidebar.markdown("---")
    st.sidebar.caption(
        "Shilu is not a medical device. It does not diagnose, "
        "treat, or replace clinical care. All outputs are for "
        "personal awareness only."
    )
    if st.sidebar.button("← Back to Welcome"):
        st.session_state.onboarded = False
        st.rerun()

    # Main navigation — tabs across the top
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📥 Log Data",
        "📊 My Baselines",
        "📈 Trends",
        "🔔 Signals & Alerts",
        "🧬 My Twin",
        "🌱 Habits",
        "ℹ️ About Shilu"
    ])

    with tab1:
        render_log_data(kernel, store, user_id)
    with tab2:
        render_baselines(kernel, store, user_id)
    with tab3:
        render_trends(kernel, store, user_id)
    with tab4:
        render_signals(kernel, store, user_id)
    with tab5:
        render_twin(kernel, store, user_id)
    with tab6:
        render_habits(kernel, store, user_id)
    with tab7:
        render_about()

if __name__ == "__main__":
    main()
