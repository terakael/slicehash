"""Migration script to update level column from INTEGER to REAL and recalculate all levels.

This script:
1. Alters the share_events table to change level from INTEGER to REAL
2. Recalculates all existing share levels using the new floating point formula
3. Updates all share_events records with precise level values

Usage:
    python scripts/migrate_level_to_float.py [--config config.yaml]
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from slicehash.config import load_config
from slicehash.db.manager import DatabaseManager
from slicehash.hash_utils import calculate_level


async def migrate_levels(config_path: str):
    """Migrate level column to REAL and recalculate all levels.

    Args:
        config_path: Path to configuration file
    """
    try:
        # Load configuration
        config = load_config(config_path)
        print(f"Loaded config from: {config_path}")
        print(f"Database: {config.database_url}")
        print()

        async with DatabaseManager(config.database_url) as db:
            # Step 1: Check if migration is needed
            print("Checking current schema...")
            result = await db.fetchval(
                """
                SELECT data_type
                FROM information_schema.columns
                WHERE table_name = 'share_events' AND column_name = 'level'
                """
            )

            if result == 'real' or result == 'double precision':
                print("Level column is already REAL type.")
                response = input("Recalculate levels anyway? (y/n): ")
                if response.lower() != 'y':
                    print("Migration cancelled.")
                    return
            else:
                print(f"Current level column type: {result}")
                print()

                # Step 2: Alter table to change level to REAL
                print("Altering table to change level from INTEGER to REAL...")
                await db.execute(
                    "ALTER TABLE share_events ALTER COLUMN level TYPE REAL"
                )
                print("✓ Table altered successfully")
                print()

            # Step 3: Get all share events with hashes
            print("Fetching all share events...")
            shares = await db.fetch(
                "SELECT id, share_hash FROM share_events WHERE share_hash IS NOT NULL"
            )
            total = len(shares)
            print(f"Found {total} shares to recalculate")
            print()

            if total == 0:
                print("No shares to migrate.")
                return

            # Step 4: Recalculate and update levels
            print("Recalculating levels...")
            updated = 0
            batch_size = 1000

            for i in range(0, total, batch_size):
                batch = shares[i:i + batch_size]

                # Update each share in the batch
                for share in batch:
                    share_id = share['id']
                    share_hash = share['share_hash']

                    # Calculate new precise level
                    new_level = calculate_level(share_hash)

                    # Update in database
                    await db.execute(
                        "UPDATE share_events SET level = $1 WHERE id = $2",
                        new_level,
                        share_id
                    )
                    updated += 1

                # Progress update
                print(f"  Processed {min(i + batch_size, total)}/{total} shares...")

            print()
            print(f"✓ Successfully updated {updated} share levels")

            # Step 5: Show some examples
            print()
            print("Sample updated levels:")
            samples = await db.fetch(
                """
                SELECT share_hash, level
                FROM share_events
                WHERE share_hash IS NOT NULL
                ORDER BY level DESC
                LIMIT 10
                """
            )

            for sample in samples:
                hash_short = sample['share_hash'][:20] + "..."
                level = sample['level']
                print(f"  {hash_short} -> level {level:.2f}")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"\nPlease create {config_path} based on config.example.yaml", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


def main():
    """Main CLI execution."""
    parser = argparse.ArgumentParser(
        description="Migrate level column to REAL and recalculate all levels",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)"
    )

    args = parser.parse_args()

    return asyncio.run(migrate_levels(args.config))


if __name__ == "__main__":
    sys.exit(main())
