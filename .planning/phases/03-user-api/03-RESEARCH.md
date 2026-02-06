# Phase 3: User API - Research

**Researched:** 2026-02-06
**Domain:** REST API development with Quart, Pydantic validation, async SQLite queries
**Confidence:** HIGH

## Summary

Phase 3 requires building four REST API endpoints using Quart (async Flask-like framework). The endpoints expose user data, share history, and traffic status. The project already has Quart 0.19+, Pydantic v2, and aiosqlite configured with working database schema and business logic modules.

The standard approach is to add route handlers to the existing app.py using Quart's decorator syntax, leverage Pydantic models for request/response validation, and reuse existing database access patterns from quota.py and priority.py modules. Since the project is a POC with no auth, endpoints default to user_id=1 (first user).

Key considerations: pagination for share history (offset-based for simplicity), Bitcoin address validation (basic regex for POC), proper HTTP status codes (200/400/404/500), and structured error responses. The architecture keeps routes in app.py (already ~112 lines, will grow to ~250-300), with Pydantic models defined inline or in a new models.py module.

**Primary recommendation:** Add routes to existing app.py, use Pydantic models for validation, implement offset-based pagination for share history, and validate Bitcoin addresses with regex pattern matching.

## Standard Stack

The project already has the core stack configured. No new dependencies required.

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| Quart | >=0.19.0 | Async web framework | Already in use, Flask-like API with async/await support |
| Pydantic | >=2.0.0 | Request/response validation | Already configured, industry standard for Python API validation |
| aiosqlite | >=0.19.0 | Async SQLite driver | Already in use for database access |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| quart-schema | 0.24+ | Auto-validation & OpenAPI docs | Optional - adds @validate_request decorators, auto-generates Swagger UI (deferred to production) |
| bitcoinlib | 0.6+ | Bitcoin address validation | Production - full checksum validation (POC can use regex) |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Offset pagination | Cursor-based | Cursor prevents consistency issues during real-time inserts but adds complexity (offset sufficient for POC) |
| Inline models | Separate models.py | Separate module cleaner for 4+ models but adds indirection (acceptable either way) |
| quart-schema | Manual validation | Schema extension adds OpenAPI docs but requires Python 3.10+ (defer to production) |
| Regex validation | bitcoinlib library | Full library validates checksums but adds dependency (regex sufficient for POC) |

**Installation:**

No new dependencies required. Project already has:
```bash
# Already in pyproject.toml
quart>=0.19.0
pydantic>=2.0.0
aiosqlite>=0.19.0
```

## Architecture Patterns

### Project Structure

Existing structure (from Phase 1-2):
```
src/slicehash/
├── __init__.py
├── config.py           # Config loading (existing)
├── db/
│   ├── __init__.py
│   ├── schema.py       # Table definitions (existing)
│   └── manager.py      # DatabaseManager (existing)
├── quota.py            # Quota calculation (existing - reuse)
├── priority.py         # Traffic level logic (existing - reuse)
├── rotation.py         # Rotation algorithm (existing)
├── share_processor.py  # Background processor (existing)
└── app.py              # Quart app + routes (existing - extend)
```

**For Phase 3:** Add routes to existing app.py. If Pydantic models grow beyond 50 lines, extract to:
```
src/slicehash/
├── models.py           # NEW: Pydantic request/response models
└── app.py              # EXTEND: Add 4 new route handlers
```

### Pattern 1: Quart Route Handler with Pydantic Validation

**What:** Define Pydantic models for request/response schemas, manually validate in route handlers
**When to use:** Every API endpoint needs type-safe validation and serialization

