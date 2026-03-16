"""
Solvra — Supabase Storage Adapter
====================================
Connects the kernel's in-memory stores to Supabase (PostgreSQL).

Usage:
    from storage import SupabaseStore
    store = SupabaseStore()
    store.save_measurement(user_id, measurement)
    measurements = store.load_measurements(user_id, signal_id)

Environment variables required (set in .env or Streamlit secrets):
    SUPABASE_URL   — your project URL from Supabase dashboard
    SUPABASE_KEY   — your anon/public key from Supabase dashboard

All writes are append-only.
Measurements are never updated — corrections create new rows.
Audit events are never updated or deleted.
"""

import os
import json
from datetime import datetime
from typing import List, Optional, Dict, Any

# Supabase client — installed via: pip install supabase
try:
    from supabase import create_client, Client
    SUPABASE_AVAILABLE = True
except ImportError:
    SUPABASE_AVAILABLE = False

from solvra_kernel.models.entities import (
    Measurement, DerivedFeature, Finding, Alert,
    BaselineContextNote, AuditEvent,
    SourceType, QualityFlag, UncertaintyLevel,
    AlertSeverity, EscalationLevel, FindingType,
    BaselineContextStatus, AuditEventType, Actor,
)


def _get_client() -> Optional["Client"]:
    """Create Supabase client from environment variables."""
    if not SUPABASE_AVAILABLE:
        return None
    url = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_KEY", "")
    if not url or not key:
        return None
    return create_client(url, key)


