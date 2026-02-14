"""Database schema definitions for SliceHash.

This module contains SQL statements for creating all database tables
and indexes required by the SliceHash mining rotation system.

Tables:
    - users: User accounts with Bitcoin addresses and priority settings
    - transactions: Share purchase history for quota tracking
    - share_events: Lean table for listing share submissions (main query table)
    - share_validation: Detailed mining parameters for hash verification
    - share_merkle_path: Merkle path hashes for coinbase transaction verification
"""

# Users table - stores user accounts and priority settings
USERS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS users (
    user_id SERIAL PRIMARY KEY,
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
    transaction_id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL CHECK(amount > 0),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
)
"""

# Share events table - lean table for listing shares
SHARE_EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS share_events (
    id SERIAL PRIMARY KEY,
    submitted_at TIMESTAMP NOT NULL,
    user_id INTEGER NOT NULL,
    share_hash TEXT,
    is_block INTEGER NOT NULL CHECK(is_block IN (0, 1)),
    level REAL NOT NULL,
    billable INTEGER NOT NULL CHECK(billable IN (0, 1)),
    shares_consumed INTEGER NOT NULL CHECK(shares_consumed >= 1 AND shares_consumed <= 5),
    coinbase_prefix_tag TEXT NOT NULL,
    block_height TEXT,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
)
"""

# Share validation table - detailed mining parameters for hash verification
SHARE_VALIDATION_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS share_validation (
    share_id INTEGER PRIMARY KEY,
    nonce BIGINT NOT NULL,
    ntime INTEGER NOT NULL,
    version INTEGER NOT NULL,
    coinbase_address TEXT NOT NULL,
    prev_block_hash TEXT,
    bits TEXT,
    extranonce TEXT,
    coinbase_value TEXT,
    witness_commitment TEXT,
    FOREIGN KEY (share_id) REFERENCES share_events(id) ON DELETE CASCADE
)
"""

# Share merkle path table - merkle path hashes for coinbase transaction verification
SHARE_MERKLE_PATH_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS share_merkle_path (
    share_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    merkle_hash TEXT NOT NULL,
    PRIMARY KEY (share_id, position),
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

# Index for user share history queries
USER_SHARE_HISTORY_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_share_events_user_time
ON share_events(user_id, submitted_at)
"""

# Index for billable share quota calculations
BILLABLE_SHARES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_share_events_billable
ON share_events(billable)
"""

# Index for highscore queries (level-based ranking)
HIGHSCORE_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_share_events_level_time
ON share_events(level DESC, submitted_at DESC)
"""

# Index for recent shares queries (time-based ordering)
RECENT_SHARES_INDEX_SQL = """
CREATE INDEX IF NOT EXISTS idx_share_events_submitted_at
ON share_events(submitted_at DESC)
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
    SHARE_VALIDATION_TABLE_SQL,
    SHARE_MERKLE_PATH_TABLE_SQL,
    GLOBAL_STATE_TABLE_SQL,
    AUTH_CHALLENGES_TABLE_SQL,
]

# All index creation statements
ALL_INDEXES = [
    USER_SHARE_HISTORY_INDEX_SQL,
    BILLABLE_SHARES_INDEX_SQL,
    HIGHSCORE_INDEX_SQL,
    RECENT_SHARES_INDEX_SQL,
    RECOVERY_INDEX_SQL,
    TRANSACTIONS_USER_INDEX_SQL,
    AUTH_CHALLENGES_INDEX_SQL,
    USERS_LIGHTNING_PUBKEY_INDEX_SQL,
]