**Example:**
```python
# Source: Quart documentation + Pydantic v2 docs
from pydantic import BaseModel, Field, field_validator
from quart import jsonify, request
import re

class UserUpdateRequest(BaseModel):
    address: str | None = None
    tag: str | None = Field(None, max_length=50)

    @field_validator('address')
    @classmethod
    def validate_address(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Basic Bitcoin address regex (POC-level validation)
        pattern = r'^(bc1|[13])[a-zA-HJ-NP-Z0-9]{25,87}$'
        if not re.match(pattern, v):
            raise ValueError('Invalid Bitcoin address format')
        return v

class UserResponse(BaseModel):
    user_id: int
    address: str
    tag: str | None
    priority_multiplier: int
    shares_remaining: int
    traffic_level: str

@app.patch("/api/users/me")
async def update_user():
    try:
        data = await request.get_json()
        # Validate with Pydantic
        update_req = UserUpdateRequest(**data)

        # Apply update to database
        async with DatabaseManager(config.database_path) as db:
            if update_req.address:
                await db.execute(
                    "UPDATE users SET address = ? WHERE user_id = ?",
                    (update_req.address, 1)  # POC: hardcoded user_id=1
                )
            if update_req.tag is not None:
                await db.execute(
                    "UPDATE users SET tag = ? WHERE user_id = ?",
                    (update_req.tag, 1)
                )
            await db.commit()

            # Return updated user data
            # ... (fetch and return UserResponse)

        return jsonify(response.model_dump()), 200

    except ValueError as e:
        # Pydantic validation errors
        return jsonify({"error": str(e)}), 400
    except Exception as e:
        logger.error(f"Update failed: {e}")
        return jsonify({"error": "Internal error"}), 500
```

### Pattern 2: Offset-Based Pagination for Share History

**What:** Use LIMIT and OFFSET for paginated queries with query parameters
**When to use:** GET /api/users/me/shares endpoint for potentially large result sets

**Example:**
```python
# Source: SQLite documentation + REST API best practices
from pydantic import BaseModel, Field

class ShareHistoryResponse(BaseModel):
    shares: list[dict]
    total: int
    limit: int
    offset: int
    has_more: bool

@app.get("/api/users/me/shares")
async def get_share_history():
    # Parse query parameters (with defaults)
    limit = int(request.args.get('limit', 50))
    offset = int(request.args.get('offset', 0))

    # Validate limits
    limit = min(max(limit, 1), 100)  # Clamp to 1-100

    async with DatabaseManager(config.database_path) as db:
        # Get total count
        cursor = await db.execute(
            "SELECT COUNT(*) FROM share_events WHERE user_id = ?",
            (1,)  # POC: hardcoded user_id=1
        )
        total = (await cursor.fetchone())[0]

        # Get paginated shares (newest first)
        cursor = await db.execute(
            """
            SELECT submitted_at, share_difficulty, billable, shares_consumed
            FROM share_events
            WHERE user_id = ?
            ORDER BY submitted_at DESC
            LIMIT ? OFFSET ?
            """,
            (1, limit, offset)
        )
        rows = await cursor.fetchall()

        shares = [
            {
                "submitted_at": row[0],
                "share_difficulty": row[1],
                "billable": bool(row[2]),
                "shares_consumed": row[3]
            }
            for row in rows
        ]

        return jsonify({
            "shares": shares,
            "total": total,
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < total
        }), 200
```

### Pattern 3: Reusing Existing Business Logic

**What:** Call existing functions from quota.py and priority.py rather than duplicating logic
**When to use:** GET /api/users/me and GET /api/traffic/status endpoints

**Example:**
```python
# Source: Project's existing modules
from .quota import calculate_shares_remaining, get_active_users
from .priority import calculate_traffic_level, TrafficLevel

@app.get("/api/users/me")
async def get_current_user():
    async with DatabaseManager(config.database_path) as db:
        # Fetch user record
        cursor = await db.execute(
            "SELECT user_id, address, tag, priority_multiplier FROM users WHERE user_id = ?",
            (1,)  # POC: hardcoded user_id=1
        )
        row = await cursor.fetchone()
        if not row:
            return jsonify({"error": "User not found"}), 404

        user_id, address, tag, priority = row

        # Reuse existing quota calculation
        shares_remaining = await calculate_shares_remaining(db, user_id)

        # Reuse existing traffic calculation
        active_count = await get_active_users(db)
        traffic_level = calculate_traffic_level(active_count)

        return jsonify({
            "user_id": user_id,
            "address": address,
            "tag": tag,
            "priority_multiplier": priority,
            "shares_remaining": shares_remaining,
            "traffic_level": traffic_level.value  # Enum to string
        }), 200

@app.get("/api/traffic/status")
async def get_traffic_status():
    async with DatabaseManager(config.database_path) as db:
        active_count = await get_active_users(db)
        traffic_level = calculate_traffic_level(active_count)

        return jsonify({
            "traffic_level": traffic_level.value,
            "active_user_count": active_count
        }), 200
```

### Anti-Patterns to Avoid