class SupabaseStore:
    """
    Persistent storage adapter for the Solvra kernel.

    Falls back to in-memory storage gracefully if Supabase is not
    configured — so the app works locally without credentials.
    """

    def __init__(self):
        self.client = _get_client()
        self.connected = self.client is not None

        # In-memory fallback stores (used when Supabase not configured)
        self._measurements:    Dict[str, List[Measurement]]          = {}
        self._baselines:       Dict[str, List[DerivedFeature]]        = {}
        self._findings:        Dict[str, List[Finding]]               = {}
        self._alerts:          Dict[str, List[Alert]]                 = {}
        self._context_notes:   Dict[str, Dict[str, BaselineContextNote]] = {}
        self._audit_events:    List[AuditEvent]                       = []

    # ── MEASUREMENTS ──────────────────────────────────────────────────────────

    def save_measurement(self, user_id: str, m: Measurement) -> bool:
        """Persist a measurement. Append-only — never updates existing rows."""
        if self.connected:
            try:
                row = {
                    "id":            m.id,
                    "user_id":       user_id,
                    "signal_id":     m.signal_id,
                    "value":         m.value,
                    "unit":          m.unit,
                    "timestamp":     m.timestamp.isoformat(),
                    "source_type":   m.source_type.value,
                    "entry_method":  m.entry_method,
                    "quality_flags": [f.value for f in m.quality_flags],
                    "notes":         m.notes,
                    "supersedes_id": m.supersedes_id,
                    "is_deleted":    m.is_deleted,
                    "created_at":    m.created_at.isoformat(),
                }
                self.client.table("measurements").insert(row).execute()
                return True
            except Exception as e:
                print(f"[Supabase] save_measurement error: {e}")
                return False
        else:
            key = f"{user_id}:{m.signal_id}"
            self._measurements.setdefault(key, []).append(m)
            return True

    def load_measurements(
        self, user_id: str, signal_id: Optional[str] = None
    ) -> List[Measurement]:
        """Load measurements for a user, optionally filtered by signal."""
        if self.connected:
            try:
                q = self.client.table("measurements") \
                    .select("*") \
                    .eq("user_id", user_id) \
                    .order("timestamp", desc=False)
                if signal_id:
                    q = q.eq("signal_id", signal_id)
                resp = q.execute()
                return [self._row_to_measurement(r) for r in resp.data]
            except Exception as e:
                print(f"[Supabase] load_measurements error: {e}")
                return []
        else:
            if signal_id:
                key = f"{user_id}:{signal_id}"
                return self._measurements.get(key, [])
            # Return all signals
            result = []
            for k, v in self._measurements.items():
                if k.startswith(f"{user_id}:"):
                    result.extend(v)
            return sorted(result, key=lambda m: m.timestamp)

    def mark_deleted(self, user_id: str, measurement_id: str) -> bool:
        """Logical delete — sets is_deleted flag, never removes the row."""
        if self.connected:
            try:
                self.client.table("measurements") \
                    .update({"is_deleted": True}) \
                    .eq("id", measurement_id) \
                    .eq("user_id", user_id) \
                    .execute()
                return True
            except Exception as e:
                print(f"[Supabase] mark_deleted error: {e}")
                return False
        else:
            for measurements in self._measurements.values():
                for m in measurements:
                    if m.id == measurement_id:
                        m.is_deleted = True
                        return True
            return False

    # ── ALERTS ────────────────────────────────────────────────────────────────

    def save_alert(self, user_id: str, alert: Alert) -> bool:
        if self.connected:
            try:
                row = {
                    "id":               alert.id,
                    "user_id":          user_id,
                    "severity":         alert.severity.value,
                    "title":            alert.title,
                    "message":          alert.message,
                    "safe_next_step":   alert.safe_next_step,
                    "uncertainty":      alert.uncertainty.value,
                    "escalation_level": alert.escalation_level.value if alert.escalation_level else None,
                    "acknowledged":     alert.acknowledged,
                    "acknowledged_at":  alert.acknowledged_at.isoformat() if alert.acknowledged_at else None,
                    "suppressible":     alert.suppressible,
                    "created_at":       alert.created_at.isoformat(),
                }
                self.client.table("alerts").insert(row).execute()
                return True
            except Exception as e:
                print(f"[Supabase] save_alert error: {e}")
                return False
        else:
            self._alerts.setdefault(user_id, []).append(alert)
            return True

    def load_alerts(self, user_id: str) -> List[Alert]:
        if self.connected:
            try:
                resp = self.client.table("alerts") \
                    .select("*") \
                    .eq("user_id", user_id) \
                    .order("created_at", desc=True) \
                    .execute()
                return [self._row_to_alert(r) for r in resp.data]
            except Exception as e:
                print(f"[Supabase] load_alerts error: {e}")
                return []
        else:
            return self._alerts.get(user_id, [])

    def acknowledge_alert(self, user_id: str, alert_id: str) -> bool:
        if self.connected:
            try:
                self.client.table("alerts") \
                    .update({
                        "acknowledged":    True,
                        "acknowledged_at": datetime.utcnow().isoformat()
                    }) \
                    .eq("id", alert_id) \
                    .eq("user_id", user_id) \
                    .execute()
                return True
            except Exception as e:
                print(f"[Supabase] acknowledge_alert error: {e}")
                return False
        else:
            for a in self._alerts.get(user_id, []):
                if a.id == alert_id:
                    a.acknowledged    = True
                    a.acknowledged_at = datetime.utcnow()
                    return True
            return False

    # ── BASELINE CONTEXT NOTES ────────────────────────────────────────────────

    def save_context_note(self, user_id: str, note: BaselineContextNote) -> bool:
        if self.connected:
            try:
                row = {
                    "id":                     note.id,
                    "user_id":                user_id,
                    "signal_id":              note.signal_id,
                    "signal_name":            note.signal_name,
                    "personal_baseline":      note.personal_baseline,
                    "personal_baseline_unit": note.personal_baseline_unit,
                    "population_normal_low":  note.population_normal_low,
                    "population_normal_high": note.population_normal_high,
                    "status":                 note.status.value,
                    "context_message":        note.context_message,
                    "guideline_source":       note.guideline_source,
                    "debate_note":            note.debate_note,
                    "acknowledged":           note.acknowledged,
                    "dormant":                note.dormant,
                    "created_at":             note.created_at.isoformat(),
                }
                self.client.table("baseline_context_notes") \
                    .upsert(row).execute()
                return True
            except Exception as e:
                print(f"[Supabase] save_context_note error: {e}")
                return False
        else:
            self._context_notes.setdefault(user_id, {})[note.signal_id] = note
            return True

    def load_context_notes(self, user_id: str) -> List[BaselineContextNote]:
        if self.connected:
            try:
                resp = self.client.table("baseline_context_notes") \
                    .select("*") \
                    .eq("user_id", user_id) \
                    .execute()
                return [self._row_to_context_note(r) for r in resp.data]
            except Exception as e:
                print(f"[Supabase] load_context_notes error: {e}")
                return []
        else:
            return list(self._context_notes.get(user_id, {}).values())

    # ── AUDIT EVENTS ──────────────────────────────────────────────────────────

    def save_audit_event(self, event: AuditEvent) -> bool:
        """Append-only. Never updates or deletes audit events."""
        if self.connected:
            try:
                row = {
                    "id":            event.id,
                    "event_type":    event.event_type.value,
                    "actor":         event.actor.value,
                    "entity_id":     event.entity_id,
                    "entity_type":   event.entity_type,
                    "reason_code":   event.reason_code,
                    "details":       event.details,
                    "previous_hash": event.previous_hash,
                    "hash":          event.hash,
                    "timestamp":     event.timestamp.isoformat(),
                }
                self.client.table("audit_events").insert(row).execute()
                return True
            except Exception as e:
                print(f"[Supabase] save_audit_event error: {e}")
                return False
        else:
            self._audit_events.append(event)
            return True

    # ── ROW CONVERTERS ────────────────────────────────────────────────────────

    def _row_to_measurement(self, r: dict) -> Measurement:
        return Measurement(
            id            = r["id"],
            user_id       = r["user_id"],
            signal_id     = r["signal_id"],
            value         = float(r["value"]),
            unit          = r["unit"],
            timestamp     = datetime.fromisoformat(r["timestamp"]),
            source_type   = SourceType(r["source_type"]),
            entry_method  = r["entry_method"],
            quality_flags = [QualityFlag(f) for f in (r.get("quality_flags") or [])],
            notes         = r.get("notes"),
            supersedes_id = r.get("supersedes_id"),
            is_deleted    = r.get("is_deleted", False),
            created_at    = datetime.fromisoformat(r["created_at"]),
        )

    def _row_to_alert(self, r: dict) -> Alert:
        return Alert(
            id               = r["id"],
            user_id          = r["user_id"],
            severity         = AlertSeverity(r["severity"]),
            title            = r["title"],
            message          = r["message"],
            safe_next_step   = r["safe_next_step"],
            uncertainty      = UncertaintyLevel(r["uncertainty"]),
            escalation_level = EscalationLevel(r["escalation_level"]) if r.get("escalation_level") else None,
            acknowledged     = r.get("acknowledged", False),
            acknowledged_at  = datetime.fromisoformat(r["acknowledged_at"]) if r.get("acknowledged_at") else None,
            suppressible     = r.get("suppressible", True),
            created_at       = datetime.fromisoformat(r["created_at"]),
        )

    def _row_to_context_note(self, r: dict) -> BaselineContextNote:
        return BaselineContextNote(
            id                       = r["id"],
            user_id                  = r["user_id"],
            signal_id                = r["signal_id"],
            signal_name              = r["signal_name"],
            personal_baseline        = float(r["personal_baseline"]),
            personal_baseline_unit   = r["personal_baseline_unit"],
            population_normal_low    = float(r["population_normal_low"]),
            population_normal_high   = float(r["population_normal_high"]),
            status                   = BaselineContextStatus(r["status"]),
            context_message          = r["context_message"],
            guideline_source         = r["guideline_source"],
            debate_note              = r.get("debate_note", ""),
            acknowledged             = r.get("acknowledged", False),
            dormant                  = r.get("dormant", False),
            created_at               = datetime.fromisoformat(r["created_at"]),
        )
