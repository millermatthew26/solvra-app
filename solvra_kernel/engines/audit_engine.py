"""
Solvra Kernel — Audit & Integrity Engine
==========================================
Implements tamper-evident, append-only audit logging.
Spec Section 14 — Audit & Integrity Layer.
Spec Section 7.3 — Deletion & Audit Scar Rules.

Every significant system action produces an AuditEvent.
Events are hash-chained so tampering with any record
breaks the chain and is detectable.

Pillar 3 — Trust Through Verifiable Integrity:
  "The system must always be able to explain itself."
"""

import hashlib
import json
from datetime import datetime
from typing import List, Optional

from solvra_kernel.models.entities import AuditEvent, AuditEventType, Actor


class AuditEngine:
    """
    Manages the immutable, hash-chained audit log.

    In production: events are written to an append-only store
    (e.g. an immutable database table or write-once object storage).
    In this prototype: events are held in memory with chain verification.
    """

    def __init__(self):
        self._events: List[AuditEvent] = []

    # ── WRITING EVENTS ────────────────────────────────────────────────────────

    def record(
        self,
        event_type:  AuditEventType,
        actor:       Actor,
        entity_id:   str,
        entity_type: str,
        reason_code: Optional[str] = None,
        details:     Optional[str] = None,
    ) -> AuditEvent:
        """
        Create and store an immutable audit event.
        Computes hash incorporating the previous event's hash (chain).
        """
        previous_hash = self._events[-1].hash if self._events else None

        event = AuditEvent(
            event_type    = event_type,
            actor         = actor,
            entity_id     = entity_id,
            entity_type   = entity_type,
            reason_code   = reason_code,
            details       = details,
            previous_hash = previous_hash,
        )

        event.hash = self._compute_hash(event)
        self._events.append(event)
        return event

    # ── CHAIN VERIFICATION ────────────────────────────────────────────────────

    def verify_chain(self) -> bool:
        """
        Verify the entire audit chain is intact.
        Returns True if untampered, False if any break detected.
        Spec Section 14 — hash chaining requirement.
        """
        if not self._events:
            return True

        for i, event in enumerate(self._events):
            # Verify this event's hash is correct
            expected_hash = self._compute_hash(event)
            if event.hash != expected_hash:
                return False

            # Verify chain linkage
            if i > 0:
                expected_previous = self._events[i - 1].hash
                if event.previous_hash != expected_previous:
                    return False

        return True

    def _compute_hash(self, event: AuditEvent) -> str:
        """
        SHA-256 hash of the event's canonical fields.
        Deterministic — same inputs always produce same hash.
        """
        payload = {
            "id":            event.id,
            "event_type":    event.event_type.value,
            "actor":         event.actor.value,
            "entity_id":     event.entity_id,
            "entity_type":   event.entity_type,
            "reason_code":   event.reason_code,
            "details":       event.details,
            "previous_hash": event.previous_hash,
            "timestamp":     event.timestamp.isoformat(),
        }
        content = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(content.encode()).hexdigest()

    # ── QUERYING ──────────────────────────────────────────────────────────────

    def events_for_entity(self, entity_id: str) -> List[AuditEvent]:
        return [e for e in self._events if e.entity_id == entity_id]

    def events_for_user(self, user_id: str) -> List[AuditEvent]:
        """Return all events where entity_id starts with the user_id prefix."""
        return [e for e in self._events if e.details and user_id in e.details]

    def safety_events(self) -> List[AuditEvent]:
        """Return all safety-critical events — these are never erasable."""
        safety_types = {
            AuditEventType.ALERT_ISSUED,
            AuditEventType.ESCALATION_TRIGGERED,
            AuditEventType.THRESHOLD_TRIGGERED,
        }
        return [e for e in self._events if e.event_type in safety_types]

    def all_events(self) -> List[AuditEvent]:
        return list(self._events)
