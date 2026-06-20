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
-- Observability — pg_stat_statements (top-N slow-query analysis under load)
-- =============================================================================
-- Aggregates execution stats per normalised query so you can find the
-- heaviest statements during a traffic spike (calls, total/mean time, rows).
-- Pairs with the slow-query LOG above: the log catches individual >1s
-- queries; pg_stat_statements ranks the cumulative cost across all calls.
--
-- NOTE: shared_preload_libraries requires a FULL RESTART (not pg_reload_conf).
-- After the restart, enable the extension in EACH tenant database:
--     CREATE EXTENSION IF NOT EXISTS pg_stat_statements;
-- Then query the worst offenders:
--     SELECT calls, round(total_exec_time) ms, round(mean_exec_time,1) avg_ms,
--            rows, query
--       FROM pg_stat_statements ORDER BY total_exec_time DESC LIMIT 20;
ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
ALTER SYSTEM SET pg_stat_statements.max = 10000;
ALTER SYSTEM SET pg_stat_statements.track = 'all';

-- =============================================================================
-- Autovacuum — tuned for the write-hot ledger tables (JournalLine/Header)
-- =============================================================================
-- Defaults (scale_factor 0.2 / 0.1) let dead tuples and stale planner stats
-- accumulate on high-churn tables, degrading index scans and aggregates as a
-- tenant posts more journals. Vacuum/analyze sooner and with more workers.
ALTER SYSTEM SET autovacuum_max_workers = 4;
ALTER SYSTEM SET autovacuum_naptime = '20s';
ALTER SYSTEM SET autovacuum_vacuum_scale_factor = 0.05;   -- default 0.2 → vacuum ~4× sooner
ALTER SYSTEM SET autovacuum_analyze_scale_factor = 0.02;  -- default 0.1 → fresher planner stats
ALTER SYSTEM SET autovacuum_vacuum_cost_limit = 2000;     -- let autovacuum keep up under load

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
