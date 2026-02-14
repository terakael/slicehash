"""CLI tool for adding dummy share events for testing.

This script allows manual insertion of share events for testing and POC
demonstrations to visualize what the shares page looks like with data.

Usage:
    python scripts/add_share.py --user-id "test-user" --level 30
    python scripts/add_share.py --user-id "test-user" --level 100 --is-block
"""

import argparse
import asyncio
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from slicehash.config import load_config
from slicehash.db.manager import DatabaseManager
from slicehash.hash_utils import calculate_level


def generate_hash_with_level(level: int) -> str:
    """Generate a dummy hash with specified number of leading zeros.

    Args:
        level: Desired level ((leading zeros - 5) * 10)

    Returns:
        Hexadecimal hash string
    """
    leading_zeros = (level // 10) + 5
    hash_str = "0" * leading_zeros
    # Add random hex characters for the rest
    remaining_length = 64 - leading_zeros
    hash_str += ''.join(random.choice('0123456789abcdef') for _ in range(remaining_length))
    return hash_str


async def add_share_event(
    db,
    user_id: str,
    level: int,
    is_block: bool = False,
    billable: bool = True,
    shares_consumed: int = 1,
    timestamp_offset_minutes: int = 0
):
    """Add a share event to the database.

    Args:
        db: Database connection
        user_id: User identifier string
        level: Share level (leading zeros - 5)
        is_block: Whether this share found a block
        billable: Whether this share is billable
        shares_consumed: Number of shares consumed
        timestamp_offset_minutes: Minutes to subtract from current time
    """
    # Generate dummy data
    nonce = random.randint(1000000, 9999999999)
    version = random.choice([0x20000000, 0x30000000])

    # Calculate timestamp
    submitted_time = datetime.now() - timedelta(minutes=timestamp_offset_minutes)
    ntime = int(submitted_time.timestamp())
    submitted_at = submitted_time.isoformat()

    # Generate addresses
    coinbase_address = f"bc1q{''.join(random.choice('023456789acdefghjklmnpqrstuvwxyz') for _ in range(39))}"
    coinbase_prefix_tag = f"user-{user_id}"

    # Generate hash
    share_hash = generate_hash_with_level(level)

    # Dummy block height
    block_height = str(850000 + random.randint(0, 1000))

    # Insert into share_events (main table)
    share_id = await db.fetchval(
        """
        INSERT INTO share_events
        (user_id, share_hash, is_block, level, billable, shares_consumed,
         coinbase_prefix_tag, block_height, submitted_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        RETURNING id
        """,
        user_id,
        share_hash,
        is_block,
        level,
        billable,
        shares_consumed,
        coinbase_prefix_tag,
        block_height,
        submitted_at
    )

    # Insert into share_validation (detailed parameters)
    await db.execute(
        """
        INSERT INTO share_validation
        (share_id, nonce, ntime, version, coinbase_address,
         prev_block_hash, bits, extranonce, coinbase_value, witness_commitment)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
        """,
        share_id,
        nonce,
        ntime,
        version,
        coinbase_address,
        None,  # prev_block_hash
        None,  # bits
        None,  # extranonce
        None,  # coinbase_value
        None,  # witness_commitment
    )


async def add_batch_shares(db, user_id: str, count: int, priority: int = 1):
    """Add a batch of random share events.

    Args:
        db: Database connection
        user_id: User identifier
        count: Number of shares to generate
        priority: Priority multiplier (1-5) - shares consumed per billable share
    """
    print(f"Generating {count} random shares with priority={priority}...")

    for i in range(count):
        # Generate random level between 10 and 100, with bias towards lower levels
        # Most shares are level 10, progressively rarer for higher levels
        level = random.choices(
            range(10, 101, 10),
            weights=[50, 30, 10, 5, 3, 1, 0.5, 0.3, 0.2, 0.1]
        )[0]

        # Random timestamp offset (last 24 hours)
        offset = random.randint(0, 1440)

        # All shares are billable now (levels start at 10)
        billable = True

        # Shares consumed equals priority multiplier
        shares_consumed = priority

        await add_share_event(
            db,
            user_id,
            level,
            is_block=False,
            billable=billable,
            shares_consumed=shares_consumed,
            timestamp_offset_minutes=offset
        )

        if (i + 1) % 10 == 0:
            print(f"  Generated {i + 1}/{count} shares...")


async def main():
    """Main CLI execution."""
    parser = argparse.ArgumentParser(
        description="Add dummy share events for testing the UI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add a single level 30 share
  python scripts/add_share.py --user-id "1" --level 30

  # Add a block share (level 100)
  python scripts/add_share.py --user-id "1" --level 100 --is-block

  # Generate 50 random shares
  python scripts/add_share.py --user-id "1" --batch 50

  # Use custom config file location
  python scripts/add_share.py --user-id "1" --level 50 --config /path/to/config.yaml
        """
    )

    parser.add_argument(
        "--user-id",
        required=True,
        help="User ID string (e.g., '1' or 'test-user')"
    )
    parser.add_argument(
        "--level",
        type=int,
        help="Share level ((leading zeros - 5) * 10), typically 10-640"
    )
    parser.add_argument(
        "--is-block",
        action="store_true",
        help="Mark this share as a found block"
    )
    parser.add_argument(
        "--batch",
        type=int,
        help="Generate N random shares instead of a single share"
    )
    parser.add_argument(
        "--priority",
        type=int,
        default=1,
        choices=range(1, 6),
        help="Priority multiplier (1-5, default 1) - shares consumed per billable share"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)"
    )

    args = parser.parse_args()

    # Validate arguments
    if args.batch and args.level is not None:
        print("Error: Cannot specify both --batch and --level", file=sys.stderr)
        return 1

    if not args.batch and args.level is None:
        print("Error: Must specify either --level or --batch", file=sys.stderr)
        return 1

    try:
        # Load configuration
        config = load_config(args.config)
        print(f"Loaded config from: {args.config}")
        print(f"Database: {config.database_url}")
        print()

        async with DatabaseManager(config.database_url) as db:
            if args.batch:
                # Generate batch of random shares
                await add_batch_shares(db, args.user_id, args.batch, args.priority)
                print()
                print(f"✓ Successfully generated {args.batch} shares for user '{args.user_id}' with priority {args.priority}")
            else:
                # Generate single share (all shares are billable)
                await add_share_event(
                    db,
                    args.user_id,
                    args.level,
                    is_block=args.is_block,
                    billable=True,
                    shares_consumed=args.priority
                )

                # Display confirmation
                print("✓ Share event added successfully")
                print()
                print(f"User ID:    {args.user_id}")
                print(f"Level:      {args.level}")
                print(f"Is Block:   {args.is_block}")
                print(f"Hash:       {generate_hash_with_level(args.level)[:20]}...")

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
