# v0.8 — SQL & PL/pgSQL: The Database Layer Every SRE Lives In
⏱ **Estimated time: 3–5 hours**

---

## What this version is about

You already use PL/SQL at work every day. That experience is an asset — the concepts translate almost directly to PostgreSQL, which is the database AOIS runs on from v4 onward. This version gives you the foundation to query AOIS data directly, write stored functions, understand why queries go slow, and diagnose database issues the way a production SRE would.

Two dialects are in play:
- **Oracle PL/SQL** — what you use at work. Stored procedures, packages, cursors, DBMS_OUTPUT.
- **PostgreSQL PL/pgSQL** — what AOIS runs on. Similar structure, different syntax in specific places.

Where they differ, both sides are shown. By the end you have one mental model that works in either environment.

---

## Prerequisites

- v0.1 (Linux) complete — you need psql and shell comfort
- v0.4 (Docker) complete — you will spin up a local Postgres container
- v0.5 (Python) complete — one exercise connects Python to Postgres

Verify Docker is running:
```bash
docker info --format '{{.ServerVersion}}'
```
Expected output:
```
27.x.x
```

Verify psql is available (it comes with the Docker image — you do not need to install it locally):
```bash
docker run --rm postgres:16-alpine psql --version
```
Expected output:
```
psql (PostgreSQL) 16.x
```

---

## Learning Goals

By the end you will be able to:

- Write the SQL an SRE reaches for every day: SELECT with filters, JOINs across tables, aggregations, GROUP BY, ORDER BY, LIMIT
- Build readable complex queries using CTEs instead of nested subqueries
- Read EXPLAIN ANALYZE output and identify what is slow and why
- Know when to add an index and when not to
- Write a PL/pgSQL function and call it from psql
- Write a PL/pgSQL procedure with transaction control
- Translate Oracle PL/SQL syntax to PL/pgSQL confidently
- Query pg_stat_activity and pg_locks — the two views every DBA and SRE opens first during an incident
- Connect Python (psycopg2) to Postgres — the same pattern AOIS uses internally

---

## Spin Up Your Local Postgres

You will run Postgres in a container for all exercises in this version. This is exactly the setup used in v4's Docker Compose.

```bash
docker run -d \
  --name aois-pg \
  -e POSTGRES_PASSWORD=aoisdev \
  -e POSTGRES_DB=aois \
  -p 5432:5432 \
  postgres:16-alpine
```

Wait 3 seconds for the container to initialise, then connect:

```bash
docker exec -it aois-pg psql -U postgres -d aois
```

Expected prompt:
```
psql (16.x)
Type "help" for help.

aois=#
```

You are now in a live Postgres shell. `\q` exits. `\?` lists psql commands. `\h SELECT` shows SQL help.

---

## Part 1 — SQL Fundamentals

### The mental model

A relational database stores data in tables. Each table has columns (schema) and rows (data). SQL is the language you use to ask questions about that data and to change it. You already know this from Oracle — the SQL standard is the same. Syntax differences appear at the edges.

### Create the AOIS incident table

You will work with a realistic table that matches what AOIS stores in production.

```sql
CREATE TABLE incidents (
    id           SERIAL PRIMARY KEY,
    log_line     TEXT NOT NULL,
    severity     VARCHAR(2) NOT NULL,   -- P1, P2, P3, P4
    summary      TEXT,
    action       TEXT,
    confidence   NUMERIC(4,3),
    model_used   VARCHAR(50),
    latency_ms   INTEGER,
    created_at   TIMESTAMPTZ DEFAULT NOW()
);
```

Expected output:
```
CREATE TABLE
```

Insert sample data:

```sql
INSERT INTO incidents (log_line, severity, summary, action, confidence, model_used, latency_ms, created_at) VALUES
('pod aois-7d9f4 OOMKilled exit code 137 memory limit 512Mi',
 'P1', 'Pod killed by OOM killer', 'Increase memory limit to 1Gi', 0.97, 'claude-sonnet-4-6', 1240,
 NOW() - INTERVAL '2 hours'),

('CrashLoopBackOff: back-off 5m0s restarting failed container aois-worker',
 'P1', 'Container in crash loop, back-off at max', 'Check container logs for root cause', 0.94, 'claude-sonnet-4-6', 1380,
 NOW() - INTERVAL '90 minutes'),

('disk pressure: node hetzner-1 diskPressure=True available 2Gi of 80Gi',
 'P2', 'Node disk nearly full', 'Clean up old logs and images on node', 0.91, 'claude-sonnet-4-6', 1150,
 NOW() - INTERVAL '1 hour'),

('5xx spike: 847 errors in 60s error rate 23% upstream timeout gateway',
 'P2', '5xx rate spike likely upstream timeout', 'Check upstream service health and increase timeout', 0.88, 'gpt-4o-mini', 890,
 NOW() - INTERVAL '45 minutes'),

('cert expiry warning: aois.46.225.235.51.nip.io expires in 6 days',
 'P3', 'TLS certificate expiring soon', 'Trigger cert-manager renewal or renew manually', 0.99, 'gpt-4o-mini', 720,
 NOW() - INTERVAL '30 minutes'),

('high CPU: pod aois-api CPU throttled 340% of limit 500m for 10 minutes',
 'P3', 'CPU throttling degrading response time', 'Increase CPU limit or optimize hot path', 0.85, 'llama-3.1-8b', 410,
 NOW() - INTERVAL '20 minutes'),

('info: health check /health returned 200 in 12ms',
 'P4', 'Health check passing normally', 'No action needed', 0.99, 'llama-3.1-8b', 180,
 NOW() - INTERVAL '10 minutes'),

('warn: slow query detected 4.2s query_id=8a3f SELECT * FROM events WHERE ts > now()-interval 1h',
 'P3', 'Slow query on events table, missing index likely', 'Add index on ts column or rewrite query', 0.82, 'gpt-4o-mini', 650,
 NOW() - INTERVAL '5 minutes');
```

