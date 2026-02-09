"""Configuration management for SliceHash mining backend.

This module provides configuration loading and validation using Pydantic models.
Configuration is loaded from YAML files and validated against a schema.
"""

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, HttpUrl


class Config(BaseModel):
    """SliceHash runtime configuration.

    Attributes:
        billable_difficulty_threshold: Minimum difficulty for shares to count toward quota.
            Shares with difficulty >= this value are considered billable.
        pool_url: HTTP URL of the SV2 pool for coinbase address updates.
        database_path: Path to the SQLite database file for storing mining state.
        jwt_secret: Secret key for JWT token signing.
        jwt_expiration_seconds: JWT token expiration in seconds.
        lnurl_callback_url: Public callback URL for LNURL-auth.
        auth_challenge_expiration_seconds: k1 challenge expiration in seconds.
    """

    billable_difficulty_threshold: float = Field(
        gt=0,
        description="Minimum difficulty for billable shares"
    )
    pool_url: HttpUrl = Field(
        description="URL of the SV2 pool"
    )
    database_path: str = Field(
        description="Path to SQLite database file"
    )
    jwt_secret: str = Field(
        description="Secret key for JWT token signing (generate with: openssl rand -hex 32)"
    )
    jwt_expiration_seconds: int = Field(
        default=2592000,
        gt=0,
        description="JWT token expiration in seconds"
    )
    lnurl_callback_url: str = Field(
        description="Public callback URL for LNURL-auth (must be HTTPS in production)"
    )
    auth_challenge_expiration_seconds: int = Field(
        default=300,
        gt=0,
        description="k1 challenge expiration in seconds"
    )


def load_config(path: str = "config.yaml") -> Config:
    """Load and validate configuration from a YAML file.

    Args:
        path: Path to the YAML configuration file. Defaults to "config.yaml".

    Returns:
        Validated Config instance.

    Raises:
        FileNotFoundError: If the configuration file doesn't exist.
        yaml.YAMLError: If the file contains invalid YAML.
        pydantic.ValidationError: If the configuration doesn't match the schema.

    Example:
        >>> config = load_config("config.yaml")
        >>> print(config.billable_difficulty_threshold)
        1000000.0
    """
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuration file not found: {path}\n"
            f"Please create a config.yaml file. See config.example.yaml for reference."
        )

    with open(config_path, "r") as f:
        try:
            data: Any = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise yaml.YAMLError(f"Invalid YAML in {path}: {e}") from e

    if data is None:
        raise ValueError(f"Configuration file {path} is empty")

    try:
        return Config(**data)
    except Exception as e:
        raise ValueError(
            f"Configuration validation failed for {path}:\n{e}"
        ) from e
