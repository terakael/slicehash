# Requirements: SliceHash Mining Backend

**Defined:** 2026-02-06
**Core Value:** Fair, transparent mining rotation that guarantees every user with remaining quota gets their turn to mine.

## v1 Requirements

Requirements for POC release. Each maps to roadmap phases.

### Database Schema

- [ ] **DB-01**: Users table with user_id, address, tag, priority_multiplier fields
- [ ] **DB-02**: Transactions table with transaction_id, user_id, amount fields
- [ ] **DB-03**: Share events table with submitted_at, user_id, share_difficulty, billable, shares_consumed fields
- [ ] **DB-04**: Share events has channel_id and sequence_number for reference
- [ ] **DB-05**: SQLite database with async driver (aiosqlite)

### Webhook Integration

- [ ] **HOOK-01**: POST /api/shares/webhook endpoint accepts share events from pool
- [ ] **HOOK-02**: Webhook responds in <10ms (immediate 200 OK response)
- [ ] **HOOK-03**: Background worker processes queued share events asynchronously
- [ ] **HOOK-04**: Store share events in database with all fields from webhook payload

### Quota Management

- [ ] **QUOTA-01**: Compute shares_remaining as SUM(transactions.amount) - SUM(billable shares_consumed)
- [ ] **QUOTA-02**: Classify shares as billable based on configurable difficulty threshold
- [ ] **QUOTA-03**: Track shares_consumed field (1-5) based on priority multiplier and traffic level
- [ ] **QUOTA-04**: Support manual transaction insertion for POC testing
- [ ] **QUOTA-05**: Identify active users (shares_remaining > 0) for rotation pool

### Priority System

- [ ] **PRIO-01**: Calculate traffic level (green <10, orange 10-25, red >25 active users)
- [ ] **PRIO-02**: Apply priority multiplier during congestion (orange/red traffic only)
- [ ] **PRIO-03**: Users can set priority_multiplier (1-5) via settings
- [ ] **PRIO-04**: During green traffic, always consume 1 share regardless of multiplier

### Rotation Logic

- [ ] **ROT-01**: Implement fairness algorithm (least recently served with weighted wait time)
- [ ] **ROT-02**: Track current_user_id and shares_this_turn in memory
- [ ] **ROT-03**: Rotation triggers when current user has 1+ share AND time interval elapsed
- [ ] **ROT-04**: Adaptive time interval scales with active user count (60s / num_active_users)
- [ ] **ROT-05**: Call pool's POST /api/coinbase with next user's address, user_id, tag
- [ ] **ROT-06**: Update current_user_id and reset shares_this_turn after rotation

### Pool API Client

- [ ] **POOL-01**: HTTP client to call pool's /api/coinbase endpoint
- [ ] **POOL-02**: Configurable pool URL (environment variable or config file)
- [ ] **POOL-03**: Handle pool API errors gracefully (log and continue)

### User API Endpoints

- [ ] **API-01**: GET /api/users/me returns user data (address, tag, priority, shares_remaining, traffic_level)
- [ ] **API-02**: PATCH /api/users/me updates address and/or tag with validation
- [ ] **API-03**: GET /api/users/me/shares returns paginated share history
- [ ] **API-04**: GET /api/traffic/status returns current traffic level and active user count

### Frontend - Dashboard

- [ ] **FE-01**: Share list displays recent shares with infinite scroll
- [ ] **FE-02**: Each share shows block height (if available), timestamp, log10 difficulty
- [ ] **FE-03**: Dashboard header shows remaining shares count
- [ ] **FE-04**: Dashboard header shows current network difficulty (log10)
- [ ] **FE-05**: Dark mode styling with futuristic Bitcoin aesthetic
- [ ] **FE-06**: Minimal CSS, no jQuery, fast page load

### Frontend - Settings

- [ ] **FE-07**: Settings page with Bitcoin address input field
- [ ] **FE-08**: Settings page with custom tag input field (max 50 chars)
- [ ] **FE-09**: Settings icon in header navigates to settings page
- [ ] **FE-10**: Settings page validates Bitcoin address format
- [ ] **FE-11**: Settings page saves changes via PATCH /api/users/me