- **Blocking operations in route handlers:** Always use async database operations (aiosqlite), never sync sqlite3
- **Missing error handling:** Catch ValidationError, database errors, and unexpected exceptions separately
- **Inconsistent status codes:** Don't return 200 for validation failures or 500 for missing resources
- **N+1 queries:** Don't fetch related data in loops - use JOINs or batch queries
- **Returning internal errors to clients:** Log detailed errors server-side, return generic "Internal error" to client

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Bitcoin address validation | Custom checksum verification | Regex for POC, bitcoinlib for production | Base58/Bech32 checksum algorithms are complex and error-prone |
| Request validation | Manual type checking | Pydantic models with validators | Field validation, coercion, and error messages handled automatically |
| API documentation | Manual API docs | quart-schema (production) | Auto-generates OpenAPI spec from Pydantic models |
| Pagination cursor encoding | Custom base64 schemes | Simple offset (POC) or cursor library (production) | Cursor encoding must handle ordering, uniqueness, and edge cases |
| JSON serialization | Manual dict building | Pydantic model_dump() | Handles nested models, datetime serialization, optional fields |

**Key insight:** API validation and serialization have solved patterns. Pydantic eliminates boilerplate while providing type safety. For POC, simple patterns (offset pagination, regex validation) are sufficient - optimize in production.

## Common Pitfalls

### Pitfall 1: Forgetting async/await in Database Operations
**What goes wrong:** Using sync sqlite3 instead of aiosqlite blocks the event loop, breaking webhook response time (<10ms requirement)
**Why it happens:** Easy to forget await on database calls, especially when copy-pasting patterns
**How to avoid:** Always use `async with DatabaseManager(...) as db` and `await db.execute()`. Never import sqlite3
**Warning signs:** Webhook response times spike above 10ms, concurrent requests block each other

### Pitfall 2: Validation Errors Return 500 Instead of 400
**What goes wrong:** Pydantic ValidationError raises exception, gets caught by generic handler, returns 500 Internal Error
**Why it happens:** Not catching ValidationError specifically in try/except blocks
**How to avoid:** Catch Pydantic validation errors (ValueError from validators) separately, return 400 Bad Request with error details
**Warning signs:** Client receives 500 status for malformed input, logs show validation errors as unexpected exceptions

### Pitfall 3: Pagination Without has_more Flag
**What goes wrong:** Frontend doesn't know when to stop paginating, may infinite loop or show "Load More" incorrectly
**Why it happens:** Returning data without metadata about total results or remaining pages
**How to avoid:** Always include total count, current offset/limit, and has_more boolean in paginated responses
**Warning signs:** Frontend pagination behaves incorrectly at end of dataset

### Pitfall 4: Not Validating Query Parameters
**What goes wrong:** Malicious or accidental large limit values (limit=1000000) cause slow queries or memory issues
**Why it happens:** Query parameters aren't validated like request bodies
**How to avoid:** Parse and clamp query params (limit between 1-100, offset >= 0) before using in SQL
**Warning signs:** Slow API responses, database locks, memory spikes on pagination endpoints

### Pitfall 5: Hardcoded user_id=1 Without 404 Check
**What goes wrong:** If database is empty or user 1 deleted, endpoints return 500 or null data
**Why it happens:** POC shortcuts assume user exists without checking
**How to avoid:** Check if user exists, return 404 Not Found if missing. Better: have init script create default user
**Warning signs:** Unexpected 500 errors on fresh database, confusing null values in responses

## Code Examples

Verified patterns from official sources:

### Complete GET Endpoint with Error Handling
```python
# Source: Quart documentation + project patterns
from quart import Quart, jsonify
from .db.manager import DatabaseManager
from .quota import calculate_shares_remaining
from .priority import calculate_traffic_level, get_active_users
import logging

logger = logging.getLogger(__name__)

@app.get("/api/users/me")
async def get_current_user():
    """Return current user's data including quota and traffic level.

    POC: Defaults to user_id=1 (no auth).

    Returns:
        200: User data JSON
        404: User not found
        500: Internal error
    """
    try:
        async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
            # Fetch user record
            cursor = await db.execute(
                "SELECT user_id, address, tag, priority_multiplier FROM users WHERE user_id = ?",
                (1,)
            )
            row = await cursor.fetchone()

            if not row:
                return jsonify({"error": "User not found"}), 404

            user_id, address, tag, priority = row

            # Calculate derived fields
            shares_remaining = await calculate_shares_remaining(db, user_id)
            active_count = await get_active_users(db)
            traffic_level = calculate_traffic_level(active_count)

            return jsonify({
                "user_id": user_id,
                "address": address,
                "tag": tag,
                "priority_multiplier": priority,
                "shares_remaining": shares_remaining,
                "traffic_level": traffic_level.value
            }), 200

    except Exception as e:
        logger.error(f"Failed to fetch user: {e}")
        return jsonify({"error": "Internal error"}), 500
```

