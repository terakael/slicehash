# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-02-06)

**Core value:** Fair, transparent mining rotation that guarantees every user with remaining quota gets their turn to mine.
**Current focus:** Phase 3 - User API

## Current Position

Phase: 3 of 4 (User API) - In Progress
Plan: 1 of 1 complete
Status: Phase 3 complete, ready for Phase 4
Last activity: 2026-02-06 — Completed 03-01-PLAN.md (User API endpoints)

Progress: [███████░░░] 75% (3/4 phases complete)

## Performance Metrics

**Velocity:**

- Total plans completed: 9
- Average duration: 4 min
- Total execution time: 0.80 hours

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 1 - Foundation | 3 | 9 min | 3 min |
| 2 - Core Backend | 5 | 27 min | 5 min |
| 3 - User API | 1 | 13 min | 13 min |

**Recent Trend:**

- Last 5 plans: 03-01 (13 min), 02-05 (5 min), 02-04 (2 min), 02-01 (16 min), 02-03 (2 min)
- Trend: Phase 3 complete, ready for Phase 4 frontend

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

**From Plan 02-05:**
- In-memory unbounded Queue: Simple POC approach, prevents webhook blocking (production would use Redis/RabbitMQ)
- Non-blocking put_nowait: Faster than await, acceptable for POC (could lose shares on crash)
- shares_consumed=1 for non-billable: Satisfies schema constraint, business logic only checks billable=1 flag
- Global queue reference: Fast webhook access without dependency injection complexity

**From Plan 03-01:**
- Regex validation for Bitcoin addresses: POC-level format check (defer bitcoinlib checksum validation to production)
- Pydantic models inline in app.py: File still under 400 lines, acceptable for POC
- Offset pagination: Simpler than cursor-based, sufficient for read-heavy POC
- ValidationError serialization: Convert to simple dict format (field + message) to avoid JSON issues
- Hardcoded user_id=1: All endpoints default to first user (no auth system in POC)

### Pending Todos

None yet.

### Blockers/Concerns

None yet.

## Session Continuity

Last session: 2026-02-06T10:56:24Z
Stopped at: Completed 03-01-PLAN.md (User API endpoints) - Phase 3 Complete
Resume file: None
