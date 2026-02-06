"""CLI tool for inspecting database state.

This script displays all users, transactions, share events, and quota calculations
for debugging and verification purposes.

Usage:
    python scripts/inspect_db.py
    python scripts/inspect_db.py --config /path/to/config.yaml
"""

import argparse
import asyncio
import sys
from pathlib import Path
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from slicehash.config import load_config
from slicehash.db.manager import DatabaseManager


def format_timestamp(ts: str) -> str:
    """Format ISO timestamp to readable format.

    Args:
        ts: ISO 8601 timestamp string

    Returns:
        Human-readable datetime string
    """
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, TypeError):
        return ts


async def main():
    """Main CLI execution."""
    parser = argparse.ArgumentParser(
        description="Inspect SliceHash database state and quota calculations",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Inspect default database
  python scripts/inspect_db.py

  # Use custom config file location
  python scripts/inspect_db.py --config /path/to/config.yaml
        """
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)"
    )

    args = parser.parse_args()

    try:
        # Load configuration
        config = load_config(args.config)
        db_path = Path(config.database_path)

        if not db_path.exists():
            print(f"Error: Database not found at {config.database_path}", file=sys.stderr)
            print("\nRun add_transaction.py to initialize the database first.", file=sys.stderr)
            return 1

        async with DatabaseManager(config.database_path) as db:
            # Get all users with quota calculations
            print("=" * 80)
            print("USERS")
            print("=" * 80)
            print()

            cursor = await db.execute("""
                SELECT
                    user_id,
                    address,
                    tag,
                    priority_multiplier,
                    created_at
                FROM users
                ORDER BY user_id
            """)
            users = await cursor.fetchall()

            if not users:
                print("No users found.")
                print()
            else:
                for user in users:
                    user_id, address, tag, priority, created_at = user

                    # Get transaction total
                    cursor = await db.execute(
                        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = ?",
                        (user_id,)
                    )
                    total_purchased = (await cursor.fetchone())[0]

                    # Get billable shares consumed
                    cursor = await db.execute(
                        "SELECT COALESCE(SUM(shares_consumed), 0) FROM share_events WHERE user_id = ? AND billable = 1",
                        (user_id,)
                    )
                    total_consumed = (await cursor.fetchone())[0]

                    shares_remaining = total_purchased - total_consumed

                    print(f"User ID:            {user_id}")
                    print(f"Address:            {address}")
                    print(f"Tag:                {tag or '(none)'}")
                    print(f"Priority Multiplier: {priority}x")
                    print(f"Created:            {format_timestamp(created_at)}")
                    print()
                    print(f"  Total purchased:   {total_purchased} shares")
                    print(f"  Total consumed:    {total_consumed} shares (billable only)")
                    print(f"  Shares remaining:  {shares_remaining} shares")
                    print()
                    print("-" * 80)
                    print()

            # Get total share events count
            cursor = await db.execute("SELECT COUNT(*) FROM share_events")
            total_events = (await cursor.fetchone())[0]

            print("=" * 80)
            print(f"SHARE EVENTS (Total: {total_events})")
            print("=" * 80)
            print()

            if total_events == 0:
                print("No share events recorded yet.")
                print()
            else:
                # Show recent share events
                cursor = await db.execute("""
                    SELECT
                        id,
                        submitted_at,
                        user_id,
                        channel_id,
                        share_difficulty,
                        billable,
                        shares_consumed
                    FROM share_events
                    ORDER BY submitted_at DESC
                    LIMIT 10
                """)
                events = await cursor.fetchall()

                print("Recent share events (last 10):")
                print()
                print(f"{'ID':<8} {'Time':<20} {'User':<6} {'Channel':<12} {'Difficulty':<12} {'Bill':<6} {'Consumed':<8}")
                print("-" * 80)

                for event in events:
                    event_id, submitted_at, user_id, channel_id, difficulty, billable, consumed = event
                    time_str = format_timestamp(submitted_at)
                    channel_str = (channel_id[:10] + "..") if channel_id and len(channel_id) > 12 else (channel_id or "N/A")
                    billable_str = "Yes" if billable else "No"

                    print(f"{event_id:<8} {time_str:<20} {user_id:<6} {channel_str:<12} {difficulty:<12.2f} {billable_str:<6} {consumed:<8}")

                print()

                # Show billable vs non-billable breakdown
                cursor = await db.execute("""
                    SELECT
                        billable,
                        COUNT(*) as count,
                        COALESCE(SUM(shares_consumed), 0) as total_consumed
                    FROM share_events
                    GROUP BY billable
                """)
                breakdown = await cursor.fetchall()

                print("Breakdown by billable status:")
                print()
                for row in breakdown:
                    billable, count, consumed = row
                    status = "Billable" if billable else "Non-billable"
                    print(f"  {status:12}: {count:6} events, {consumed:8} shares consumed")
                print()

            # Get total transactions
            cursor = await db.execute("SELECT COUNT(*) FROM transactions")
            total_transactions = (await cursor.fetchone())[0]

            print("=" * 80)
            print(f"TRANSACTIONS (Total: {total_transactions})")
            print("=" * 80)
            print()

            if total_transactions == 0:
                print("No transactions recorded yet.")
                print()
            else:
                cursor = await db.execute("""
                    SELECT
                        t.transaction_id,
                        t.user_id,
                        u.address,
                        t.amount,
                        t.created_at
                    FROM transactions t
                    JOIN users u ON t.user_id = u.user_id
                    ORDER BY t.created_at DESC
                    LIMIT 20
                """)
                transactions = await cursor.fetchall()

                print(f"{'ID':<8} {'User':<6} {'Address':<30} {'Amount':<10} {'Created':<20}")
                print("-" * 80)

                for txn in transactions:
                    txn_id, user_id, address, amount, created_at = txn
                    time_str = format_timestamp(created_at)
                    addr_short = address[:27] + "..." if len(address) > 30 else address

                    print(f"{txn_id:<8} {user_id:<6} {addr_short:<30} {amount:<10} {time_str:<20}")

                print()

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"\nPlease create {args.config} based on config.example.yaml", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
