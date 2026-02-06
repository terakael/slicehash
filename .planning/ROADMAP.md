# Roadmap: SliceHash Mining Backend

## Overview

This roadmap delivers a POC mining pool backend in 4 phases: Foundation establishes the data layer, Core Backend implements the intelligence center (webhooks, quota, rotation, priority), User API bridges backend to frontend, and Frontend provides the user interface. Each phase delivers a testable, coherent capability building toward fair, transparent mining rotation.

## Phases

**Phase Numbering:**

- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation** - Database schema and configuration layer
- [ ] **Phase 2: Core Backend** - Webhook processing, quota, rotation, and priority system
- [ ] **Phase 3: User API** - REST endpoints for user data and share history
- [ ] **Phase 4: Frontend** - Dark-mode dashboard and settings interface

## Phase Details

### Phase 1: Foundation
**Goal**: Database and configuration infrastructure ready for backend logic
**Depends on**: Nothing (first phase)
**Requirements**: DB-01, DB-02, DB-03, DB-04, DB-05, CFG-01, CFG-02, CFG-03
**Success Criteria** (what must be TRUE):
  1. SQLite database exists with users, transactions, share_events tables
  2. Database supports async operations via aiosqlite
  3. Configuration file defines billable threshold, pool URL, and database path
  4. Manual transaction insertion works for testing quota calculations
**Plans**: TBD

Plans:
- [ ] (Plans defined during plan-phase)

### Phase 2: Core Backend
**Goal**: Backend receives shares, tracks quotas, and rotates addresses fairly
**Depends on**: Phase 1
**Requirements**: HOOK-01, HOOK-02, HOOK-03, HOOK-04, QUOTA-01, QUOTA-02, QUOTA-03, QUOTA-04, QUOTA-05, PRIO-01, PRIO-02, PRIO-03, PRIO-04, ROT-01, ROT-02, ROT-03, ROT-04, ROT-05, ROT-06, POOL-01, POOL-02, POOL-03
**Success Criteria** (what must be TRUE):
  1. Webhook endpoint responds to share events in <10ms
  2. Share events are stored with billable classification based on difficulty threshold
  3. Shares_remaining calculation reflects transactions minus billable consumption
  4. Traffic level (green/orange/red) determines share consumption multiplier
  5. Current user rotates to least recently served user when turn completes
  6. Pool receives updated coinbase address after each rotation
**Plans**: TBD

Plans:
- [ ] (Plans defined during plan-phase)

### Phase 3: User API
**Goal**: REST API exposes user data, share history, and traffic status
**Depends on**: Phase 2
**Requirements**: API-01, API-02, API-03, API-04
**Success Criteria** (what must be TRUE):
  1. GET /api/users/me returns current user's address, tag, priority, shares_remaining, traffic_level
  2. PATCH /api/users/me updates address and tag with validation
  3. GET /api/users/me/shares returns paginated share history
  4. GET /api/traffic/status returns current traffic level and active user count
**Plans**: TBD

Plans:
- [ ] (Plans defined during plan-phase)

### Phase 4: Frontend
**Goal**: Users can view mining activity and configure payout settings
**Depends on**: Phase 3
**Requirements**: FE-01, FE-02, FE-03, FE-04, FE-05, FE-06, FE-07, FE-08, FE-09, FE-10, FE-11
**Success Criteria** (what must be TRUE):
  1. Dashboard displays recent shares with infinite scroll
  2. Each share shows block height, timestamp, and log10 difficulty
  3. Dashboard header shows remaining shares count and network difficulty
  4. Settings page allows updating Bitcoin address with format validation
  5. Settings page allows updating custom tag (max 50 chars)
  6. Dark mode styling loads fast with minimal CSS
**Plans**: TBD

Plans:
- [ ] (Plans defined during plan-phase)

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → 3 → 4

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation | 0/TBD | Not started | - |
| 2. Core Backend | 0/TBD | Not started | - |
| 3. User API | 0/TBD | Not started | - |
| 4. Frontend | 0/TBD | Not started | - |
