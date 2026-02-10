"""Async database connection management and utility functions.

This module provides the DatabaseManager class for managing PostgreSQL connections
with async support via asyncpg, along with utility functions for common
database operations like user creation and transaction logging.
"""

import asyncpg
from typing import Optional
from pathlib import Path

from .schema import ALL_TABLES, ALL_INDEXES


class DatabaseManager:
    """Async context manager for PostgreSQL database connections.

    Provides clean connection lifecycle management with asyncpg.

    Example:
        async with DatabaseManager("postgresql://user:pass@host/db") as db:
            rows = await db.fetch("SELECT * FROM users")
    """

    def __init__(self, database_url: str):
        """Initialize database manager.

        Args:
            database_url: PostgreSQL connection URL
        """
        self.database_url = database_url
        self._connection: Optional[asyncpg.Connection] = None

    async def connect(self) -> asyncpg.Connection:
        """Create async database connection.

        Returns:
            Connected asyncpg.Connection instance
        """
        self._connection = await asyncpg.connect(self.database_url)
        return self._connection

    async def close(self) -> None:
        """Close database connection if open."""
        if self._connection:
            await self._connection.close()
            self._connection = None

    async def __aenter__(self) -> asyncpg.Connection:
        """Async context manager entry."""
        return await self.connect()

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Async context manager exit."""
        await self.close()

    async def get_persistent_connection(self) -> asyncpg.Connection:
        """Create a persistent database connection.

        This method creates a connection that persists beyond the context manager.
        The caller is responsible for closing the connection using close_persistent_connection().

        Returns:
            Connected asyncpg.Connection instance
        """
        return await asyncpg.connect(self.database_url)

    async def close_persistent_connection(self, conn: asyncpg.Connection) -> None:
        """Close a persistent database connection.

        Args:
            conn: The connection to close
        """
        if conn:
            await conn.close()


async def init_database(database_url: str) -> None:
    """Initialize database with schema.

    Creates all tables and indexes defined in schema.py.

    Args:
        database_url: PostgreSQL connection URL

    Raises:
        asyncpg.PostgresError: If database operations fail
    """
    async with DatabaseManager(database_url) as db:
        # Create all tables
        for table_sql in ALL_TABLES:
            await db.execute(table_sql)

        # Create all indexes
        for index_sql in ALL_INDEXES:
            await db.execute(index_sql)


async def get_or_create_user(
    db: asyncpg.Connection,
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
        asyncpg.PostgresError: If database operations fail
    """
    # Check if user exists
    row = await db.fetchrow(
        "SELECT user_id FROM users WHERE address = $1",
        address
    )

    if row:
        return row['user_id']

    # Create new user
    user_id = await db.fetchval(
        "INSERT INTO users (address, tag) VALUES ($1, $2) RETURNING user_id",
        address, tag
    )

    return user_id


async def add_transaction(
    db: asyncpg.Connection,
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
        asyncpg.PostgresError: If database operations fail (e.g., invalid user_id)
    """
    if amount <= 0:
        raise ValueError(f"Transaction amount must be positive, got {amount}")

    transaction_id = await db.fetchval(
        "INSERT INTO transactions (user_id, amount) VALUES ($1, $2) RETURNING transaction_id",
        user_id, amount
    )

    return transaction_id
