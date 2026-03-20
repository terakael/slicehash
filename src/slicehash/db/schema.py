"""Database schema definitions for SliceHash.

This module contains SQL statements for creating all database tables
and indexes required by the SliceHash mining rotation system.

Tables:
    - users: User accounts with Bitcoin addresses and priority settings
    - transactions: Share purchase history for quota tracking
    - share_events: Individual mining share submissions from pool webhooks
"""

# Users table - stores user accounts and priority settings
USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    address TEXT NOT NULL UNIQUE,
    tag TEXT,
    priority_multiplier INTEGER DEFAULT 1 CHECK(priority_multiplier >= 1 AND priority_multiplier <= 5),
    last_served_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    lightning_pubkey TEXT
)
"""

# Transactions table - tracks share purchases for quota calculation
TRANSACTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL CHECK(amount > 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
"""

# Share events table - list view for shares with pre-calculated display fields
SHARE_EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS share_events (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    share_hash TEXT,
    ntime INTEGER NOT NULL,
    level REAL NOT NULL,
    is_block INTEGER NOT NULL CHECK(is_block IN (0, 1)),
    miner_tag TEXT,
    block_height INTEGER NOT NULL,
    billable INTEGER NOT NULL CHECK(billable IN (0, 1)),
    shares_consumed INTEGER NOT NULL CHECK(shares_consumed >= 1 AND shares_consumed <= 5),
    FOREIGN KEY (user_id) REFERENCES users(id)
)
"""

# Share verification table - full verification data for share reconstruction
SHARE_VERIFICATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS share_verification (
    share_id INTEGER PRIMARY KEY,
    coinbase_tx TEXT NOT NULL,
    prev_block_hash TEXT NOT NULL,
    bits TEXT NOT NULL,
    nonce BIGINT NOT NULL,
    version INTEGER NOT NULL,
    merkle_path JSONB,
    FOREIGN KEY (share_id) REFERENCES share_events(id) ON DELETE CASCADE
)
"""

# Global state table - stores system-wide configuration
GLOBAL_STATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS global_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

# Index for user's recent shares (most common query pattern)
USER_RECENT_SHARES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_share_events_user_ntime
ON share_events(user_id, ntime DESC)
"""

# Index for share hash uniqueness and lookups
SHARE_HASH_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_share_events_share_hash
ON share_events(share_hash)
"""

# Index for level-based leaderboard queries
LEVEL_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_share_events_level
ON share_events(level DESC)
"""

# Index for billable share quota calculations
BILLABLE_SHARES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_share_events_billable
ON share_events(billable)
"""

# Index for SSE recovery queries (faster missed share lookups)
RECOVERY_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_share_events_user_id
ON share_events(user_id, id)
"""

# Index for transactions user_id queries (optimizes quota calculations)
TRANSACTIONS_USER_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_transactions_user_id
ON transactions(user_id)
"""

# Auth challenges table - stores LNURL k1 challenges
AUTH_CHALLENGES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS auth_challenges (
    k1 TEXT PRIMARY KEY,
    created_at BIGINT NOT NULL,
    expires_at BIGINT NOT NULL,
    used INTEGER DEFAULT 0 CHECK(used IN (0, 1))
)
"""

AUTH_CHALLENGES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_auth_challenges_expires
ON auth_challenges(expires_at)
"""

# Lightning invoices table - tracks payment requests for share purchases
LIGHTNING_INVOICES_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS lightning_invoices (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    payment_hash TEXT UNIQUE NOT NULL,
    label TEXT UNIQUE NOT NULL,
    payment_request TEXT NOT NULL,
    amount_shares INTEGER NOT NULL CHECK(amount_shares > 0),
    amount_sats INTEGER NOT NULL CHECK(amount_sats > 0),
    status TEXT DEFAULT 'pending' NOT NULL CHECK(status IN ('pending', 'paid', 'expired')),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP NOT NULL,
    paid_at TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
)
"""

LIGHTNING_INVOICES_USER_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_lightning_invoices_user_id
ON lightning_invoices(user_id)
"""

LIGHTNING_INVOICES_STATUS_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_lightning_invoices_status
ON lightning_invoices(status)
"""

# Unique index on lightning_pubkey for LNURL-auth lookups
USERS_LIGHTNING_PUBKEY_INDEX_SQL = """
CREATE UNIQUE INDEX IF NOT EXISTS idx_users_lightning_pubkey
ON users(lightning_pubkey)
"""

# All table creation statements in order
ALL_TABLES = [
    USERS_TABLE_SQL,
    TRANSACTIONS_TABLE_SQL,
    SHARE_EVENTS_TABLE_SQL,
    SHARE_VERIFICATION_TABLE_SQL,
    GLOBAL_STATE_TABLE_SQL,
    AUTH_CHALLENGES_TABLE_SQL,
    LIGHTNING_INVOICES_TABLE_SQL,
]

# All index creation statements
ALL_INDEXES = [
    USER_RECENT_SHARES_INDEX_SQL,
    SHARE_HASH_INDEX_SQL,
    LEVEL_INDEX_SQL,
    BILLABLE_SHARES_INDEX_SQL,
    RECOVERY_INDEX_SQL,
    TRANSACTIONS_USER_INDEX_SQL,
    AUTH_CHALLENGES_INDEX_SQL,
    USERS_LIGHTNING_PUBKEY_INDEX_SQL,
    LIGHTNING_INVOICES_USER_INDEX_SQL,
    LIGHTNING_INVOICES_STATUS_INDEX_SQL,
]