Expected output:
```
INSERT 0 8
```

### SELECT — the shape of every query

```sql
SELECT id, severity, summary, latency_ms
FROM incidents
ORDER BY created_at DESC;
```

Expected output:
```
 id | severity |                    summary                     | latency_ms
----+----------+------------------------------------------------+------------
  8 | P3       | Slow query on events table, missing index      |        650
  7 | P4       | Health check passing normally                  |        180
  6 | P3       | CPU throttling degrading response time         |        410
  5 | P3       | TLS certificate expiring soon                  |        720
  4 | P2       | 5xx rate spike likely upstream timeout         |        890
  3 | P2       | Node disk nearly full                          |       1150
  2 | P1       | Container in crash loop, back-off at max       |       1380
  1 | P1       | Pod killed by OOM killer                       |       1240
(8 rows)
```

### WHERE — filter to what you need

```sql
SELECT id, severity, summary, model_used
FROM incidents
WHERE severity IN ('P1', 'P2')
ORDER BY created_at DESC;
```

Expected output:
```
 id | severity |                    summary                    |     model_used
----+----------+-----------------------------------------------+--------------------
  3 | P2       | Node disk nearly full                         | claude-sonnet-4-6
  4 | P2       | 5xx rate spike likely upstream timeout        | gpt-4o-mini
  2 | P1       | Container in crash loop, back-off at max      | claude-sonnet-4-6
  1 | P1       | Pod killed by OOM killer                      | claude-sonnet-4-6
(4 rows)
```

Filter by time — this is the pattern you reach for during incidents:

```sql
SELECT severity, summary, created_at
FROM incidents
WHERE created_at > NOW() - INTERVAL '1 hour'
ORDER BY created_at DESC;
```

Expected output (rows within the last hour from insert time):
```
 severity |                    summary                     |           created_at
----------+------------------------------------------------+-------------------------------
 P3       | Slow query on events table, missing index      | 2026-04-19 22:55:00+00
 P4       | Health check passing normally                  | 2026-04-19 22:50:00+00
 P3       | CPU throttling degrading response time         | 2026-04-19 22:40:00+00
 P3       | TLS certificate expiring soon                  | 2026-04-19 22:30:00+00
 P2       | 5xx rate spike likely upstream timeout         | 2026-04-19 22:15:00+00
(5 rows)
```

**Oracle PL/SQL equivalent:**
```sql
-- Oracle uses SYSDATE and interval literals differently
WHERE created_at > SYSDATE - INTERVAL '1' HOUR
-- or: WHERE created_at > SYSDATE - (1/24)
```

---

▶ **STOP — do this now**

Write a query that returns all P1 and P2 incidents where confidence is above 0.90, showing only severity, summary, confidence, and model_used. Order by confidence descending.

Expected output:
```
 severity |                    summary                    | confidence |     model_used
----------+-----------------------------------------------+------------+--------------------
 P3       | TLS certificate expiring soon                 |      0.990 | gpt-4o-mini
 P1       | Pod killed by OOM killer                      |      0.970 | claude-sonnet-4-6
 P1       | Container in crash loop, back-off at max      |      0.940 | claude-sonnet-4-6
 P2       | Node disk nearly full                         |      0.910 | claude-sonnet-4-6
(4 rows)
```

Note: the P3 cert expiry row appears because confidence > 0.90 is the only filter — severity filter is `IN ('P1', 'P2')` so adjust your WHERE accordingly to match this exact output.

Actual WHERE clause for the above: `WHERE confidence > 0.90 ORDER BY confidence DESC` (no severity filter, checking your column selection).

---

## Part 2 — Aggregations and GROUP BY

This is the pattern that answers "how many P1s did we get today?" and "which model is slowest?"

```sql
SELECT severity, COUNT(*) AS incident_count
FROM incidents
GROUP BY severity
ORDER BY severity;
```

Expected output:
```
 severity | incident_count
----------+----------------
 P1       |              2
 P2       |              2
 P3       |              3
 P4       |              1
(4 rows)
```

Average latency per model — which model tier is fastest:

```sql
SELECT
    model_used,
    COUNT(*)                          AS calls,
    ROUND(AVG(latency_ms))            AS avg_latency_ms,
    MIN(latency_ms)                   AS min_ms,
    MAX(latency_ms)                   AS max_ms
FROM incidents
GROUP BY model_used
ORDER BY avg_latency_ms DESC;
```

Expected output:
```
      model_used      | calls | avg_latency_ms | min_ms | max_ms
----------------------+-------+----------------+--------+--------
 claude-sonnet-4-6    |     3 |           1257 |   1150 |   1380
 gpt-4o-mini          |     3 |            753 |    650 |    890
 llama-3.1-8b         |     2 |            295 |    180 |    410
(3 rows)
```

This is real signal: the routing tiers (Claude for P1/P2, cheaper models for P3/P4) produce exactly this latency spread. The data confirms the architecture works.

HAVING — filter after grouping (not before, that is WHERE):

```sql
SELECT model_used, COUNT(*) AS calls
FROM incidents
GROUP BY model_used
HAVING COUNT(*) >= 3;
```

Expected output:
```
      model_used      | calls
----------------------+-------
 claude-sonnet-4-6    |     3
 gpt-4o-mini          |     3
(2 rows)
```

**Oracle equivalent:**
```sql
-- HAVING is identical in Oracle. GROUP BY is identical.
-- Oracle uses ROUND differently for very large numbers but same function name.
```

---

## Part 3 — JOINs

Add a second table to make this realistic. In production AOIS will have a `remediations` table tracking what actions were taken.

