# SliceHash Mining Backend

Fair-rotation mining pool backend that guarantees every user with remaining quota gets their turn to mine.

## Overview

SliceHash is a backend system for managing fair mining rotation across multiple users sharing a single mining pool connection. The system receives share submission webhooks from the pool, tracks quota consumption, and updates the active miner's coinbase address to ensure equitable rotation.

**Architecture:**

- Backend receives share webhooks from SV2 pool
- Tracks billable shares against user quotas
- Manages rotation queue with priority multipliers (1-5x)
- Calls pool API to update active coinbase address

**Current Status:** Phase 1 - Foundation (Database & Configuration)

## Prerequisites

- Python 3.11 or higher
- [uv](https://github.com/astral-sh/uv) package manager

## Installation

1. Clone the repository:
```bash
git clone <repository-url>
cd slicehash
```

2. Install dependencies:
```bash
uv sync
```

3. Create configuration file:
```bash
cp config.example.yaml config.yaml
```

4. Edit `config.yaml` with your settings:
   - `billable_difficulty_threshold`: Minimum difficulty for shares to count toward quota
   - `pool_url`: URL of your SV2 pool for API calls
   - `database_path`: Path to SQLite database file (created automatically)

## Development Usage

### Initialize Database

The database is automatically initialized on first use of any script. No manual setup required.

### Add Test Transactions

Manually credit shares to a user account for testing:

```bash
# Add 1000 shares to a new user
uv run python scripts/add_transaction.py --address bc1qtest123 --amount 1000 --tag "TestUser"

# Add more shares to existing user
uv run python scripts/add_transaction.py --address bc1qtest123 --amount 500

# Use custom config path
uv run python scripts/add_transaction.py --address bc1qtest123 --amount 1000 --config /path/to/config.yaml
```

**Options:**

- `--address`: Bitcoin address (required, unique identifier)
- `--amount`: Number of shares to credit (required, positive integer)
- `--tag`: Optional label for new users (ignored if user exists)
- `--config`: Path to config file (default: config.yaml)

### Inspect Database

View current database state with quota calculations:

```bash
# Inspect default database
uv run python scripts/inspect_db.py

# Use custom config path
uv run python scripts/inspect_db.py --config /path/to/config.yaml
```

**Displays:**

- All users with addresses, tags, and priority multipliers
- Quota calculations: total purchased, consumed (billable only), remaining
- Recent share events (last 10)
- All transactions with timestamps

## Project Structure

```
slicehash/
├── src/slicehash/          # Core library
│   ├── config.py           # Configuration loading (Pydantic + YAML)
│   └── db/
│       ├── schema.py       # Database schema definitions
│       └── manager.py      # Async database operations
├── scripts/                # CLI tools for manual operations
│   ├── add_transaction.py  # Manually credit shares to users
│   └── inspect_db.py       # View database state and quotas
├── config.example.yaml     # Configuration template
├── config.yaml             # Your configuration (gitignored)
└── pyproject.toml          # Project dependencies
```

## Configuration

### config.yaml

```yaml
# Minimum difficulty for shares to count toward quota
billable_difficulty_threshold: 1000000.0

# URL of the SV2 pool for coinbase address updates
pool_url: "http://localhost:8080"

# Path to SQLite database file (created automatically)
database_path: "slicehash.db"
```

**billable_difficulty_threshold:**

- Shares with difficulty >= this value count toward quota consumption
- Shares below threshold don't consume quota (practice/warm-up shares)
- Adjust based on your pool's difficulty requirements

**pool_url:**

- HTTP endpoint for updating the active miner's coinbase address
- Backend calls this API when rotation occurs
- Use `http://localhost:8080` for local testing

**database_path:**

- Path to SQLite database file for storing state
- Created automatically with schema on first use
- Stores users, transactions, share events, and rotation state

## Database Schema

### users

Stores user accounts with Bitcoin addresses and priority settings.

- `user_id`: Auto-incrementing primary key
- `address`: Bitcoin address (unique)
- `tag`: Optional custom label
- `priority_multiplier`: 1-5x multiplier for rotation weight (default: 1)
- `created_at`: Timestamp

### transactions

Tracks share purchase history for quota calculations.

- `transaction_id`: Auto-incrementing primary key
- `user_id`: Foreign key to users table
- `amount`: Number of shares purchased (must be > 0)
- `created_at`: Timestamp

### share_events

Records individual mining share submissions from pool webhooks.

- `id`: Auto-incrementing primary key
- `submitted_at`: Timestamp from pool
- `user_id`: Foreign key to users table
- `channel_id`: SV2 channel identifier
- `sequence_number`: Share sequence within channel
- `share_difficulty`: Actual difficulty of submitted share
- `billable`: 0 or 1 (based on difficulty threshold)
- `shares_consumed`: 1-5 (based on priority_multiplier)

## Quota Calculation

**Shares remaining** = Total purchased - Total consumed (billable only)

- Users purchase shares via transactions
- Billable shares consume quota based on priority multiplier
- Non-billable shares (below threshold) don't consume quota
- When shares_remaining reaches 0, user is removed from rotation

## License

[Add license information]

## Contributing

[Add contribution guidelines]
