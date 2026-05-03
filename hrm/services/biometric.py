"""Biometric event ingest + HMAC verification.

Public API:
    verify_signature(secret, body_bytes, signature_hex) -> bool
    ingest_event(device, payload, *, user=None) -> BiometricEvent
    project_to_attendance(event) -> Attendance | None
    haversine_distance_m(lat1, lon1, lat2, lon2) -> float

Flow:
    Device → POST JSON to webhook
    → verify_signature()
    → ingest_event() writes BiometricEvent row
    → project_to_attendance() upserts the Attendance row

Design rules:
    * HMAC is SHA-256 of the raw body using the device's secret.
    * Unknown device_user_id → store as 'unmatched', never crash.
    * Duplicate check: same (device, device_user_id, occurred_at) is a no-op.
    * First daily event is check_in; last is check_out. Hours = delta.
"""
from __future__ import annotations

import hmac
import hashlib
import logging
import math
from dataclasses import dataclass
from datetime import datetime, date
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class BiometricIngestError(Exception):
    """Raised for malformed payloads."""


@dataclass(frozen=True)
class IngestResult:
    """Immutable summary of a single ingest call."""

    event_id: int
    status: str           # matched / unmatched / duplicate / error
    attendance_id: Optional[int]
    employee_id: Optional[int]


# --------------------------------------------------------------------------- #
# Pure helpers — testable without Django
# --------------------------------------------------------------------------- #

def verify_signature(secret: str, body_bytes: bytes, signature_hex: str) -> bool:
    """Constant-time HMAC-SHA256 check.

    Returns False on any exception (bad hex, wrong length, missing secret)
    so the caller can treat it as a simple auth failure.
    """
    if not secret or not signature_hex:
        return False
    try:
        expected = hmac.new(
            secret.encode('utf-8'), body_bytes, hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature_hex.lower())
    except Exception:  # noqa: BLE001
        return False


def haversine_distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance between two WGS-84 points, in metres."""
    R = 6_371_000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


def _classify_event(event_type: str, existing_check_in: bool) -> str:
    """Decide how a raw event should flow into the Attendance record.

    Rules:
        * Explicit 'check_in'  → always check_in.
        * Explicit 'check_out' → always check_out.
        * Unspecified: first event of the day = check_in, subsequent = check_out.
    """
    if event_type == 'check_in':
        return 'check_in'
    if event_type == 'check_out':
        return 'check_out'
    return 'check_out' if existing_check_in else 'check_in'


# --------------------------------------------------------------------------- #
# Ingest
# --------------------------------------------------------------------------- #

def _parse_occurred_at(value) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, str):
        return datetime.fromisoformat(value.replace('Z', '+00:00'))
    raise BiometricIngestError(f'occurred_at must be ISO-8601 string; got {value!r}')


def _geofence_violation(device, payload_lat, payload_lng) -> Optional[str]:
    if not (device.geofence_latitude and device.geofence_longitude and device.geofence_radius_m):
        return None
    if payload_lat is None or payload_lng is None:
        return None
    d = haversine_distance_m(
        float(device.geofence_latitude), float(device.geofence_longitude),
        float(payload_lat), float(payload_lng),
    )
    if d > device.geofence_radius_m:
        return f'outside_geofence ({d:.0f}m > {device.geofence_radius_m}m)'
    return None


@transaction.atomic
def ingest_event(device, payload: dict, *, user=None):
    """Persist one raw event + enrich with employee / process status.

    Expected ``payload`` keys:
        event_type      (required) — check_in / check_out / enroll / …
        device_user_id  (required)
        occurred_at     (required) — ISO-8601
        latitude, longitude (optional)
        raw             (optional) — dict stored verbatim

    Returns the created :class:`hrm.models.BiometricEvent`.
    """
    from hrm.models import BiometricEnrollment, BiometricEvent

    event_type = payload.get('event_type')
    device_user_id = payload.get('device_user_id', '')
    occurred_at_raw = payload.get('occurred_at')
    if not event_type or not occurred_at_raw:
        raise BiometricIngestError('event_type and occurred_at are required.')

    occurred_at = _parse_occurred_at(occurred_at_raw)
    lat = payload.get('latitude')
    lng = payload.get('longitude')

    # Idempotent: reject duplicates of (device, user, ts).
    dupe = BiometricEvent.objects.filter(
        device=device, device_user_id=device_user_id, occurred_at=occurred_at,
    ).first()
    if dupe is not None:
        return dupe

    enrollment = (
        BiometricEnrollment.objects
        .filter(device=device, device_user_id=device_user_id, is_active=True)
        .select_related('employee')
        .first()
    )
    employee = enrollment.employee if enrollment else None

    process_status = 'matched' if employee else 'unmatched'
    notes = ''
    geofence_note = _geofence_violation(device, lat, lng)
    if geofence_note:
        process_status = 'error'
        notes = geofence_note

    event = BiometricEvent.objects.create(
        device=device,
        event_type=event_type,
        device_user_id=device_user_id,
        occurred_at=occurred_at,
        received_at=timezone.now(),
        latitude=lat,
        longitude=lng,
        employee=employee,
        process_status=process_status,
        processing_notes=notes,
        raw_payload=payload.get('raw', {}),
        created_by=user,
        updated_by=user,
    )
    device.last_seen_at = timezone.now()
    device.save(update_fields=['last_seen_at'])
    return event


# --------------------------------------------------------------------------- #
# Attendance projection
# --------------------------------------------------------------------------- #

@transaction.atomic
def project_to_attendance(event):
    """Upsert the :class:`Attendance` row for a matched event.

    * First event of the day → creates Attendance with check_in.
    * Subsequent event → updates check_out and recomputes work_hours.
    * No-op for unmatched / error events.
    """
    from hrm.models import Attendance

    if event.employee is None or event.process_status not in {'matched', 'pending'}:
        return None
    if event.event_type not in {'check_in', 'check_out'}:
        return None

    local_day: date = event.occurred_at.date()
    attendance, created = Attendance.objects.get_or_create(
        employee=event.employee, date=local_day,
        defaults={'status': 'Present', 'check_in': event.occurred_at},
    )

    existing_check_in = attendance.check_in is not None
    classified = _classify_event(event.event_type, existing_check_in)

    if classified == 'check_in':
        if attendance.check_in is None or event.occurred_at < attendance.check_in:
            attendance.check_in = event.occurred_at
    else:  # check_out
        if attendance.check_out is None or event.occurred_at > attendance.check_out:
            attendance.check_out = event.occurred_at

    if attendance.check_in and attendance.check_out:
        seconds = (attendance.check_out - attendance.check_in).total_seconds()
        hours = Decimal(str(round(seconds / 3600, 2)))
        attendance.work_hours = hours
        attendance.status = 'Present'

    attendance.save(update_fields=['check_in', 'check_out', 'work_hours', 'status'])
    return attendance
