"""Make the posted-journal balance guard case-insensitive.

Follow-up to 0111. The original trigger only matched ``status = 'Posted'``
exactly. Some legacy/forked paths stamped the JournalHeader with
``status='POSTED'`` (all-caps), which (a) bypassed the balance guard and
(b) was invisible to every ``status='Posted'`` report/query. The sibling
models (AssetRevaluationRun, RevenueCollection, AllocationRun, …) actually
*store* ``'POSTED'`` as their posted value, so the case difference is easy
to get wrong on the JournalHeader itself.

This migration replaces the trigger function so the balance check fires for
ANY posted spelling (LOWER(status) = 'posted'), guaranteeing double-entry
enforcement for every transaction regardless of how the status string was
written. The balance-only (debit = credit) check is preserved; we do NOT
add a zero-line guard because non-atomic header-first creators
(seed_demo_gl, manual JV drafts) legitimately commit a header before its
lines and must not be rejected.

Safe to re-run / reversible (mirrors 0111).
"""
from django.db import migrations


SQL = """
CREATE OR REPLACE FUNCTION prevent_unbalanced_posted_journal()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_debit  numeric;
    v_credit numeric;
BEGIN
    -- Enforce double-entry for ANY posted journal regardless of case
    -- ('Posted', 'POSTED', 'posted', …). Case-insensitive so a legacy
    -- path that stamped status='POSTED' cannot bypass the balance guard.
    IF NEW.status IS NULL OR LOWER(NEW.status) <> 'posted' THEN
        RETURN NEW;
    END IF;

    SELECT COALESCE(SUM(debit), 0), COALESCE(SUM(credit), 0)
      INTO v_debit, v_credit
      FROM accounting_journalline
      WHERE header_id = NEW.id;

    IF v_debit <> v_credit THEN
        RAISE EXCEPTION
          'IPSAS-INTEGRITY: journal % is unbalanced (debit=% credit=%)',
          NEW.id, v_debit, v_credit;
    END IF;

    RETURN NEW;
END;
$$;

DROP TRIGGER IF EXISTS trg_journal_balanced ON accounting_journalheader;

CREATE CONSTRAINT TRIGGER trg_journal_balanced
    AFTER INSERT OR UPDATE ON accounting_journalheader
    DEFERRABLE INITIALLY DEFERRED
    FOR EACH ROW
    EXECUTE FUNCTION prevent_unbalanced_posted_journal();
"""

REVERSE_SQL = """
DROP TRIGGER IF EXISTS trg_journal_balanced ON accounting_journalheader;
DROP FUNCTION IF EXISTS prevent_unbalanced_posted_journal();
"""


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0111_journal_balance_guard'),
    ]

    replaces = []

    operations = [
        migrations.RunSQL(SQL, REVERSE_SQL),
    ]
