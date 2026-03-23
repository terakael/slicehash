"""Recalculate all share levels using the current calculate_level formula.

Run this after any change to the level calculation in hash_utils.py to bring
existing share_events rows in line with the new formula.

Usage:
    uv run python scripts/recalculate_levels.py [--config config.yaml]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from slicehash.config import load_config
from slicehash.db.manager import DatabaseManager
from slicehash.hash_utils import calculate_level


async def recalculate_levels(config_path: str) -> int:
    try:
        config = load_config(config_path)
        print(f"Database: {config.database_url}")
        print()

        async with DatabaseManager(config.database_url) as db:
            total = await db.fetchval(
                "SELECT COUNT(*) FROM share_events WHERE share_hash IS NOT NULL"
            )
            print(f"Found {total} shares to recalculate")

            if total == 0:
                print("Nothing to do.")
                return 0

            response = input(f"Recalculate all {total} levels? (y/n): ")
            if response.lower() != "y":
                print("Cancelled.")
                return 0

            print()

            # Stream rows in batches to avoid loading the whole table into memory
            BATCH_SIZE = 5000
            processed = 0
            offset = 0

            while True:
                rows = await db.fetch(
                    """
                    SELECT id, share_hash
                    FROM share_events
                    WHERE share_hash IS NOT NULL
                    ORDER BY id
                    LIMIT $1 OFFSET $2
                    """,
                    BATCH_SIZE,
                    offset,
                )

                if not rows:
                    break

                updates = [
                    (calculate_level(row["share_hash"]), row["id"])
                    for row in rows
                ]

                await db.executemany(
                    "UPDATE share_events SET level = $1 WHERE id = $2",
                    updates,
                )

                processed += len(rows)
                offset += BATCH_SIZE
                print(f"  {processed}/{total}")

            print()
            print(f"Done. Updated {processed} rows.")
            print()

            # Show top 10 as a sanity check
            samples = await db.fetch(
                """
                SELECT share_hash, level
                FROM share_events
                WHERE share_hash IS NOT NULL
                ORDER BY level DESC
                LIMIT 10
                """
            )
            print("Top 10 levels after recalculation:")
            for row in samples:
                print(f"  {row['share_hash'][:20]}...  level {row['level']:.2f}")

    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(f"Create {config_path} based on config.example.yaml", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return 1

    return 0


def main():
    parser = argparse.ArgumentParser(
        description="Recalculate all share levels using the current formula",
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )
    args = parser.parse_args()
    return asyncio.run(recalculate_levels(args.config))


if __name__ == "__main__":
    sys.exit(main())