```sql
CREATE TABLE remediations (
    id            SERIAL PRIMARY KEY,
    incident_id   INTEGER REFERENCES incidents(id),
    action_taken  TEXT NOT NULL,
    operator      VARCHAR(50),
    applied_at    TIMESTAMPTZ DEFAULT NOW(),
    success       BOOLEAN DEFAULT NULL
);

INSERT INTO remediations (incident_id, action_taken, operator, applied_at, success) VALUES
(1, 'kubectl set resources deployment/aois --limits=memory=1Gi', 'collins', NOW() - INTERVAL '100 minutes', true),
(2, 'kubectl rollout restart deployment/aois-worker', 'collins', NOW() - INTERVAL '80 minutes', true),
(3, 'docker system prune -f on hetzner-1', 'collins', NOW() - INTERVAL '55 minutes', false);
```

INNER JOIN — only incidents that have been remediated:

```sql
SELECT
    i.severity,
    i.summary,
    r.action_taken,
    r.success,
    r.operator
FROM incidents i
INNER JOIN remediations r ON r.incident_id = i.id
ORDER BY i.severity;
```

Expected output:
```
 severity |                  summary                   |                        action_taken                         | success | operator
----------+--------------------------------------------+------------------------------------------------------------+---------+----------
 P1       | Pod killed by OOM killer                   | kubectl set resources deployment/aois --limits=memory=1Gi  | t       | collins
 P1       | Container in crash loop, back-off at max   | kubectl rollout restart deployment/aois-worker             | t       | collins
 P2       | Node disk nearly full                       | docker system prune -f on hetzner-1                        | f       | collins
(3 rows)
```

LEFT JOIN — all incidents, with remediation data where it exists (NULL where it does not):

```sql
SELECT
    i.id,
    i.severity,
    i.summary,
    r.action_taken,
    r.success
FROM incidents i
LEFT JOIN remediations r ON r.incident_id = i.id
ORDER BY i.id;
```

Expected output:
```
 id | severity |                    summary                     |                        action_taken                         | success
----+----------+------------------------------------------------+------------------------------------------------------------+---------
  1 | P1       | Pod killed by OOM killer                       | kubectl set resources deployment/aois --limits=memory=1Gi  | t
  2 | P1       | Container in crash loop, back-off at max       | kubectl rollout restart deployment/aois-worker             | t
  3 | P2       | Node disk nearly full                          | docker system prune -f on hetzner-1                        | f
  4 | P2       | 5xx rate spike likely upstream timeout         |                                                            |
  5 | P3       | TLS certificate expiring soon                  |                                                            |
  6 | P3       | CPU throttling degrading response time         |                                                            |
  7 | P4       | Health check passing normally                  |                                                            |
  8 | P3       | Slow query on events table, missing index      |                                                            |
(8 rows)
```

Find all incidents with no remediation yet — the open work queue:

```sql
SELECT i.id, i.severity, i.summary
FROM incidents i
LEFT JOIN remediations r ON r.incident_id = i.id
WHERE r.id IS NULL
ORDER BY i.severity, i.id;
```

Expected output:
```
 id | severity |                    summary
----+----------+------------------------------------------------
  4 | P2       | 5xx rate spike likely upstream timeout
  5 | P3       | TLS certificate expiring soon
  6 | P3       | CPU throttling degrading response time
  8 | P3       | Slow query on events table, missing index
  7 | P4       | Health check passing normally
(5 rows)
```

**Oracle equivalent:**
```sql
-- LEFT JOIN is identical syntax in Oracle.
-- Oracle outer join old syntax (+) still works but LEFT JOIN is standard.
WHERE r.id IS NULL  -- identical
```

---

## Part 4 — CTEs (Common Table Expressions)

A CTE is a named subquery that you write once at the top and reference like a table. Postgres and Oracle both support CTEs. This is the readable way to build complex queries — no nested parentheses six levels deep.

```sql
WITH
  open_incidents AS (
    SELECT i.id, i.severity, i.summary, i.confidence, i.model_used
    FROM incidents i
    LEFT JOIN remediations r ON r.incident_id = i.id
    WHERE r.id IS NULL
  ),
  high_confidence AS (
    SELECT id, severity, summary, model_used
    FROM open_incidents
    WHERE confidence >= 0.80
  )
SELECT *
FROM high_confidence
ORDER BY severity, id;
```

Expected output:
```
 id | severity |                    summary                    |   model_used
----+----------+-----------------------------------------------+-------------
  4 | P2       | 5xx rate spike likely upstream timeout        | gpt-4o-mini
  5 | P3       | TLS certificate expiring soon                 | gpt-4o-mini
  6 | P3       | CPU throttling degrading response time        | llama-3.1-8b
  8 | P3       | Slow query on events table, missing index     | gpt-4o-mini
(4 rows)
```

Each CTE in the `WITH` block is evaluated once and reused. This replaces the pattern of deeply nested subqueries that are hard to read and harder to debug.

**Oracle equivalent:**
```sql
-- WITH ... AS (...) is identical syntax in Oracle (available since 9i).
-- Oracle calls these "Subquery Factoring" in documentation.
```

---

▶ **STOP — do this now**

Write a query using a CTE that:
1. First CTE: finds all incidents from the last 2 hours
2. Second CTE: calculates average latency per severity from those incidents
3. Final SELECT: returns severity and avg latency, only where avg latency > 500ms, ordered by avg latency descending

Expected output (will vary slightly by time of insert, approximate):
```
 severity | avg_latency_ms
----------+----------------
 P1       |           1310
 P2       |           1020
 P3       |            673
(3 rows)
```

---

## Part 5 — EXPLAIN ANALYZE: Reading the Query Plan

This is the tool you reach for when a query is slow. `EXPLAIN ANALYZE` shows what Postgres actually did to execute a query — not what you asked it to do.

```sql
EXPLAIN ANALYZE
SELECT severity, summary
FROM incidents
WHERE created_at > NOW() - INTERVAL '1 hour';
```

