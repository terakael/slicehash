# SliceHash Mining Backend

## What This Is

A backend service for an SV2 mining pool that manages fair address rotation between users. It receives share events from the pool via webhooks, implements a fairness algorithm to determine which user mines next, and tracks quota consumption with priority-based billing. Users interact through a minimal dark-mode web frontend to view their mining history and configure payout settings.

## Core Value

Fair, transparent mining rotation that guarantees every user with remaining quota gets their turn to mine.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] **Backend receives share webhooks** from pool (POST /api/shares/webhook)
- [ ] **Store share events** in database with billable flag based on configurable difficulty threshold
- [ ] **Fairness algorithm** selects next user (least recently served with shares remaining)
- [ ] **Rotation logic** switches addresses after user finds ≥1 share AND adaptive time interval
- [ ] **Call pool API** to update coinbase address (POST /api/coinbase)
- [ ] **Track user quotas** computed from transactions minus billable share consumption
- [ ] **Priority system** with traffic levels (green <10 users, orange 10-25, red >25)
- [ ] **Share consumption multipliers** (1-5x) apply during congestion (orange/red traffic)
- [ ] **Frontend: Share list** with infinite scroll showing block, timestamp, log10 difficulty
- [ ] **Frontend: Dashboard** displays remaining shares and current network difficulty
- [ ] **Frontend: Settings page** allows updating Bitcoin address and custom tag
- [ ] **Frontend: Dark mode** with futuristic Bitcoin aesthetic, minimal CSS
- [ ] **Multi-user database schema** with users, transactions, share_events, template_served_log
- [ ] **Config-based billable threshold** for share classification
- [ ] **Default to first user** in frontend (no auth system yet)

### Out of Scope

- **Lightning authentication** — Deferred to v2 (POC uses hardcoded/default user)
- **BTCPay Server payments** — Deferred to v2 (POC uses manual transaction entries)
- **PostgreSQL database** — Using SQLite for POC simplicity (migrate when proven)
- **Dynamic rate control** — Pool's share rate adjustment endpoint (POST /update-shares-per-minute) not implemented
- **Database migrations framework** — Add Alembic when migrating to PostgreSQL
- **User registration/onboarding** — Requires auth system first
- **Admin panel** — Manual database access sufficient for POC
- **API rate limiting** — Not needed for single-user POC
- **HTTPS/TLS** — Local development only for now

## Context

**Architecture:**

This backend is the intelligence center of a 2-service architecture (Backend + Pool). The pool validates shares and sends webhooks; the backend contains all business logic and actively calls the pool to switch addresses.

**Integration:**

Pool is running on a separate machine. Backend and pool communicate via HTTP (configurable URL). Pool integration testing happens after POC is functional.

**Full PRD available:**

Detailed specifications in `PRD-BACKEND-MINING-API.md` covering production requirements, security, observability, and full feature set. POC implements core rotation mechanics to prove the concept before building production features.

**Development approach:**

Build sequentially: webhook handling → database storage → rotation logic → priority system → frontend. Each component testable independently.

## Constraints

- **Tech Stack**: Python 3.11+ with Quart (async web framework), SQLite database — chosen for async performance and POC simplicity
- **Performance**: Webhook response must be <10ms (p99) — critical path, pool cannot block on backend
- **Frontend**: Minimal CSS, no jQuery or heavy frameworks — fast loading required
- **Deployment**: Local development initially — testing rotation mechanics before production
- **Pool Integration**: Pool on separate machine — URL configurable, integration test after build
- **Database**: SQLite for POC — will migrate to PostgreSQL for production (concurrent writes)

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Quart over Flask | Need async for <10ms webhook response, background task queue | — Pending |
| SQLite for POC | Simpler than PostgreSQL, prove mechanics before production migration | — Pending |
| Skip auth in v1 | Focus on core rotation algorithm, add Lightning auth after proven | — Pending |
| Include priority system | Core differentiator (1-5x multipliers), traffic-based, worth building early | — Pending |
| Minimal frontend | Speed and functionality over polish, iterate based on real usage | — Pending |
| Config-based threshold | Billable difficulty threshold in config file, easy to tune without code changes | — Pending |

---
*Last updated: 2026-02-06 after initialization*
