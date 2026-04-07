-- =============================================================================
-- PostgreSQL Tuning for DTSG ERP Multi-Tenant — Phase 1
-- =============================================================================
-- Run as superuser: psql -U postgres -f postgresql_tuning.sql
-- Then: SELECT pg_reload_conf();
-- =============================================================================

-- Increase max connections (default: 100)
-- With pgbouncer, PostgreSQL sees fewer connections than clients
ALTER SYSTEM SET max_connections = 200;

-- Shared buffers: 25% of available RAM (example: 4GB server → 1GB)
ALTER SYSTEM SET shared_buffers = '1GB';

-- Work memory per query (sorting, hashing)
ALTER SYSTEM SET work_mem = '16MB';

-- Maintenance work memory (vacuum, index creation)
ALTER SYSTEM SET maintenance_work_mem = '256MB';

-- Effective cache size: 75% of RAM (helps query planner)
ALTER SYSTEM SET effective_cache_size = '3GB';

-- WAL settings for write-heavy workloads
ALTER SYSTEM SET wal_buffers = '64MB';
ALTER SYSTEM SET checkpoint_completion_target = 0.9;

-- Connection handling
ALTER SYSTEM SET idle_in_transaction_session_timeout = '5min';
ALTER SYSTEM SET statement_timeout = '5min';

-- Lock timeout to prevent indefinite waits
ALTER SYSTEM SET lock_timeout = '30s';

-- Parallel query settings (PostgreSQL 10+)
ALTER SYSTEM SET max_parallel_workers_per_gather = 2;
ALTER SYSTEM SET max_parallel_workers = 4;

-- Schema-per-tenant optimization: increase search_path cache
ALTER SYSTEM SET search_path = '"$user",public';

-- Logging for slow queries
ALTER SYSTEM SET log_min_duration_statement = 1000;  -- Log queries >1s
ALTER SYSTEM SET log_statement = 'ddl';  -- Log schema changes only

-- =============================================================================
-- Phase 3: Read Replica Setup (run on PRIMARY only)
-- =============================================================================
-- Uncomment these when setting up streaming replication:
--
-- ALTER SYSTEM SET wal_level = replica;
-- ALTER SYSTEM SET max_wal_senders = 5;
-- ALTER SYSTEM SET wal_keep_size = '1GB';
-- ALTER SYSTEM SET hot_standby = on;
--
-- CREATE ROLE replica_user WITH REPLICATION LOGIN PASSWORD 'your_password';
-- =============================================================================

-- Apply changes (requires restart for some settings)
SELECT pg_reload_conf();