Expected output:
```
                                         QUERY PLAN
--------------------------------------------------------------------------------------------
 Seq Scan on incidents  (cost=0.00..1.18 rows=3 width=38) (actual time=0.012..0.025 rows=5 loops=1)
   Filter: (created_at > (now() - '01:00:00'::interval))
   Rows Removed by Filter: 3
 Planning Time: 0.120 ms
 Execution Time: 0.045 ms
(5 rows)
```

What you are reading:
- **Seq Scan** — Postgres read every row in the table. With 8 rows this is fine. With 8 million rows this is your alert.
- **cost=0.00..1.18** — planner's estimated cost (relative units). First number = startup cost, second = total cost.
- **actual time=0.012..0.025** — wall clock milliseconds. First = time to first row, second = total.
- **rows=5** — how many rows actually came back.
- **Rows Removed by Filter: 3** — 3 rows were read and discarded. With a large table, this is where an index saves you.

Now add an index and see what changes:

```sql
CREATE INDEX idx_incidents_created_at ON incidents(created_at);

EXPLAIN ANALYZE
SELECT severity, summary
FROM incidents
WHERE created_at > NOW() - INTERVAL '1 hour';
```

Expected output after index:
```
                                                     QUERY PLAN
---------------------------------------------------------------------------------------------------------------------
 Index Scan using idx_incidents_created_at on incidents  (cost=0.13..8.16 rows=3 width=38) (actual time=0.030..0.042 rows=5 loops=1)
   Index Cond: (created_at > (now() - '01:00:00'::interval))
 Planning Time: 0.140 ms
 Execution Time: 0.060 ms
(4 rows)
```

**Seq Scan → Index Scan.** Postgres is now using the index. On 8 rows the time difference is negligible. On 8 million rows, a Seq Scan that took 4.2 seconds becomes a sub-millisecond Index Scan. This is exactly what the slow query in the test data (`query_id=8a3f`) needed.

**Oracle equivalent:**
```sql
-- Oracle uses EXPLAIN PLAN FOR ... then SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY)
-- Or: press F5 in SQL Developer, or use AUTOTRACE
EXPLAIN PLAN FOR SELECT severity FROM incidents WHERE created_at > SYSDATE - 1/24;
SELECT * FROM TABLE(DBMS_XPLAN.DISPLAY);
-- PG's EXPLAIN ANALYZE is more direct — runs the query and gives actual timings
```

### When to add an index

Add an index when:
- The column appears in WHERE clauses frequently
- The table has more than ~10,000 rows
- EXPLAIN shows Seq Scan with many rows removed by filter

Do not add an index on:
- Columns with very few distinct values (boolean, status with 3 values) — the index is not selective enough
- Columns rarely queried
- Every column "just in case" — indexes slow down INSERT/UPDATE/DELETE

---

## Part 6 — Transactions

A transaction is a unit of work that either completes fully or not at all. If you update three tables and the third fails, the first two roll back. This is how databases stay consistent.

```sql
BEGIN;

INSERT INTO incidents (log_line, severity, summary, action, confidence, model_used, latency_ms)
VALUES ('etcd leader election timeout: cluster may be unstable',
        'P1', 'etcd unstable, cluster at risk', 'Check etcd health immediately', 0.98, 'claude-sonnet-4-6', 1420);

-- Check it is there before committing
SELECT id, severity, summary FROM incidents WHERE severity = 'P1' ORDER BY id DESC LIMIT 1;
```

Expected after INSERT inside the transaction:
```
 id | severity |            summary
----+----------+-----------------------------
  9 | P1       | etcd unstable, cluster at risk
(1 row)
```

Now roll it back — the row disappears:

```sql
ROLLBACK;

SELECT id, severity, summary FROM incidents WHERE id = 9;
```

Expected:
```
 id | severity | summary
----+----------+---------
(0 rows)
```

The row never persisted. This is how you safely test a destructive change before committing it.

SAVEPOINT — partial rollback within a transaction (Oracle and Postgres both support this):

```sql
BEGIN;

INSERT INTO remediations (incident_id, action_taken, operator)
VALUES (4, 'Restarted upstream auth service', 'collins');

SAVEPOINT after_remediation;

-- Simulate a mistake
UPDATE incidents SET severity = 'P4' WHERE id = 4;

-- Realise the mistake, roll back to savepoint only
ROLLBACK TO SAVEPOINT after_remediation;

-- The remediation insert is still there, the bad UPDATE is gone
COMMIT;
```

Verify the remediation was saved but severity is unchanged:

```sql
SELECT i.id, i.severity, r.action_taken
FROM incidents i
JOIN remediations r ON r.incident_id = i.id
WHERE i.id = 4;
```

Expected:
```
 id | severity |         action_taken
----+----------+-------------------------------
  4 | P2       | Restarted upstream auth service
(1 row)
```

**Oracle equivalent:**
```sql
-- BEGIN is not needed in Oracle — autocommit is OFF by default in SQL*Plus/SQLcl
-- SAVEPOINT, ROLLBACK TO SAVEPOINT, COMMIT are identical syntax
-- Oracle: ROLLBACK TO after_remediation (no SAVEPOINT keyword in the ROLLBACK)
```

---

▶ **STOP — do this now**

Run this and observe the error:

```sql
BEGIN;
INSERT INTO incidents (log_line, severity, summary, action, confidence, model_used, latency_ms)
VALUES ('test', 'P5', 'invalid severity', 'none', 1.5, 'test', -1);
```

Expected output:
```
ERROR:  new row for relation "incidents" violates check constraint ...
-- or no error (no check constraint yet) -- check what happens
```

Now add a check constraint and test it:

```sql
ROLLBACK;

ALTER TABLE incidents
ADD CONSTRAINT chk_severity CHECK (severity IN ('P1','P2','P3','P4'));

BEGIN;
INSERT INTO incidents (log_line, severity, summary, action, confidence, model_used, latency_ms)
VALUES ('test invalid', 'P5', 'bad severity', 'none', 0.5, 'test', 100);
```

