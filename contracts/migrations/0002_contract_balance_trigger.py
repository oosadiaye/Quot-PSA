"""
Migration 0002 — PostgreSQL trigger for ContractBalance invariants.

This trigger is the *deepest* defence layer.  Even if the Python service
layer is bypassed (e.g. a direct DB UPDATE), the trigger fires BEFORE UPDATE
and raises a SQLSTATE '23514' (check_violation) exception for any of:

  1. cumulative_gross_paid > cumulative_gross_certified
  2. cumulative_gross_certified + pending_voucher_amount > contract_ceiling
  3. mobilization_recovered > mobilization_paid
  4. retention_released > retention_held
  5. version not strictly increasing (optimistic locking guard)

It also provides:
  6. Partial index on InterimPaymentCertificate.integrity_hash
     (unique across non-rejected IPCs) to prevent duplicate payment.

These SQL objects are per-tenant (applied inside each schema by
django-tenants' migrate --tenant flow).
"""
from django.db import migrations

# ── Trigger SQL ────────────────────────────────────────────────────────

CREATE_TRIGGER_FN = """
CREATE OR REPLACE FUNCTION contracts_balance_guard()
RETURNS TRIGGER
LANGUAGE plpgsql
AS $$
BEGIN
    -- 1. Paid cannot exceed certified
    IF NEW.cumulative_gross_paid > NEW.cumulative_gross_certified THEN
        RAISE EXCEPTION
            'CONTRACT_BALANCE_INVARIANT [contract=%]: '
            'cumulative_gross_paid (%) > cumulative_gross_certified (%)',
            NEW.contract_id,
            NEW.cumulative_gross_paid,
            NEW.cumulative_gross_certified
        USING ERRCODE = 'check_violation';
    END IF;

    -- 2. Certified + pending cannot exceed ceiling
    IF (NEW.cumulative_gross_certified + NEW.pending_voucher_amount) > NEW.contract_ceiling THEN
        RAISE EXCEPTION
            'CONTRACT_BALANCE_INVARIANT [contract=%]: '
            'cumulative_gross_certified (%) + pending_voucher_amount (%) > contract_ceiling (%)',
            NEW.contract_id,
            NEW.cumulative_gross_certified,
            NEW.pending_voucher_amount,
            NEW.contract_ceiling
        USING ERRCODE = 'check_violation';
    END IF;

    -- 3. Mobilization recovered cannot exceed mobilization paid
    IF NEW.mobilization_recovered > NEW.mobilization_paid THEN
        RAISE EXCEPTION
            'CONTRACT_BALANCE_INVARIANT [contract=%]: '
            'mobilization_recovered (%) > mobilization_paid (%)',
            NEW.contract_id,
            NEW.mobilization_recovered,
            NEW.mobilization_paid
        USING ERRCODE = 'check_violation';
    END IF;

    -- 4. Retention released cannot exceed retention held
    IF NEW.retention_released > NEW.retention_held THEN
        RAISE EXCEPTION
            'CONTRACT_BALANCE_INVARIANT [contract=%]: '
            'retention_released (%) > retention_held (%)',
            NEW.contract_id,
            NEW.retention_released,
            NEW.retention_held
        USING ERRCODE = 'check_violation';
    END IF;

    -- 5. Optimistic lock: version must strictly increase on UPDATE
    IF TG_OP = 'UPDATE' AND NEW.version <= OLD.version THEN
        RAISE EXCEPTION
            'CONTRACT_BALANCE_VERSION [contract=%]: '
            'version must strictly increase (old=%, new=%)',
            NEW.contract_id,
            OLD.version,
            NEW.version
        USING ERRCODE = 'check_violation';
    END IF;

    RETURN NEW;
END;
$$;
"""

CREATE_TRIGGER = """
DROP TRIGGER IF EXISTS trg_contracts_balance_guard
    ON contracts_contractbalance;

CREATE TRIGGER trg_contracts_balance_guard
    BEFORE INSERT OR UPDATE
    ON contracts_contractbalance
    FOR EACH ROW
    EXECUTE FUNCTION contracts_balance_guard();
"""

DROP_TRIGGER = """
DROP TRIGGER IF EXISTS trg_contracts_balance_guard
    ON contracts_contractbalance;
DROP FUNCTION IF EXISTS contracts_balance_guard();
"""

# ── Partial unique index on IPC integrity_hash ────────────────────────
# Prevents duplicate payment for the same (contract, period, cumulative)
# combination across non-rejected IPCs.

CREATE_IPC_HASH_INDEX = """
CREATE UNIQUE INDEX IF NOT EXISTS
    contracts_ipc_unique_active_hash
ON contracts_interimpaymentcertificate (integrity_hash)
WHERE status NOT IN ('REJECTED', 'DRAFT');
"""

DROP_IPC_HASH_INDEX = """
DROP INDEX IF EXISTS contracts_ipc_unique_active_hash;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("contracts", "0001_initial_contract_models"),
    ]

    operations = [
        migrations.RunSQL(
            sql=CREATE_TRIGGER_FN + CREATE_TRIGGER,
            reverse_sql=DROP_TRIGGER,
            hints={"contract_balance_guard_trigger": True},
        ),
        migrations.RunSQL(
            sql=CREATE_IPC_HASH_INDEX,
            reverse_sql=DROP_IPC_HASH_INDEX,
            hints={"ipc_integrity_hash_unique_index": True},
        ),
    ]
