"""CLI tool for manual transaction insertion.

This script allows manual crediting of shares to user accounts for testing
and POC demonstrations before payment integration is implemented.

Usage:
    python scripts/add_transaction.py --address bc1q... --amount 1000 --tag "TestUser"
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from slicehash.config import load_config
from slicehash.db.manager import DatabaseManager, init_database, get_or_create_user, add_transaction


async def calculate_shares_remaining(db, user_id: int) -> tuple[int, int, int]:
    """Calculate shares remaining for a user.

    Args:
        db: Active database connection
        user_id: User ID to calculate for

    Returns:
        Tuple of (total_purchased, total_consumed, shares_remaining)
    """
    # Calculate total shares purchased from transactions
    total_purchased = await db.fetchval(
        "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE user_id = $1",
        user_id
    )

    # Calculate total billable shares consumed
    total_consumed = await db.fetchval(
        "SELECT COALESCE(SUM(shares_consumed), 0) FROM share_events WHERE user_id = $1 AND billable = true",
        user_id
    )

    shares_remaining = total_purchased - total_consumed

    return total_purchased, total_consumed, shares_remaining


async def main():
    """Main CLI execution."""
    parser = argparse.ArgumentParser(
        description="Add a manual transaction to credit shares to a user account",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add 1000 shares to a new user
  python scripts/add_transaction.py --address bc1qtest123 --amount 1000 --tag "TestUser"

  # Add more shares to an existing user (tag will be ignored if user exists)
  python scripts/add_transaction.py --address bc1qtest123 --amount 500

  # Use custom config file location
  python scripts/add_transaction.py --address bc1qtest123 --amount 1000 --config /path/to/config.yaml
        """
    )

    parser.add_argument(
        "--address",
        required=True,
        help="Bitcoin address (unique identifier for user)"
    )
    parser.add_argument(
        "--amount",
        type=int,
        required=True,
        help="Number of shares to credit (must be positive integer)"
    )
    parser.add_argument(
        "--tag",
        help="Optional custom label for the user (only used when creating new user)"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)"
    )

    args = parser.parse_args()

    # Validate amount
    if args.amount <= 0:
        print(f"Error: Amount must be positive, got {args.amount}", file=sys.stderr)
        return 1

    try:
        # Load configuration
        config = load_config(args.config)
        print(f"Loaded config from: {args.config}")
        print(f"Database: {config.database_url}")
        print()

        # Initialize database if needed
        await init_database(config.database_url)
        print("Database initialized successfully")
        print()

        # Add transaction
        async with DatabaseManager(config.database_url) as db:
            # Get or create user
            user_id = await get_or_create_user(db, args.address, args.tag)

            # Check if user already existed
            row = await db.fetchrow(
                "SELECT tag FROM users WHERE user_id = $1",
                user_id
            )
            existing_tag = row['tag'] if row else None

            # Add transaction
            transaction_id = await add_transaction(db, user_id, args.amount)

            # Calculate current shares
            total_purchased, total_consumed, shares_remaining = await calculate_shares_remaining(db, user_id)

            # Display confirmation
            print("✓ Transaction added successfully")
            print()
            print(f"User ID:        {user_id}")
            print(f"Address:        {args.address}")
            if existing_tag:
                print(f"Tag:            {existing_tag}")
            print(f"Transaction ID: {transaction_id}")
            print(f"Amount:         {args.amount} shares")
            print()
            print("Current Balance:")
            print(f"  Total purchased:   {total_purchased} shares")
            print(f"  Total consumed:    {total_consumed} shares")
            print(f"  Shares remaining:  {shares_remaining} shares")

        return 0

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"\nPlease create {args.config} based on config.example.yaml", file=sys.stderr)
        return 1
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