### PATCH Endpoint with Pydantic Validation
```python
# Source: Pydantic v2 documentation + Quart patterns
from pydantic import BaseModel, Field, field_validator, ValidationError
from quart import request, jsonify
import re

class UserUpdateRequest(BaseModel):
    """Request model for updating user profile."""
    address: str | None = None
    tag: str | None = Field(None, max_length=50)

    @field_validator('address')
    @classmethod
    def validate_bitcoin_address(cls, v: str | None) -> str | None:
        if v is None:
            return v
        # Basic format check (POC-level)
        # Matches: bc1..., 1..., 3... addresses
        pattern = r'^(bc1[a-z0-9]{39,87}|[13][a-km-zA-HJ-NP-Z1-9]{25,34})$'
        if not re.match(pattern, v):
            raise ValueError('Invalid Bitcoin address format')
        return v

@app.patch("/api/users/me")
async def update_user():
    """Update current user's address and/or tag.

    POC: Updates user_id=1 (no auth).

    Request body:
        {
            "address": "bc1...",  # optional
            "tag": "my-label"     # optional, max 50 chars
        }

    Returns:
        200: Updated user data
        400: Validation error
        500: Internal error
    """
    try:
        data = await request.get_json()

        # Validate request
        update_req = UserUpdateRequest(**data)

        # Apply updates
        async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
            updates = []
            params = []

            if update_req.address is not None:
                updates.append("address = ?")
                params.append(update_req.address)

            if update_req.tag is not None:
                updates.append("tag = ?")
                params.append(update_req.tag)

            if not updates:
                return jsonify({"error": "No fields to update"}), 400

            params.append(1)  # user_id
            await db.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE user_id = ?",
                tuple(params)
            )
            await db.commit()

            # Return updated user (reuse GET logic)
            cursor = await db.execute(
                "SELECT user_id, address, tag, priority_multiplier FROM users WHERE user_id = ?",
                (1,)
            )
            row = await cursor.fetchone()
            if not row:
                return jsonify({"error": "User not found"}), 404

            user_id, address, tag, priority = row
            shares_remaining = await calculate_shares_remaining(db, user_id)
            active_count = await get_active_users(db)
            traffic_level = calculate_traffic_level(active_count)

            return jsonify({
                "user_id": user_id,
                "address": address,
                "tag": tag,
                "priority_multiplier": priority,
                "shares_remaining": shares_remaining,
                "traffic_level": traffic_level.value
            }), 200

    except ValidationError as e:
        # Pydantic validation failed
        return jsonify({
            "error": "Validation failed",
            "details": e.errors()
        }), 400
    except Exception as e:
        logger.error(f"Failed to update user: {e}")
        return jsonify({"error": "Internal error"}), 500
```