Expected:
```
ERROR:  new row for relation "incidents" violates check constraint "chk_severity"
DETAIL:  Failing row contains (10, test invalid, P5, bad severity, none, 0.500, test, 100, ...).
```

This is how the database enforces the same rules your Pydantic model enforces in Python — defence in depth.

```sql
ROLLBACK;
```

---

## Part 7 — PL/pgSQL Functions

This is where Oracle PL/SQL and PL/pgSQL are most similar. Both have:
- `CREATE OR REPLACE FUNCTION`
- Typed parameters and return values
- `DECLARE` block for variables
- `BEGIN / END` block for logic
- `RETURN` statement

The differences are in the details.

### Your first function

Write a function that takes a severity level and returns the count of incidents at that level.

```sql
CREATE OR REPLACE FUNCTION count_by_severity(p_severity VARCHAR)
RETURNS INTEGER
LANGUAGE plpgsql
AS $$
DECLARE
    v_count INTEGER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM incidents
    WHERE severity = p_severity;

    RETURN v_count;
END;
$$;
```

Expected output:
```
CREATE FUNCTION
```

Call it:

```sql
SELECT count_by_severity('P1');
```

Expected:
```
 count_by_severity
-------------------
                 2
(1 row)
```

```sql
SELECT count_by_severity('P3');
```

Expected:
```
 count_by_severity
-------------------
                 3
(1 row)
```

**Oracle PL/SQL equivalent:**
```sql
CREATE OR REPLACE FUNCTION count_by_severity(p_severity IN VARCHAR2)
RETURN NUMBER
IS
    v_count NUMBER;
BEGIN
    SELECT COUNT(*)
    INTO v_count
    FROM incidents
    WHERE severity = p_severity;

    RETURN v_count;
END;
/
```

Differences:
| | PL/pgSQL | Oracle PL/SQL |
|---|---|---|
| Language declaration | `LANGUAGE plpgsql` | Not required |
| Body delimiter | `$$` ... `$$` | `IS` ... `END;` + `/` |
| Parameter direction | Positional only | `IN`, `OUT`, `IN OUT` explicit |
| VARCHAR | `VARCHAR` | `VARCHAR2` |
| Number type | `INTEGER`, `NUMERIC` | `NUMBER` |

### Function returning a table

Write a function that returns the full incident record for all incidents above a confidence threshold.

```sql
CREATE OR REPLACE FUNCTION high_confidence_incidents(p_threshold NUMERIC)
RETURNS TABLE(
    incident_id  INTEGER,
    severity     VARCHAR(2),
    summary      TEXT,
    confidence   NUMERIC,
    model_used   VARCHAR(50)
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        i.id,
        i.severity,
        i.summary,
        i.confidence,
        i.model_used
    FROM incidents i
    WHERE i.confidence >= p_threshold
    ORDER BY i.confidence DESC;
END;
$$;
```

Call it:

```sql
SELECT * FROM high_confidence_incidents(0.90);
```

Expected:
```
 incident_id | severity |                    summary                    | confidence |     model_used
-------------+----------+-----------------------------------------------+------------+--------------------
           5 | P3       | TLS certificate expiring soon                 |      0.990 | gpt-4o-mini
           7 | P4       | Health check passing normally                 |      0.990 | llama-3.1-8b
           1 | P1       | Pod killed by OOM killer                      |      0.970 | claude-sonnet-4-6
           2 | P1       | Container in crash loop, back-off at max      |      0.940 | claude-sonnet-4-6
           3 | P2       | Node disk nearly full                         |      0.910 | claude-sonnet-4-6
(5 rows)
```

**Oracle equivalent:**
```sql
-- Oracle uses pipelined table functions or REF CURSOR for this pattern.
-- The RETURNS TABLE pattern is PG-specific. Oracle alternative:
CREATE OR REPLACE FUNCTION high_confidence_incidents(p_threshold IN NUMBER)
RETURN SYS_REFCURSOR
IS
    v_cursor SYS_REFCURSOR;
BEGIN
    OPEN v_cursor FOR
        SELECT id, severity, summary, confidence, model_used
        FROM incidents
        WHERE confidence >= p_threshold
        ORDER BY confidence DESC;
    RETURN v_cursor;
END;
/
```

---

## Part 8 — PL/pgSQL Procedures

A procedure differs from a function: it does not return a value, and it can control transactions with `COMMIT` and `ROLLBACK` inside the body. Functions cannot commit inside themselves.

Write a procedure that marks an incident as remediated — inserts the remediation record and logs a note.

```sql
CREATE OR REPLACE PROCEDURE apply_remediation(
    p_incident_id  INTEGER,
    p_action       TEXT,
    p_operator     VARCHAR(50),
    p_success      BOOLEAN
)
LANGUAGE plpgsql
AS $$
DECLARE
    v_incident_exists BOOLEAN;
BEGIN
    -- Check incident exists
    SELECT EXISTS(SELECT 1 FROM incidents WHERE id = p_incident_id)
    INTO v_incident_exists;

    IF NOT v_incident_exists THEN
        RAISE EXCEPTION 'Incident % does not exist', p_incident_id;
    END IF;

    -- Insert remediation record
    INSERT INTO remediations (incident_id, action_taken, operator, success)
    VALUES (p_incident_id, p_action, p_operator, p_success);

    RAISE NOTICE 'Remediation recorded for incident % by %', p_incident_id, p_operator;
END;
$$;
```

Call it:

```sql
CALL apply_remediation(5, 'Triggered cert-manager certificate renewal', 'collins', true);
```

Expected output:
```
NOTICE:  Remediation recorded for incident 5 by collins
CALL
```

Try calling it with a non-existent incident:

```sql
CALL apply_remediation(999, 'Some action', 'collins', true);
```

Expected:
```
ERROR:  Incident 999 does not exist
```

Verify the remediation was recorded:

