# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-06)

**Core value:** Fair, transparent mining rotation that guarantees every user with remaining quota gets their turn to mine.
**Current focus:** Phase 2 - Core Backend

## Current Position

Phase: 2 of 4 (Core Backend) - In Progress
Plan: 4 of 5 (Rotation Logic)
Status: In progress
Last activity: 2026-02-06 — Completed 02-04-PLAN.md

Progress: [███████░░░] 70% (7/10 plans complete)

## Performance Metrics

**Velocity:**

- Total plans completed: 7
- Average duration: 3 min
- Total execution time: 0.52 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 - Foundation | 3 | 9 min | 3 min |
| 2 - Core Backend | 4 | 22 min | 6 min |

**Recent Trend:**

- Last 5 plans: 02-04 (2 min), 02-01 (16 min), 02-03 (2 min), 02-02 (2 min), 01-03 (3 min)
- Trend: Consistent velocity

*Updated after each plan completion*

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

**From PROJECT.md:**
- Quart over Flask: Need async for <10ms webhook response
- SQLite for POC: Simpler than PostgreSQL, prove mechanics before production migration
- Skip auth in v1: Focus on core rotation algorithm
- Include priority system: Core differentiator (1-5x multipliers), worth building early
- Minimal frontend: Speed and functionality over polish
- Config-based threshold: Billable difficulty threshold in config file

**From Plan 01-01:**
- uv package manager: Use uv instead of pip (user preference)
- Pydantic v2: Modern type validation with Field() validators
- YAML configuration: Config file approach instead of environment variables
- Config.yaml gitignored: Template committed, actual config deployment-specific

**From Plan 01-02:**
- Schema constants pattern: Store SQL statements as module constants for easy reference
- Foreign key enforcement: Enable by default in DatabaseManager
- Parameterized queries: Prevent SQL injection throughout
- Idempotent user creation: get_or_create_user checks before inserting

**From Plan 01-03:**
- CLI scripts over web UI: Faster development, sufficient for POC testing
- Display shares_remaining: Show balance after each transaction for immediate feedback
- Separate inspect tool: Single responsibility principle for add vs view operations
- Human-readable output: Format timestamps and tables for developer experience

**From Plan 02-01:**
- SQL aggregation with COALESCE: Handle users with no transactions/shares gracefully
- Active user filtering: Calculate balance for all users, filter positive (POC approach)
- Billable-only consumption: Only shares with billable=1 count toward quota

**From Plan 02-02:**
- Traffic thresholds: <10 (green), 10-25 (orange), >25 (red) active users
- Fairness mechanism: No multiplier during low traffic, priority multiplier during congestion
- Priority range: 1-5 inclusive with validation

**From Plan 02-03:**
- httpx for async HTTP: Modern, async-native library with good error handling
- Graceful error handling pattern: Return False on errors, log but never raise
- Async context manager pattern: Ensures proper client cleanup

**From Plan 02-04:**
- Weighted wait time formula: time_since / priority_multiplier ensures fair queue distribution
- Never-served users get highest priority to bootstrap fair rotation
- Adaptive interval formula: 60s / active_user_count (minimum 1s)
- Rotation requires both time elapsed AND 1+ share found (prevents instant rotation)

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-02-06T09:41:24Z
Stopped at: Completed 02-04-PLAN.md (Rotation Logic)
Resume file: None