### Paginated GET Endpoint
```python
# Source: SQLite pagination patterns + REST API standards
@app.get("/api/users/me/shares")
async def get_share_history():
    """Return paginated share history for current user.

    Query parameters:
        limit: Results per page (default 50, max 100)
        offset: Number of results to skip (default 0)

    Returns:
        200: Paginated share history
        400: Invalid query parameters
        500: Internal error
    """
    try:
        # Parse and validate query params
        limit = int(request.args.get('limit', 50))
        offset = int(request.args.get('offset', 0))

        # Clamp to reasonable values
        limit = min(max(limit, 1), 100)
        offset = max(offset, 0)

        async with DatabaseManager(app.config["SLICEHASH_CONFIG"].database_path) as db:
            # Get total count
            cursor = await db.execute(
                "SELECT COUNT(*) FROM share_events WHERE user_id = ?",
                (1,)
            )
            total = (await cursor.fetchone())[0]

            # Get paginated results (newest first)
            cursor = await db.execute(
                """
                SELECT submitted_at, share_difficulty, billable, shares_consumed
                FROM share_events
                WHERE user_id = ?
                ORDER BY submitted_at DESC
                LIMIT ? OFFSET ?
                """,
                (1, limit, offset)
            )
            rows = await cursor.fetchall()

            shares = [
                {
                    "submitted_at": row[0],
                    "share_difficulty": row[1],
                    "billable": bool(row[2]),
                    "shares_consumed": row[3]
                }
                for row in rows
            ]

            return jsonify({
                "shares": shares,
                "total": total,
                "limit": limit,
                "offset": offset,
                "has_more": offset + limit < total
            }), 200

    except ValueError:
        return jsonify({"error": "Invalid limit or offset parameter"}), 400
    except Exception as e:
        logger.error(f"Failed to fetch share history: {e}")
        return jsonify({"error": "Internal error"}), 500
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Flask sync routes | Quart async routes | Quart 0.19+ (2023) | Enables async database access without blocking |
| Manual validation | Pydantic v2 models | Pydantic 2.0 (2023) | Faster validation, better error messages, improved type hints |
| Decorators for validation | Manual validation + Pydantic | Current | quart-schema adds @validate_request but requires Python 3.10+ (project uses 3.11+ so available) |
| dict responses | Pydantic model_dump() | Pydantic 2.0+ | model_dump() replaces deprecated dict() method |
| Cursor pagination | Offset still standard for simple cases | Ongoing | Cursor-based better for real-time but offset simpler for read-heavy POCs |

**Deprecated/outdated:**

- Pydantic v1 .dict() method: Use .model_dump() in v2
- Flask Blueprint imports in Quart: Quart has its own Blueprint class
- quart-schema requires Python 3.10+: Project uses 3.11+ so compatible if needed

## Open Questions

Things that couldn't be fully resolved:

1. **Should Pydantic models be in separate models.py or inline in app.py?**
   - What we know: Project has ~112 line app.py, will add 4 endpoints (~150+ lines), Pydantic models add ~50-80 lines
   - What's unclear: Whether keeping everything in app.py (total ~250-300 lines) is acceptable or should extract models
   - Recommendation: Keep inline initially for simplicity. Extract to models.py if file exceeds 300 lines or models reused across modules

2. **Should we add quart-schema for automatic validation?**
   - What we know: Adds @validate_request decorator and auto-generates OpenAPI docs, requires Python 3.10+ (project has 3.11+)
   - What's unclear: Whether OpenAPI docs valuable for POC or premature optimization
   - Recommendation: Defer to production. Manual validation with Pydantic sufficient for POC, add quart-schema when building frontend consumes API

3. **How strict should Bitcoin address validation be?**
   - What we know: Full validation requires checksum verification (base58check for legacy, bech32 for segwit)
   - What's unclear: Whether POC can accept technically invalid addresses or must reject them
   - Recommendation: Use regex pattern matching for POC (catches format errors), add bitcoinlib for checksum validation in production

4. **Should get_active_users() function exist already?**
   - What we know: priority.py has calculate_traffic_level() but unclear if get_active_users() implemented in quota.py
   - What's unclear: Definition of "active user" (has shares_remaining > 0? has recent share submission?)
   - Recommendation: Check quota.py for existing implementation. If missing, implement as "users with shares_remaining > 0" for Phase 3

## Sources

### Primary (HIGH confidence)

- Quart official documentation: https://quart.palletsprojects.com/en/latest/
  - Topics: REST API tutorial, routing, JSON handling, async patterns
- Pydantic v2 documentation: https://docs.pydantic.dev/latest/
  - Topics: model validation, field validators, model_dump, async usage
- Project codebase: /home/dan/git/personal/slicehash/src/slicehash/
  - Existing patterns: app.py structure, DatabaseManager usage, quota/priority modules

### Secondary (MEDIUM confidence)

- Quart-Schema PyPI: https://pypi.org/project/quart-schema/
  - Validation decorator patterns, OpenAPI generation capabilities
- Quart GitHub releases: https://github.com/pallets/quart
  - Version 0.20.0 latest (December 2024), migration notes

### Tertiary (LOW confidence)

- REST API pagination patterns (general knowledge from training data)
- Bitcoin address validation formats (standard patterns, not library-specific)
- HTTP status code conventions (RFC standards, widely adopted)

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH - Project already has Quart, Pydantic, aiosqlite configured and working
- Architecture: HIGH - Existing app.py patterns verified, database access patterns established
- Pitfalls: HIGH - Common async/validation issues well-documented in Quart/Pydantic docs

**Research date:** 2026-02-06
**Valid until:** ~60 days (stack is mature, unlikely breaking changes)