```sql
SELECT i.severity, i.summary, r.action_taken, r.success, r.operator
FROM incidents i
JOIN remediations r ON r.incident_id = i.id
WHERE i.id = 5;
```

Expected:
```
 severity |          summary           |              action_taken               | success | operator
----------+----------------------------+-----------------------------------------+---------+----------
 P3       | TLS certificate expiring soon | Triggered cert-manager certificate renewal | t     | collins
(1 row)
```

**Oracle PL/SQL equivalent:**
```sql
CREATE OR REPLACE PROCEDURE apply_remediation(
    p_incident_id  IN NUMBER,
    p_action       IN VARCHAR2,
    p_operator     IN VARCHAR2,
    p_success      IN NUMBER  -- Oracle has no BOOLEAN in SQL layer; use 0/1
)
IS
    v_count NUMBER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM incidents WHERE id = p_incident_id;
    IF v_count = 0 THEN
        RAISE_APPLICATION_ERROR(-20001, 'Incident ' || p_incident_id || ' does not exist');
    END IF;

    INSERT INTO remediations (incident_id, action_taken, operator, success)
    VALUES (p_incident_id, p_action, p_operator, p_success);

    DBMS_OUTPUT.PUT_LINE('Remediation recorded for incident ' || p_incident_id);
    COMMIT;
END;
/
```

Key differences:
| | PL/pgSQL | Oracle PL/SQL |
|---|---|---|
| Call | `CALL procedure_name(args)` | `EXEC procedure_name(args)` or `BEGIN procedure_name(args); END;` |
| Raise error | `RAISE EXCEPTION 'msg'` | `RAISE_APPLICATION_ERROR(-20001, 'msg')` |
| Print/log | `RAISE NOTICE 'msg'` | `DBMS_OUTPUT.PUT_LINE('msg')` |
| BOOLEAN | Native type in PL/pgSQL | Not available in SQL layer — use NUMBER(1) or VARCHAR2 |
| Transaction in proc | `COMMIT`/`ROLLBACK` inside proc body | Same, but autocommit behavior differs |

---

## Part 9 — Oracle PL/SQL vs PL/pgSQL Full Cheat Sheet

| Concept | Oracle PL/SQL | PL/pgSQL |
|---|---|---|
| String type | `VARCHAR2(n)` | `VARCHAR(n)` or `TEXT` |
| Number type | `NUMBER(p,s)` | `NUMERIC(p,s)` or `INTEGER` |
| Boolean | No SQL boolean — use `NUMBER(1)` | `BOOLEAN` (true/false/null) |
| Sequence | `CREATE SEQUENCE s; s.NEXTVAL` | `SERIAL` or `CREATE SEQUENCE` + `nextval('s')` |
| Date + time | `DATE` (includes time), `TIMESTAMP` | `DATE` (no time), `TIMESTAMP`, `TIMESTAMPTZ` |
| Current time | `SYSDATE`, `SYSTIMESTAMP` | `NOW()`, `CURRENT_TIMESTAMP` |
| String concat | `'a' \|\| 'b'` | `'a' \|\| 'b'` (same) |
| Null check | `NVL(col, default)` | `COALESCE(col, default)` |
| Conditional | `DECODE(col, v1, r1, default)` | `CASE WHEN col=v1 THEN r1 ELSE default END` |
| Limit rows | `WHERE ROWNUM <= n` | `LIMIT n` |
| Regex match | `REGEXP_LIKE(col, pattern)` | `col ~ 'pattern'` |
| String to date | `TO_DATE('2026-04-19', 'YYYY-MM-DD')` | `'2026-04-19'::DATE` or `TO_DATE(...)` |
| Exception | `RAISE_APPLICATION_ERROR(-20001, 'msg')` | `RAISE EXCEPTION 'msg'` |
| Print | `DBMS_OUTPUT.PUT_LINE('msg')` | `RAISE NOTICE 'msg'` |
| Package | `CREATE PACKAGE` / `CREATE PACKAGE BODY` | No packages — use schemas for grouping |
| Cursor FOR loop | `FOR rec IN (SELECT ...) LOOP` | `FOR rec IN SELECT ... LOOP` (no parens) |
| Bulk collect | `SELECT ... BULK COLLECT INTO v_arr` | Arrays + `ARRAY_AGG` or `FOREACH` |
| Function body | `IS ... BEGIN ... END;` + `/` | `LANGUAGE plpgsql AS $$ BEGIN ... END; $$` |
| Procedure call | `EXEC proc(args)` | `CALL proc(args)` |
| DDL in transaction | Not possible (DDL auto-commits) | Possible — DDL is transactional in PG |

---

## Part 10 — SRE Operational Queries

These are the queries you run during incidents. Memorise the shape; look up the exact columns when needed.

### Who is connected and what are they doing?

```sql
SELECT
    pid,
    usename,
    application_name,
    state,
    query_start,
    NOW() - query_start AS duration,
    LEFT(query, 80) AS query_preview
FROM pg_stat_activity
WHERE state != 'idle'
ORDER BY query_start;
```

During an incident this tells you: is there a long-running query holding locks?

### Find blocked queries (lock wait)

```sql
SELECT
    blocked.pid                    AS blocked_pid,
    blocked.query                  AS blocked_query,
    blocking.pid                   AS blocking_pid,
    blocking.query                 AS blocking_query,
    blocking.usename               AS blocking_user
FROM pg_stat_activity blocked
JOIN pg_stat_activity blocking
    ON blocking.pid = ANY(pg_blocking_pids(blocked.pid))
WHERE blocked.cardinality(pg_blocking_pids(blocked.pid)) > 0;
```

If this returns rows during an incident: someone's transaction is blocking others. The `blocking_pid` is the one to investigate (or kill with `SELECT pg_terminate_backend(blocking_pid)`).

### Kill a long-running query

```sql
-- Gentle cancel (like ctrl+c — lets it finish cleanly if it can)
SELECT pg_cancel_backend(pid) FROM pg_stat_activity WHERE pid = 12345;

-- Hard terminate (immediate)
SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE pid = 12345;
```

