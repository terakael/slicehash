"""Configuration management for SliceHash mining backend.

This module provides configuration loading and validation using Pydantic models.
Configuration is loaded from YAML files and validated against a schema.
Sensitive fields can be overridden at runtime via environment variables.
"""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field, HttpUrl


# Sensitive fields that can be overridden with environment variables.
# Set these in your shell or k8s Secret manifests instead of storing them in
# the config file.
_ENV_OVERRIDES: dict[str, str] = {
    "DATABASE_USER": "database_user",
    "DATABASE_PASSWORD": "database_password",
    "JWT_SECRET": "jwt_secret",
    "REDIS_PASSWORD": "redis_password",
    "BTC_RPC_USER": "btc_rpc_user",
    "BTC_RPC_PASSWORD": "btc_rpc_password",
    "LIGHTNING_RUNE": "lightning_rune",
}


class Config(BaseModel):
    """SliceHash runtime configuration.

    Attributes:
        billable_difficulty_threshold: Minimum difficulty for shares to count toward quota.
            Shares with difficulty >= this value are considered billable.
        pool_url: HTTP URL of the SV2 pool for coinbase address updates.
        database_host: PostgreSQL server host.
        database_port: PostgreSQL server port.
        database_name: PostgreSQL database name.
        database_user: PostgreSQL username. Override with DATABASE_USER.
        database_password: PostgreSQL password. Override with DATABASE_PASSWORD.
        jwt_secret: Secret key for JWT token signing. Override with JWT_SECRET.
        jwt_expiration_seconds: JWT token expiration in seconds.
        lnurl_callback_url: Public callback URL for LNURL-auth.
        auth_challenge_expiration_seconds: k1 challenge expiration in seconds.
        redis_host: Redis server host.
        redis_port: Redis server port.
        redis_password: Redis authentication password. Override with REDIS_PASSWORD.
        redis_stream_key: Redis stream key name for shares.
        redis_consumer_group: Redis consumer group name.
        redis_consumer_name: Redis consumer name.
        btc_rpc_host: Bitcoin Core RPC server host.
        btc_rpc_port: Bitcoin Core RPC server port.
        btc_rpc_user: Bitcoin Core RPC username. Override with BTC_RPC_USER.
        btc_rpc_password: Bitcoin Core RPC password. Override with BTC_RPC_PASSWORD.
    """

    billable_difficulty_threshold: float = Field(
        gt=0, description="Minimum difficulty for billable shares"
    )
    pool_url: HttpUrl = Field(description="URL of the SV2 pool")

    # PostgreSQL database connection components
    database_host: str = Field(default="localhost", description="PostgreSQL host")
    database_port: int = Field(default=5432, gt=0, description="PostgreSQL port")
    database_name: str = Field(
        default="slicehash", description="PostgreSQL database name"
    )
    database_user: str = Field(description="PostgreSQL username")
    database_password: str = Field(description="PostgreSQL password")

    jwt_secret: str = Field(
        description="Secret key for JWT token signing (generate with: openssl rand -hex 32)"
    )
    jwt_expiration_seconds: int = Field(
        default=900, gt=0, description="Access token (JWT) expiration in seconds"
    )
    refresh_token_expiration_seconds: int = Field(
        default=7776000, gt=0, description="Refresh token expiration in seconds (default: 90 days)"
    )
    lnurl_callback_url: str = Field(
        description="Public callback URL for LNURL-auth (must be HTTPS in production)"
    )
    auth_challenge_expiration_seconds: int = Field(
        default=300, gt=0, description="k1 challenge expiration in seconds"
    )
    redis_host: str = Field(default="localhost", description="Redis server host")
    redis_port: int = Field(default=6379, gt=0, description="Redis server port")
    redis_password: str | None = Field(
        default=None, description="Redis authentication password (optional)"
    )
    redis_stream_key: str = Field(
        default="slicehash:shares", description="Redis stream key name for shares"
    )
    redis_consumer_group: str = Field(
        default="slicehash-processors", description="Redis consumer group name"
    )
    redis_consumer_name: str = Field(
        default="processor-1", description="Redis consumer name"
    )
    is_test_network: bool = Field(
        default=False, description="Enable test network mode with modified block logic"
    )
    test_network_block_level: int = Field(
        default=60, ge=0, description="Block level threshold for test network mode"
    )
    btc_rpc_host: str = Field(default="127.0.0.1", description="Bitcoin Core RPC host")
    btc_rpc_port: int = Field(default=8332, gt=0, description="Bitcoin Core RPC port")
    btc_rpc_user: str = Field(description="Bitcoin Core RPC username")
    btc_rpc_password: str = Field(description="Bitcoin Core RPC password")

    # Core Lightning (CLN) payment settings — optional, payments disabled if not set
    lightning_node_url: str | None = Field(
        default=None, description="CLN clnrest base URL (e.g. https://127.0.0.1:3010)"
    )
    lightning_rune: str | None = Field(
        default=None, description="CLN rune for authentication. Override with LIGHTNING_RUNE."
    )
    lightning_ca_cert: str | None = Field(
        default=None, description="Path to CLN CA certificate for TLS verification"
    )
    sats_per_share: int = Field(
        default=1000, gt=0, description="Price per share in satoshis"
    )
    invoice_expiry_seconds: int = Field(
        default=600, gt=0, description="Lightning invoice expiry in seconds"
    )
    hashrate_ths: float = Field(
        default=6.45, gt=0, description="Miner hashrate in TH/s, used for level probability estimates"
    )

    @property
    def database_url(self) -> str:
        """Construct PostgreSQL connection URL from component fields."""
        return (
            f"postgresql://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


def load_config(path: str = "config.yaml") -> Config:
    """Load and validate configuration from a YAML file.

    Sensitive fields (database_password, jwt_secret, redis_password,
    btc_rpc_user, btc_rpc_password, database_user) can be overridden by
    environment variables — see _ENV_OVERRIDES for the full mapping.
    Environment variables take precedence over values in the YAML file.

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

    # Environment variable overrides — take precedence over the YAML file.
    for env_var, config_key in _ENV_OVERRIDES.items():
        value = os.environ.get(env_var)
        if value is not None:
            data[config_key] = value

    try:
        return Config(**data)
    except Exception as e:
        raise ValueError(f"Configuration validation failed for {path}:\n{e}") from e
