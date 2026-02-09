import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from slicehash.db.manager import DatabaseManager
from slicehash.config import load_config

async def migrate():
    config = load_config("config.yaml")

    async with DatabaseManager(config.database_path) as db:
        # Add lightning_pubkey column to users (without UNIQUE for ALTER TABLE compatibility)
        try:
            await db.execute(
                "ALTER TABLE users ADD COLUMN lightning_pubkey TEXT"
            )
            print("✓ Added lightning_pubkey column to users table")

            # Create unique index separately
            await db.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_users_lightning_pubkey ON users(lightning_pubkey)"
            )
            print("✓ Created unique index on lightning_pubkey")
        except Exception as e:
            print(f"Note: lightning_pubkey column may already exist: {e}")

        # Create auth_challenges table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auth_challenges (
                k1 TEXT PRIMARY KEY,
                created_at INTEGER NOT NULL,
                expires_at INTEGER NOT NULL,
                used INTEGER DEFAULT 0 CHECK(used IN (0, 1))
            )
        """)
        print("✓ Created auth_challenges table")

        # Create auth_tokens table
        await db.execute("""
            CREATE TABLE IF NOT EXISTS auth_tokens (
                k1 TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                token TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (user_id) REFERENCES users(user_id)
            )
        """)
        print("✓ Created auth_tokens table")

        # Create indexes
        await db.execute("""
            CREATE INDEX IF NOT EXISTS idx_auth_challenges_expires
            ON auth_challenges(expires_at)
        """)
        print("✓ Created auth_challenges index")

        await db.commit()
        print("\n✅ Migration completed successfully")

if __name__ == "__main__":
    asyncio.run(migrate())