### Check table sizes

```sql
SELECT
    relname AS table_name,
    pg_size_pretty(pg_total_relation_size(oid)) AS total_size,
    pg_size_pretty(pg_relation_size(oid))       AS table_size,
    pg_size_pretty(pg_indexes_size(oid))        AS index_size
FROM pg_class
WHERE relkind = 'r'
  AND relnamespace = 'public'::regnamespace
ORDER BY pg_total_relation_size(oid) DESC;
```

### Vacuum stats — is autovacuum keeping up?

```sql
SELECT
    relname,
    n_live_tup,
    n_dead_tup,
    last_autovacuum,
    last_autoanalyze
FROM pg_stat_user_tables
ORDER BY n_dead_tup DESC;
```

High `n_dead_tup` with no recent `last_autovacuum` means table bloat is accumulating. Run `VACUUM ANALYZE table_name;` manually.

---

## Part 11 — Python + psycopg2 (the AOIS pattern)

AOIS talks to Postgres using psycopg2 internally. Here is the same pattern you will see in the codebase.

First install psycopg2 (in your Python environment or directly):

```bash
pip install psycopg2-binary
```

Then from a Python file (or the Python REPL inside your container):

```python
import psycopg2
from psycopg2.extras import RealDictCursor

conn = psycopg2.connect(
    host="localhost",
    port=5432,
    dbname="aois",
    user="postgres",
    password="aoisdev"
)

with conn.cursor(cursor_factory=RealDictCursor) as cur:
    cur.execute(
        "SELECT id, severity, summary FROM incidents WHERE severity = %s ORDER BY id",
        ("P1",)   # always use parameterised queries — never f-strings with user input
    )
    rows = cur.fetchall()
    for row in rows:
        print(f"[{row['severity']}] {row['summary']}")

conn.close()
```

Expected output:
```
[P1] Pod killed by OOM killer
[P1] Container in crash loop, back-off at max
```

The `%s` placeholder is how psycopg2 safely passes parameters — it escapes them, preventing SQL injection. Never build SQL with string concatenation or f-strings when the value comes from outside your code.

**The same pattern with a context manager (production style):**

```python
with psycopg2.connect(
    host="localhost", port=5432,
    dbname="aois", user="postgres", password="aoisdev"
) as conn:
    with conn.cursor(cursor_factory=RealDictCursor) as cur:
        cur.execute(
            "SELECT model_used, COUNT(*) AS calls FROM incidents GROUP BY model_used ORDER BY calls DESC"
        )
        for row in cur.fetchall():
            print(f"{row['model_used']}: {row['calls']} calls")
```

Expected output:
```
claude-sonnet-4-6: 3 calls
gpt-4o-mini: 3 calls
llama-3.1-8b: 2 calls
```

---

▶ **STOP — do this now**

Write a Python script that:
1. Connects to your local Postgres container
2. Calls the `high_confidence_incidents(0.85)` function you created earlier
3. Prints each row in the format: `[MODEL] SEVERITY — SUMMARY (conf: 0.XX)`

Expected output:
```
[gpt-4o-mini] P3 — TLS certificate expiring soon (conf: 0.99)
[llama-3.1-8b] P4 — Health check passing normally (conf: 0.99)
[claude-sonnet-4-6] P1 — Pod killed by OOM killer (conf: 0.97)
[claude-sonnet-4-6] P1 — Container in crash loop, back-off at max (conf: 0.94)
[claude-sonnet-4-6] P2 — Node disk nearly full (conf: 0.91)
[gpt-4o-mini] P2 — 5xx rate spike likely upstream timeout (conf: 0.88)
[llama-3.1-8b] P3 — CPU throttling degrading response time (conf: 0.85)
```

Hint: call a stored function from Python using `cur.execute("SELECT * FROM high_confidence_incidents(%s)", (0.85,))`.

---

## Common Mistakes

### 1. `WHERE` vs `HAVING` confusion

**Symptom:** `ERROR: column "count" does not exist` or wrong results.

```sql
-- Wrong: WHERE filters rows before grouping, cannot use aggregate aliases
SELECT severity, COUNT(*) AS cnt FROM incidents WHERE cnt > 1 GROUP BY severity;
-- ERROR: column "cnt" does not exist

-- Right: HAVING filters after grouping
SELECT severity, COUNT(*) AS cnt FROM incidents GROUP BY severity HAVING COUNT(*) > 1;
```

### 2. NULL comparisons

**Symptom:** Query returns 0 rows when you expect rows with NULL values.

```sql
-- Wrong: = NULL is never true in SQL
SELECT * FROM remediations WHERE success = NULL;
-- Returns 0 rows even if success IS NULL

-- Right
SELECT * FROM remediations WHERE success IS NULL;
```

**Oracle and PG both behave this way.** NULL is not a value — it is the absence of a value. Nothing equals NULL, including NULL itself.

### 3. Missing FROM in PL/pgSQL SELECT INTO

**Symptom:** `ERROR: query has no destination for result data`

```sql
-- Wrong: SELECT without INTO in a function
CREATE OR REPLACE FUNCTION bad_example() RETURNS INTEGER LANGUAGE plpgsql AS $$
BEGIN
    SELECT COUNT(*) FROM incidents;  -- result goes nowhere
    RETURN 0;
END; $$;
```

```sql
-- Right: SELECT INTO captures the result
DECLARE v_count INTEGER;
BEGIN
    SELECT COUNT(*) INTO v_count FROM incidents;
    RETURN v_count;
END;
```

### 4. `COMMIT` inside a PL/pgSQL function

**Symptom:** `ERROR: invalid transaction termination`

Functions cannot commit. Only procedures can. If you need to commit inside a stored routine, it must be a `PROCEDURE` called with `CALL`, not a `FUNCTION`.

### 5. Oracle-only syntax that breaks in PG

