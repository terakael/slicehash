#!/usr/bin/env python3
"""Initialize PostgreSQL database with SliceHash schema.

Usage:
    python scripts/init_db.py
    python scripts/init_db.py --config /path/to/config.yaml
    python scripts/init_db.py --drop  # Drop existing tables first
"""

import argparse
import asyncio
import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from slicehash.config import load_config
from slicehash.db.manager import init_database, DatabaseManager


async def drop_tables(database_url: str):
    """Drop all existing tables."""
    print("Dropping all tables...")
    async with DatabaseManager(database_url) as db:
        await db.execute("DROP TABLE IF EXISTS auth_tokens CASCADE")
        await db.execute("DROP TABLE IF EXISTS auth_challenges CASCADE")
        await db.execute("DROP TABLE IF EXISTS share_events CASCADE")
        await db.execute("DROP TABLE IF EXISTS transactions CASCADE")
        await db.execute("DROP TABLE IF EXISTS global_state CASCADE")
        await db.execute("DROP TABLE IF EXISTS users CASCADE")
    print("✓ All tables dropped")


async def main():
    """Main CLI execution."""
    parser = argparse.ArgumentParser(
        description="Initialize PostgreSQL database with SliceHash schema",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Initialize database with schema from config.yaml
  python scripts/init_db.py

  # Drop existing tables and recreate
  python scripts/init_db.py --drop

  # Use custom config file location
  python scripts/init_db.py --config /path/to/config.yaml
        """
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)"
    )
    parser.add_argument(
        "--drop",
        action="store_true",
        help="Drop existing tables before creating new ones"
    )

    args = parser.parse_args()

    try:
        # Load configuration
        config = load_config(args.config)
        print(f"Loaded config from: {args.config}")
        print(f"Database URL: {config.database_url}")
        print()

        # Drop tables if requested
        if args.drop:
            await drop_tables(config.database_url)
            print()

        # Initialize database
        print("Creating tables and indexes...")
        await init_database(config.database_url)
        print("✓ Database initialized successfully")
        print()

        # Verify tables were created
        async with DatabaseManager(config.database_url) as db:
            tables = await db.fetch("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """)

            print("Created tables:")
            for table in tables:
                print(f"  - {table['table_name']}")

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
