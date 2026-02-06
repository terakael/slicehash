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
    user_id INTEGER PRIMARY KEY AUTOINCREMENT,
    address TEXT NOT NULL UNIQUE,
    tag TEXT,
    priority_multiplier INTEGER DEFAULT 1 CHECK(priority_multiplier >= 1 AND priority_multiplier <= 5),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
)
"""

# Transactions table - tracks share purchases for quota calculation
TRANSACTIONS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS transactions (
    transaction_id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    amount INTEGER NOT NULL CHECK(amount > 0),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id)
)
"""

# Share events table - records individual share submissions from pool
SHARE_EVENTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS share_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    submitted_at TEXT NOT NULL,
    user_id INTEGER NOT NULL,
    channel_id TEXT,
    sequence_number INTEGER,
    share_difficulty REAL NOT NULL,
    billable INTEGER NOT NULL CHECK(billable IN (0, 1)),
    shares_consumed INTEGER NOT NULL CHECK(shares_consumed >= 1 AND shares_consumed <= 5),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
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

# All table creation statements in order
ALL_TABLES = [
    USERS_TABLE_SQL,
    TRANSACTIONS_TABLE_SQL,
    SHARE_EVENTS_TABLE_SQL,
]

# All index creation statements
ALL_INDEXES = [
    USER_SHARE_HISTORY_INDEX_SQL,
    BILLABLE_SHARES_INDEX_SQL,
]
