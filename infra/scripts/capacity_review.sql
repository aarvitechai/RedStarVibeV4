-- Phase 8 scale-readiness review (Execution Plan §14 Phase 8). Read-only apart from creating the stats extension.
--   docker compose exec -T db psql -U rsv -d rsv -f - < infra/scripts/capacity_review.sql
-- Reset counters before a load test with: SELECT pg_stat_statements_reset();
\pset footer off
CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

\echo '== Top 10 queries by total time'
SELECT calls, round(total_exec_time)::bigint AS total_ms, round(mean_exec_time::numeric, 2) AS mean_ms,
       round(max_exec_time::numeric, 1) AS max_ms, rows,
       left(regexp_replace(query, '\s+', ' ', 'g'), 110) AS query
FROM pg_stat_statements WHERE dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY total_exec_time DESC LIMIT 10;

\echo '== Slowest queries by mean time (called at least 20 times)'
SELECT calls, round(mean_exec_time::numeric, 2) AS mean_ms, left(regexp_replace(query, '\s+', ' ', 'g'), 120) AS query
FROM pg_stat_statements WHERE calls >= 20 AND dbid = (SELECT oid FROM pg_database WHERE datname = current_database())
ORDER BY mean_exec_time DESC LIMIT 10;

\echo '== Buffer cache hit rate (target > 99%)'
SELECT round(100.0 * sum(blks_hit) / nullif(sum(blks_hit) + sum(blks_read), 0), 2) AS cache_hit_pct,
       sum(deadlocks) AS deadlocks, sum(temp_bytes) AS temp_bytes
FROM pg_stat_database WHERE datname = current_database();

\echo '== Lock waits right now'
SELECT wait_event_type, wait_event, state, count(*) FROM pg_stat_activity
WHERE datname = current_database() AND pid <> pg_backend_pid() GROUP BY 1, 2, 3 ORDER BY 4 DESC;

\echo '== Connections in use vs max'
SELECT count(*) AS connections, current_setting('max_connections')::int AS max_connections FROM pg_stat_activity;

\echo '== Largest tables (with indexes)'
SELECT n.nspname || '.' || c.relname AS table, pg_size_pretty(pg_total_relation_size(c.oid)) AS total,
       pg_size_pretty(pg_indexes_size(c.oid)) AS indexes, c.reltuples::bigint AS approx_rows
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE c.relkind IN ('r', 'p') AND n.nspname NOT IN ('pg_catalog', 'information_schema')
ORDER BY pg_total_relation_size(c.oid) DESC LIMIT 10;

\echo '== Tables read mostly by sequential scan (possible missing index)'
SELECT schemaname || '.' || relname AS table, seq_scan, seq_tup_read, idx_scan, n_live_tup
FROM pg_stat_user_tables WHERE seq_scan > 50 AND n_live_tup > 1000 AND seq_tup_read > 10 * coalesce(idx_scan, 0)
ORDER BY seq_tup_read DESC LIMIT 10;

\echo '== Indexes never used since stats reset (review before dropping)'
SELECT s.schemaname || '.' || s.indexrelname AS index, pg_size_pretty(pg_relation_size(s.indexrelid)) AS size
FROM pg_stat_user_indexes s JOIN pg_index i ON i.indexrelid = s.indexrelid
WHERE s.idx_scan = 0 AND NOT i.indisunique AND NOT i.indisprimary
ORDER BY pg_relation_size(s.indexrelid) DESC LIMIT 10;

\echo '== Outbox and dead letters'
SELECT count(*) FILTER (WHERE published_at IS NULL) AS outbox_pending,
       coalesce(extract(epoch FROM now() - min(created_at) FILTER (WHERE published_at IS NULL)), 0)::int AS oldest_pending_s
FROM notify.outbox;

SELECT count(*) AS dead_letters FROM notify.dead_letter;
