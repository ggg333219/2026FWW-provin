---
name: sqlx-code-review
label: SQLx 代码审查
icon: https://lf3-static.bytednsdoc.com/obj/eden-cn/ylcylz_fsph_ryhs/ljhwZthlaukjlkulzlp/doubao_skill_new/sqlx-code-review.png
description: Reviews sqlx database code for compile-time query checking, connection pool management, migration patterns, and PostgreSQL-specific usage. Use when reviewing Rust code that uses sqlx, database queries, connection pools, or migrations. Covers offline mode, type mapping, and transaction patterns.
---

# sqlx Code Review

## Review Workflow

1. **Check Cargo.toml** — Note sqlx features (`runtime-tokio`, `tls-rustls`/`tls-native-tls`, `postgres`/`mysql`/`sqlite`, `uuid`, `chrono`, `json`, `migrate`)
2. **Check query patterns** — Compile-time checked (`query!`, `query_as!`) vs runtime (`query`, `query_as`)
3. **Check pool configuration** — Connection limits, timeouts, idle settings
4. **Check migrations** — File naming, reversibility, data migration safety
5. **Check type mappings** — Rust types align with SQL column types

For an isolated snippet, only steps supported by the visible code are findings. Missing `Cargo.toml`, schema, uniqueness constraints, indexes, migrations, and caller contract are unknown; do not convert them into additional issues.

## Evidence Rules

- Direct interpolation of attacker-controlled data into a SQL string is a confirmed injection finding when the dataflow is visible.
- `query_as!`, `fetch_optional`, custom errors, indexes, or pool tuning are recommendations unless the schema and API contract prove the current choice wrong.
- Do not say code compiled, a database accepted the query, a test passed, or a scanner ran unless that action actually occurred in this task.
- Use a concrete malicious input to explain how query syntax changes, but label it as a demonstration payload, not as an executed exploit.

## Output Contract

The final answer must be self-contained and include, in this order:

1. **Graded findings** — location (real file/line or “input snippet”), severity, visible evidence, trigger, and impact.
2. **Exploit path** for injection findings — show the input and the resulting query shape without claiming execution.
3. **Complete corrected function** — use SQLx placeholders (`$1`, `$2`, …) and `.bind(...)`; preserve the original return cardinality unless schema/API evidence supports changing it.
4. **Executable test plan** — normal input, quotes, an injection-shaped payload, zero/multiple rows as applicable, and database/error propagation. State which tests were proposed versus actually run.
5. **Validation status** — list compiler/database/tool actions actually performed and the remaining gaps.

Never end with a summary that says details are “above”, “in the report”, or “in an attachment” unless those complete details are present in the same response or a verified accessible artifact.

## Review Checklist

### Query Patterns
- [ ] Compile-time checked queries (`query!`, `query_as!`) used where possible
- [ ] `sqlx.toml` or `DATABASE_URL` configured for offline compile-time checking
- [ ] No string interpolation in queries (SQL injection risk) — use bind parameters (`$1`, `$2`)
- [ ] `query_as!` maps to named structs, not anonymous records, for public APIs
- [ ] `.fetch_one()`, `.fetch_optional()`, `.fetch_all()` chosen appropriately
- [ ] `.fetch()` (streaming) used for large result sets

### Connection Pool
- [ ] `PgPool` shared via `Arc` or framework state (not created per-request)
- [ ] Pool size configured for the deployment (not left at defaults in production)
- [ ] Connection acquisition timeout set
- [ ] Idle connection cleanup configured

### Transactions
- [ ] `pool.begin()` used for multi-statement operations
- [ ] Transaction committed explicitly (not relying on implicit rollback on drop)
- [ ] Errors within transactions trigger rollback before propagation
- [ ] Nested transactions use savepoints (`tx.begin()`) if needed

### Type Mapping
- [ ] `sqlx::Type` derives match database column types
- [ ] Enum representations consistent between Rust, serde, and SQL
- [ ] `Uuid`, `DateTime<Utc>`, `Decimal` types used (not strings for structured data)
- [ ] `Option<T>` used for nullable columns
- [ ] `serde_json::Value` used for JSONB columns

### Migrations
- [ ] Migration files follow naming convention (`YYYYMMDDHHMMSS_description.sql`)
- [ ] Destructive migrations (DROP, ALTER DROP COLUMN) are reversible or have data backup plan
- [ ] No data-dependent schema changes in same migration as data changes
- [ ] `sqlx::migrate!()` called at application startup

## Severity Calibration

### Critical
- String interpolation in SQL queries (SQL injection)
- Missing transaction for multi-statement writes (partial writes on error)
- Connection pool created per-request (connection exhaustion)
- Missing bind parameter escaping

### Major
- Runtime queries (`query()`) where compile-time (`query!()`) could verify correctness
- Missing transaction rollback on error paths
- Enum type mismatch between Rust and database
- Unbounded `.fetch_all()` on potentially large tables

### Minor
- Pool defaults used in production without tuning
- Missing `.fetch_optional()` (using `.fetch_one()` then handling error for "not found")
- Overly broad `SELECT *` when only specific columns needed
- Missing indexes for queried columns (flag only if query pattern is clearly slow)

### Informational
- Suggestions to use `query_as!` for type-safe result mapping
- Suggestions to add database-level constraints alongside Rust validation
- Migration organization improvements

## Valid Patterns (Do NOT Flag)

- **Runtime `query()` for dynamic queries** — Compile-time checking doesn't work with dynamic SQL
- **`sqlx::FromRow` derive** — Valid alternative to `query_as!` for reusable row types
- **`TEXT` columns for enum storage** — Valid with `sqlx::Type` derive, simpler than custom SQL types
- **`.execute()` ignoring row count** — Acceptable for idempotent operations (upserts, deletes)
- **Shared DB with other languages** — e.g., Elixir owns migrations, Rust reads. This is a valid architecture.

## Before Submitting Findings

- Confirm every finding is supported by visible code or a real task artifact.
- Confirm the response contains the complete bind-based correction, not only a recommendation to use parameters.
- Confirm tests cover normal values, quote handling, injection-shaped input, and error propagation.
- Confirm optional API/cardinality suggestions are separated from confirmed defects.
- Confirm there is no reference to missing text, files, tools, or validation.
