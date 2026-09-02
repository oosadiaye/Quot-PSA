"""DB-level guarantee that a Posted journal is double-entry balanced.

Background
----------
Application code enforces balance via ``BasePostingService.assert_balanced``
and the canonical ``IPSASJournalService.post_journal`` path. However,
forked/legacy paths historically set ``status='Posted'`` directly and
skipped the balance check (see cost_allocation / currency_revaluation
"ghost journal" defects). A DB-level constraint closes that gap for
every path, including raw-SQL and future code, so an unbalanced Posted
journal can never be committed.

Design
------
- ``DEFERRABLE INITIALLY DEFERRED`` so it fires at transaction end, after
  the journal lines are inserted in the same transaction (matches how
  ``post_journal`` writes lines then flips status).
- Only checks rows whose new status is ``Posted`` — Draft/Pending journals
  are unaffected, so normal drafting flows are not blocked.
- Runs per tenant schema (django-tenants executes migrations in each
  tenant schema), so the guard exists everywhere business data lives.

Safe to re-run / reversible.
"""
from django.db import migrations


SQL = """
CREATE OR REPLACE FUNCTION prevent_unbalanced_posted_journal()
RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    v_debit  numeric;
    v_credit numeric;
BEGIN
    IF NEW.status <> 'Posted' THEN
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
        ('accounting', '0110_budget_rule_strict_default'),
    ]

    replaces = []

    operations = [
        migrations.RunSQL(SQL, REVERSE_SQL),
    ]
