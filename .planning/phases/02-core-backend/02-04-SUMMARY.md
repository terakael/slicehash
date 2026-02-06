---
phase: 02-core-backend
plan: 04
subsystem: rotation
tags: [fairness-algorithm, rotation-logic, weighted-wait-time, adaptive-interval]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: Database schema with users table
  - phase: 02-01
    provides: Quota calculation with get_active_users function
  - phase: 02-02
    provides: Priority system with multiplier validation
provides:
  - RotationState dataclass for tracking current mining turn
  - Fairness algorithm selecting least recently served user with priority weighting
  - Adaptive rotation interval scaling with active user count
  - Rotation decision logic requiring time + share thresholds
affects: [02-05-webhook-processor, state-management, mining-coordinator]

# Tech tracking
tech-stack:
  added: []
  patterns: [weighted-fairness-algorithm, adaptive-interval-calculation, dataclass-state-tracking]

key-files:
  created:
    - src/slicehash/rotation.py
    - test_rotation.py
  modified:
    - src/slicehash/db/schema.py

key-decisions:
  - "Weighted wait time formula: time_since / priority_multiplier ensures fair queue distribution"
  - "Never-served users get highest priority to bootstrap fair rotation"
  - "Adaptive interval formula: 60s / active_user_count (minimum 1s)"
  - "Rotation requires both time elapsed AND 1+ share found (prevents instant rotation)"

patterns-established:
  - "Fairness algorithm pattern: never-served first, then weighted wait time"
  - "State tracking via dataclass with Optional fields for safety"
  - "SQL-based timestamp calculations for consistency with database time"

# Metrics
duration: 2min
completed: 2026-02-06
---

# Phase 02 Plan 04: Rotation Logic Summary

**Weighted fairness algorithm with adaptive intervals: never-served priority, wait time divided by priority multiplier, 60s/user_count rotation threshold**

## Performance

- **Duration:** 2 min
- **Started:** 2026-02-06T09:39:33Z
- **Completed:** 2026-02-06T09:41:24Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments

- RotationState dataclass tracks current user, shares found, and rotation timing
- Fairness algorithm prioritizes never-served users, then selects based on weighted_wait_time = time_since / priority_multiplier
- Adaptive rotation interval scales inversely with user count (60s / N users, minimum 1s)
- should_rotate enforces both time threshold AND minimum 1 share before rotation
- Comprehensive test suite verifies fairness across multiple scenarios including priority weighting and exclusion

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement rotation algorithm and state management** - `cdd6728` (feat)

## Files Created/Modified

- `src/slicehash/rotation.py` - Core rotation logic: RotationState dataclass, calculate_rotation_interval (60s/user_count), should_rotate (time + share check), select_next_user (weighted fairness algorithm with never-served priority and wait time / priority_multiplier calculation)
- `test_rotation.py` - Manual verification testing fairness algorithm, priority weighting, rotation intervals, and rotation decision conditions
- `src/slicehash/db/schema.py` - Added last_served_at column to users table (critical for rotation tracking)

## Decisions Made

**Weighted wait time formula:** Implemented `weighted_wait_time = time_since_last_served / priority_multiplier`. This ensures users with lower priority (who pay less during congestion) get more frequent turns proportional to their wait time. Users with higher priority (who pay more) have their effective wait time reduced, creating fair market-based queuing.

**Never-served users first:** Users with `last_served_at = NULL` always get highest priority. This bootstraps the rotation system when new users join and ensures everyone gets at least one turn before weighted calculations apply.

**Adaptive interval formula:** 60 seconds divided by active user count ensures all users cycle through approximately once per minute. As congestion increases (more users), intervals shrink proportionally. Minimum 1 second prevents thrashing with 60+ users.

**Dual rotation threshold:** Rotation requires BOTH time elapsed >= interval AND shares_this_turn >= 1. This prevents instant rotation on first share while ensuring productivity (user found at least one share before rotating).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 2 - Missing Critical] Added last_served_at column to users table**

- **Found during:** Task 1 (Implementing select_next_user function)
- **Issue:** users table schema lacked last_served_at timestamp column required for rotation tracking. Without this field, fairness algorithm cannot calculate time since last served.
- **Fix:** Added `last_served_at TEXT` column to USERS_TABLE_SQL schema definition. This allows NULL for never-served users and timestamp updates when user gets mining turn.
- **Files modified:** src/slicehash/db/schema.py
- **Verification:** Test script successfully queries last_served_at, handles NULL values correctly, and uses timestamps for weighted wait calculation
- **Committed in:** cdd6728 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (Rule 2 - Missing Critical)
**Impact on plan:** Essential schema addition for rotation algorithm to function. No scope creep - this field is fundamental to tracking "least recently served" user.

## Issues Encountered

None - straightforward implementation once schema was corrected.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

Ready for webhook processor implementation (02-05-PLAN.md). Rotation logic provides:

- `RotationState` for tracking current mining assignment
- `select_next_user(db, exclude_user_id)` for fairness-based selection
- `should_rotate(state, interval, now)` for rotation decision
- `calculate_rotation_interval(active_user_count)` for adaptive timing

The webhook handler can now use these functions to:
1. Check if rotation should occur after each share submission
2. Select the next fair user when rotation triggers
3. Update last_served_at timestamp in database after rotation
4. Maintain RotationState for turn tracking

No blockers or concerns.

---
*Phase: 02-core-backend*
*Completed: 2026-02-06*