### Configuration

- [ ] **CFG-01**: Configurable billable difficulty threshold
- [ ] **CFG-02**: Configurable pool URL for API calls
- [ ] **CFG-03**: Configurable database path (SQLite file location)

## v2 Requirements

Deferred to future release. Tracked but not in current roadmap.

### Authentication

- **AUTH-01**: Lightning authentication (LNURL-auth)
- **AUTH-02**: User registration and login flow
- **AUTH-03**: Session management and JWT tokens

### Payments

- **PAY-01**: BTCPay Server integration for invoice creation
- **PAY-02**: Webhook handler for payment confirmations
- **PAY-03**: Automatic transaction creation on payment

### Database

- **DB-06**: PostgreSQL database for production
- **DB-07**: Database migration framework (Alembic)
- **DB-08**: Connection pooling for concurrent access

### Pool Integration

- **POOL-04**: Dynamic rate control (POST /update-shares-per-minute)
- **POOL-05**: Adjust share submission rate based on active user count

### Operations

- **OPS-01**: Structured logging (JSON format)
- **OPS-02**: Prometheus metrics for monitoring
- **OPS-03**: Health check endpoint
- **OPS-04**: Docker Compose deployment

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Share deduplication | POC accepts pool sends unique events, add if needed |
| User registration UI | Requires Lightning auth first |
| Admin panel | Manual database access sufficient for POC |
| API rate limiting | Single user POC, not needed yet |
| HTTPS/TLS | Local development only |
| Database backups | SQLite file copy sufficient for POC |
| Email notifications | No notification system in v1 |
| Multi-language support | English only for POC |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| DB-01 | Phase 1 | Complete |
| DB-02 | Phase 1 | Complete |
| DB-03 | Phase 1 | Complete |
| DB-04 | Phase 1 | Complete |
| DB-05 | Phase 1 | Complete |
| CFG-01 | Phase 1 | Complete |
| CFG-02 | Phase 1 | Complete |
| CFG-03 | Phase 1 | Complete |
| HOOK-01 | Phase 2 | Complete |
| HOOK-02 | Phase 2 | Complete |
| HOOK-03 | Phase 2 | Complete |
| HOOK-04 | Phase 2 | Complete |
| QUOTA-01 | Phase 2 | Complete |
| QUOTA-02 | Phase 2 | Complete |
| QUOTA-03 | Phase 2 | Complete |
| QUOTA-04 | Phase 2 | Complete |
| QUOTA-05 | Phase 2 | Complete |
| PRIO-01 | Phase 2 | Complete |
| PRIO-02 | Phase 2 | Complete |
| PRIO-03 | Phase 2 | Complete |
| PRIO-04 | Phase 2 | Complete |
| ROT-01 | Phase 2 | Complete |
| ROT-02 | Phase 2 | Complete |
| ROT-03 | Phase 2 | Complete |
| ROT-04 | Phase 2 | Complete |
| ROT-05 | Phase 2 | Complete |
| ROT-06 | Phase 2 | Complete |
| POOL-01 | Phase 2 | Complete |
| POOL-02 | Phase 2 | Complete |
| POOL-03 | Phase 2 | Complete |
| API-01 | Phase 3 | Pending |
| API-02 | Phase 3 | Pending |
| API-03 | Phase 3 | Pending |
| API-04 | Phase 3 | Pending |
| FE-01 | Phase 4 | Pending |
| FE-02 | Phase 4 | Pending |
| FE-03 | Phase 4 | Pending |
| FE-04 | Phase 4 | Pending |
| FE-05 | Phase 4 | Pending |
| FE-06 | Phase 4 | Pending |
| FE-07 | Phase 4 | Pending |
| FE-08 | Phase 4 | Pending |
| FE-09 | Phase 4 | Pending |
| FE-10 | Phase 4 | Pending |
| FE-11 | Phase 4 | Pending |

**Coverage:**

- v1 requirements: 45
- Mapped to phases: 45
- Unmapped: 0

---
*Requirements defined: 2026-02-06*
*Last updated: 2026-02-06 after roadmap creation*
