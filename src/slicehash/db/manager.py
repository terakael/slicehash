"""Async database connection management and utility functions.

This module provides the DatabaseManager class for managing SQLite connections
with async support via aiosqlite, along with utility functions for common
database operations like user creation and transaction logging.
"""

import aiosqlite
from typing import Optional
from pathlib import Path

from .schema import ALL_TABLES, ALL_INDEXES


class DatabaseManager:
    """Async context manager for SQLite database connections.

    Automatically enables foreign key constraints and provides clean
    connection lifecycle management.

    Example:
        async with DatabaseManager("slicehash.db") as db:
            cursor = await db.execute("SELECT * FROM users")
            rows = await cursor.fetchall()
    """

    def __init__(self, db_path: str):
        """Initialize database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self._connection: Optional[aiosqlite.Connection] = None

    async def connect(self) -> aiosqlite.Connection:
        """Create async database connection with foreign keys enabled.

        Returns:
            Connected aiosqlite.Connection instance
        """
        self._connection = await aiosqlite.connect(self.db_path)
        # Enable foreign key constraints
        await self._connection.execute("PRAGMA foreign_keys = ON")
        await self._connection.commit()
        return self._connection

    async def close(self) -> None:
        """Close database connection if open."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def __aenter__(self) -> aiosqlite.Connection:
        """Async context manager entry."""
        conn = await self.connect()
        # Performance optimizations
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA synchronous = NORMAL")
        await conn.execute("PRAGMA cache_size = -10000")
        await conn.commit()
        return conn

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def get_persistent_connection(self) -> aiosqlite.Connection:
        """Create a persistent database connection with optimizations.

        This method creates a connection that persists beyond the context manager.
        The caller is responsible for closing the connection using close_persistent_connection().

        Returns:
            Connected aiosqlite.Connection instance with foreign keys enabled
            and performance optimizations applied
        """
        conn = await aiosqlite.connect(self.db_path)
        # Enable foreign key constraints
        await conn.execute("PRAGMA foreign_keys = ON")
        # Performance optimizations
        await conn.execute("PRAGMA journal_mode = WAL")
        await conn.execute("PRAGMA synchronous = NORMAL")
        await conn.execute("PRAGMA cache_size = -10000")
        await conn.commit()
        return conn

    async def close_persistent_connection(self, conn: aiosqlite.Connection) -> None:
        """Close a persistent database connection.

        Performs a checkpoint to flush WAL to main database before closing.

        Args:
            conn: The connection to close
        """
        if conn:
            try:
                # Checkpoint WAL to flush changes to main database file
                await conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                await conn.commit()
            except Exception as e:
                # Log but don't fail on checkpoint errors
                import logging
                logging.getLogger(__name__).warning(f"WAL checkpoint failed: {e}")
            finally:
                await conn.close()


async def init_database(db_path: str) -> None:
    """Initialize database with schema.

    Creates the database file if it doesn't exist, then creates all tables
    and indexes defined in schema.py. Enables foreign key constraints.

    Args:
        db_path: Path to SQLite database file to create/initialize

    Raises:
        aiosqlite.Error: If database operations fail
    """
    # Ensure parent directory exists
    db_file = Path(db_path)
    db_file.parent.mkdir(parents=True, exist_ok=True)

    async with DatabaseManager(db_path) as db:
        # Create all tables
        for table_sql in ALL_TABLES:
            await db.execute(table_sql)

        # Create all indexes
        for index_sql in ALL_INDEXES:
            await db.execute(index_sql)

        await db.commit()


async def get_or_create_user(
    db: aiosqlite.Connection,
    address: str,
    tag: Optional[str] = None
) -> int:
    """Get existing user or create new user by Bitcoin address.

    Args:
        db: Active database connection
        address: Bitcoin address (must be unique)
        tag: Optional custom label for the user (max 50 chars recommended)

    Returns:
        user_id of existing or newly created user

    Raises:
        aiosqlite.Error: If database operations fail
    """
    # Check if user exists
    cursor = await db.execute(
        "SELECT user_id FROM users WHERE address = ?",
        (address,)
    )
    row = await cursor.fetchone()

    if row:
        return row[0]

    # Create new user
    cursor = await db.execute(
        "INSERT INTO users (address, tag) VALUES (?, ?)",
        (address, tag)
    )
    await db.commit()

    return cursor.lastrowid


async def add_transaction(
    db: aiosqlite.Connection,
    user_id: int,
    amount: int
) -> int:
    """Record a share purchase transaction.

    Args:
        db: Active database connection
        user_id: ID of user purchasing shares
        amount: Number of shares purchased (must be > 0)

    Returns:
        transaction_id of newly created transaction

    Raises:
        ValueError: If amount <= 0
        aiosqlite.Error: If database operations fail (e.g., invalid user_id)
    """
    if amount <= 0:
        raise ValueError(f"Transaction amount must be positive, got {amount}")

    cursor = await db.execute(
        "INSERT INTO transactions (user_id, amount) VALUES (?, ?)",
        (user_id, amount)
    )
    await db.commit()

    return cursor.lastrowid
