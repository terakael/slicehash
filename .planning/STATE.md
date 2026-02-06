# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-06)

**Core value:** Fair, transparent mining rotation that guarantees every user with remaining quota gets their turn to mine.
**Current focus:** Phase 2 - Core Backend

## Current Position

Phase: 2 of 4 (Core Backend) - In Progress
Plan: 3 of 5 (Pool API Client)
Status: In progress
Last activity: 2026-02-06 — Completed 02-03-PLAN.md

Progress: [█████░░░░░] 50% (5/10 plans complete)

## Performance Metrics

**Velocity:**

- Total plans completed: 5
- Average duration: 2 min
- Total execution time: 0.22 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 - Foundation | 3 | 9 min | 3 min |
| 2 - Core Backend | 2 | 4 min | 2 min |

**Recent Trend:**

- Last 5 plans: 02-03 (2 min), 02-02 (2 min), 01-03 (3 min), 01-02 (3 min), 01-01 (3 min)
- Trend: Excellent velocity

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

**From Plan 02-02:**
- Traffic thresholds: <10 (green), 10-25 (orange), >25 (red) active users
- Fairness mechanism: No multiplier during low traffic, priority multiplier during congestion
- Priority range: 1-5 inclusive with validation

**From Plan 02-03:**
- httpx for async HTTP: Modern, async-native library with good error handling
- Graceful error handling pattern: Return False on errors, log but never raise
- Async context manager pattern: Ensures proper client cleanup

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-02-06T09:36:44Z
Stopped at: Completed 02-03-PLAN.md (Pool API Client)
Resume file: None
