"""Database layer for SliceHash mining backend."""

from .manager import DatabaseManager, init_database

__all__ = [
    "DatabaseManager",
    "init_database",
]
