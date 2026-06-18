"""Shared constants for the snapshots feature.

Centralises values that have to stay in sync across multiple modules
(e.g. the schema-name validation regex is enforced at the DB layer via
CheckConstraint, at the model layer in serializers, and at the dump
subprocess layer).
"""
from __future__ import annotations

import re

# PostgreSQL identifier rules: lowercase, digit-not-first, max 63 chars.
SCHEMA_NAME_PATTERN = r'^[a-z][a-z0-9_]{0,62}$'
SCHEMA_NAME_RE = re.compile(SCHEMA_NAME_PATTERN)
