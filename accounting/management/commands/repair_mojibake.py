"""Repair U+FFFD replacement characters in reference-data names.

Why this exists
---------------
22 Chart-of-Accounts names in the OAG tenant contain U+FFFD ("�"),
e.g. ``Budget Augmentation � Derivation``, ``Fees � General``.
The usual cause is a cp1252 file read as UTF-8: byte 0x96 (en-dash) is
not valid UTF-8, so the decoder substitutes U+FFFD.

Important: that substitution is **lossy**. The original byte is gone, so
the true character cannot be recovered by re-decoding — it can only be
inferred. Every occurrence found here is the space-delimited ``" � "``
pattern, which in these names is a dash. This command therefore replaces
it with a plain ASCII hyphen: it reads the same, is unambiguous, and
cannot re-break on another encoding round-trip.

Because the corrupted names propagate into every report that prints an
account name, this is worth fixing at the source rather than papering
over it in the UI.

Usage
-----
    # show what would change, touch nothing (default)
    python manage.py repair_mojibake --schema=<tenant>

    # apply
    python manage.py repair_mojibake --schema=<tenant> --apply

    # every non-deleted tenant
    python manage.py repair_mojibake --all-tenants [--apply]
"""
from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError
from django_tenants.utils import schema_context

REPLACEMENT = "�"

# There is more than one corruption pattern, and they need opposite fixes.
# Position in the string is the only surviving evidence of what the
# original character was:
#
#   "Fees � General"      space-delimited  -> a dash
#   "Governor�s Office"   letter-adjacent  -> an apostrophe
#
# A single blanket substitution gets one of these wrong. A naive
# ``replace("�", "-")`` turns "Governor's Office" into
# "Governor-s Office", which is worse than leaving it corrupted.
#
# Anything matching neither pattern is deliberately left alone and
# reported, rather than guessed at.
SUBSTITUTIONS = [
    # dash between words, with or without surrounding spaces
    (re.compile(rf"\s+{REPLACEMENT}\s+"), " - "),
    # apostrophe inside a word: Governor|s, Peoples|
    (re.compile(rf"(?<=\w){REPLACEMENT}(?=\w)"), "'"),
    # trailing possessive: "Workers� Union"
    (re.compile(rf"(?<=\w){REPLACEMENT}(?=\s)"), "'"),
]

# (model label, field name) pairs to sweep.
TARGETS = [
    ("accounting.Account", "name"),
    ("accounting.MDA", "name"),
    ("accounting.Fund", "name"),
]


def _repair(text: str) -> str:
    """Apply only the substitutions whose pattern we can justify.

    Returns the text with recognised patterns fixed. Any remaining
    U+FFFD means the position gave no clue and the caller should report
    it rather than write a guess.
    """
    for pattern, good in SUBSTITUTIONS:
        text = pattern.sub(good, text)
    return text


class Command(BaseCommand):
    help = "Replace U+FFFD replacement characters in reference-data names."

    def add_arguments(self, parser):
        parser.add_argument(
            "--schema",
            help="Tenant schema to repair.",
        )
        parser.add_argument(
            "--all-tenants",
            action="store_true",
            help="Sweep every tenant that is not soft-deleted.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Actually write the changes. Without this the command "
                 "only reports what it would do.",
        )

    def handle(self, *args, **options):
        schema = options.get("schema")
        all_tenants = options.get("all_tenants")
        apply_changes = options.get("apply")

        if not schema and not all_tenants:
            raise CommandError("Pass --schema=<tenant> or --all-tenants.")

        if all_tenants:
            from tenants.models import Client
            schemas = [
                t.schema_name for t in Client.objects.all()
                if t.schema_name != "public"
                and not getattr(t, "is_deleted", False)
            ]
        else:
            schemas = [schema]

        if not apply_changes:
            self.stdout.write(self.style.WARNING(
                "DRY RUN — nothing will be written. Re-run with --apply."
            ))

        self.unresolved: list[tuple] = []
        grand_total = 0
        for schema_name in schemas:
            grand_total += self._repair_schema(schema_name, apply_changes)

        verb = "Repaired" if apply_changes else "Would repair"
        self.stdout.write(self.style.SUCCESS(
            f"\n{verb} {grand_total} record(s) across {len(schemas)} schema(s)."
        ))

        if self.unresolved:
            self.stdout.write(self.style.WARNING(
                f"\n{len(self.unresolved)} record(s) left unchanged because the "
                f"corruption pattern was unrecognised — fix these by hand:"
            ))
            for schema_name, label, identifier, text in self.unresolved:
                self.stdout.write(f"  {schema_name} {label} {identifier}: {text!r}")

    def _repair_schema(self, schema_name: str, apply_changes: bool) -> int:
        from django.apps import apps

        self.stdout.write(f"\n=== {schema_name} ===")
        changed = 0

        with schema_context(schema_name):
            for label, field in TARGETS:
                try:
                    model = apps.get_model(label)
                except LookupError:
                    self.stdout.write(f"  {label}: model not found, skipped")
                    continue

                rows = model.objects.filter(**{f"{field}__contains": REPLACEMENT})
                count = rows.count()
                if not count:
                    continue

                self.stdout.write(f"  {label}.{field}: {count} affected")
                for row in rows:
                    before = getattr(row, field)
                    after = _repair(before)
                    identifier = getattr(row, "code", None) or row.pk

                    if REPLACEMENT in after:
                        # Position gave no clue. Writing a guess here could
                        # corrupt the name further, so skip and surface it.
                        self.stdout.write(self.style.WARNING(
                            f"    {identifier}: {before!r} — UNRECOGNISED "
                            f"pattern, left unchanged"
                        ))
                        self.unresolved.append((schema_name, label, identifier, before))
                        continue

                    self.stdout.write(f"    {identifier}: {before!r} -> {after!r}")
                    if apply_changes:
                        setattr(row, field, after)
                        row.save(update_fields=[field])
                    changed += 1

        if not changed:
            self.stdout.write("  nothing to repair")
        return changed