```sql
-- Oracle: works
SELECT * FROM incidents WHERE ROWNUM <= 5;

-- PG: ERROR: column "rownum" does not exist
-- PG equivalent:
SELECT * FROM incidents LIMIT 5;
```

```sql
-- Oracle: NVL
SELECT NVL(action, 'no action') FROM incidents;

-- PG: COALESCE (also valid in Oracle — prefer this for portability)
SELECT COALESCE(action, 'no action') FROM incidents;
```

### 6. Forgetting `$$` delimiters in PL/pgSQL

**Symptom:** `ERROR: syntax error at or near "BEGIN"`

```sql
-- Wrong
CREATE OR REPLACE FUNCTION f() RETURNS VOID LANGUAGE plpgsql AS
BEGIN
    RAISE NOTICE 'hello';
END;

-- Right
CREATE OR REPLACE FUNCTION f() RETURNS VOID LANGUAGE plpgsql AS $$
BEGIN
    RAISE NOTICE 'hello';
END;
$$;
```

---

## Troubleshooting

### `psql: error: connection to server on socket "/var/run/postgresql/.s.PGSQL.5432" failed`

Postgres is not running or you are connecting to the wrong host.

```bash
# Check the container is running
docker ps | grep aois-pg

# If stopped, restart it
docker start aois-pg

# Connect specifying host explicitly
docker exec -it aois-pg psql -U postgres -d aois
```

### `ERROR: relation "incidents" does not exist`

You are connected to the wrong database.

```sql
-- Check which database you are in
SELECT current_database();

-- List all databases
\l

-- Switch database (reconnect)
\c aois
```

### `ERROR: function count_by_severity(unknown) does not exist`

The function was not created or was created in a different schema.

```sql
-- List all functions you created
\df count_by_severity

-- If empty, create it again
-- If it exists in a different schema, qualify it:
SELECT public.count_by_severity('P1');
```

### `ERROR: duplicate key value violates unique constraint`

You are inserting a row with a primary key that already exists — usually happens when you re-run an INSERT script that does not use `ON CONFLICT`.

```sql
-- Safe insert: skip if exists
INSERT INTO incidents (...) VALUES (...)
ON CONFLICT (id) DO NOTHING;

-- Or reset the sequence if you truncated the table
SELECT setval('incidents_id_seq', (SELECT MAX(id) FROM incidents));
```

### Python: `psycopg2.OperationalError: could not connect to server`

Port 5432 is not mapped or the container is stopped.

```bash
# Check port mapping
docker ps --format 'table {{.Names}}\t{{.Ports}}' | grep aois-pg

# Should show: 0.0.0.0:5432->5432/tcp
# If not, the container was started without -p 5432:5432 — recreate it
```

---

## Connection to Later Phases

**v4 (Docker Compose):** Postgres runs as a service alongside AOIS. The Docker Compose file you already have spins up the exact same container you used here. The `POSTGRES_PASSWORD` from your `.env` matches what AOIS uses to connect.

**v5 (Security):** SQL injection is one of the OWASP API Top 10 vulnerabilities. The parameterised query pattern (`%s` placeholders) you used in the Python section is your defence. If AOIS ever builds SQL from user-supplied log data without parameterisation, it is vulnerable. The psycopg2 pattern prevents this at the driver level.

**v16 (OpenTelemetry):** You will instrument database queries with OTel spans. EXPLAIN ANALYZE output informs which queries need tracing — slow queries are the ones worth measuring in production.

**v17 (Kafka):** AOIS consumes log events from Kafka and writes analysis results to Postgres. The `incidents` table schema you built here is the schema that table uses in production.

**v20 (Agent Memory):** Mem0 stores agent memory in a vector database alongside Postgres for structured data. The PL/pgSQL skills you built here let you query agent memory directly when debugging why AOIS remembered the wrong context.

**v23 (LangGraph):** The audit trail for every agent action is written to Postgres. The CTEs and JOINs you wrote here are the queries you will run to audit what the agent did during an incident.

---

## Mastery Checkpoint

Work through each of these in your local Postgres container. Do not move to v1 until you can do all of them from memory or near-memory.

1. Write a query that returns the number of incidents per model, only for models with an average latency above 600ms, ordered by average latency descending. Use a CTE.

2. Write a PL/pgSQL function `severity_summary()` that returns a table of (severity, count, avg_confidence, avg_latency_ms) for all four severity levels, with no parameters.

3. Add an index on `incidents(severity, created_at)` (composite index). Run EXPLAIN ANALYZE on a query filtering by both columns and confirm Index Scan is used.

4. Write a transaction that: inserts a new P1 incident, immediately inserts a remediation for it, and rolls back if the remediation insert fails (simulate failure by inserting a duplicate primary key). Verify both rows are absent after rollback.

5. Translate this Oracle PL/SQL block to PL/pgSQL and run it successfully:
   ```sql
   -- Oracle
   DECLARE
       v_count NUMBER;
   BEGIN
       SELECT COUNT(*) INTO v_count FROM incidents WHERE severity = 'P1';
       DBMS_OUTPUT.PUT_LINE('P1 count: ' || v_count);
   END;
   /
   ```

6. Write a Python script that calls `apply_remediation` for every unresolved P2 incident (those with no entry in remediations), using the psycopg2 parameterised query pattern, and prints the count of remediations it created.

7. Run `SELECT * FROM pg_stat_activity;` and explain what each column tells you during a live incident investigation.

8. Write a query using `pg_stat_user_tables` that identifies which tables have not been autovacuumed in the last 24 hours and have more than 100 dead tuples.

**The mastery bar:** You can write production-quality SQL queries and PL/pgSQL functions without looking up the syntax. You understand what EXPLAIN ANALYZE output tells you, when to add an index, and how to diagnose lock contention. You can translate between Oracle PL/SQL and PL/pgSQL fluently. You would not hesitate to open psql during a production incident.
