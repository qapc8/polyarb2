"""Application settings loaded from configuration."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field


class PolymarketConfig(BaseModel):
    """Endpoints and API configuration for Polymarket services."""

    clob_rest_base: str = Field(..., description="Base URL for the CLOB REST API")
    clob_ws_url: str = Field(..., description="Websocket subscription endpoint")
    markets_api_base: str = Field(..., description="Base URL for market discovery")
    api_key: str | None = Field(default=None, description="API key for authenticated endpoints")
    read_timeout_s: int = 10
    write_timeout_s: int = 5
    ws_heartbeat_s: int = 10


class StrategyConfig(BaseModel):
    """Configuration for strategy level thresholds."""

    epsilon_bps: int = 20
    slippage_bps: int = 15
    min_notional_usd: float = 200.0
    resolution_guard_minutes: int = 60
    reentry_threshold_bps: int = 10
    enable_parity: bool = True
    enable_basket: bool = True
    enable_resolution: bool = True


class RiskConfig(BaseModel):
    """Pre-trade risk guardrails."""

    max_notional_per_market: float = 5_000.0
    max_notional_per_event: float = 15_000.0
    max_concurrent_signals: int = 5
    kill_on_ws_stale_ms: int = 8_000


class PersistenceConfig(BaseModel):
    """Database configuration."""

    dsn: str = "sqlite:///pm_arb.db"


class MetricsConfig(BaseModel):
    """Metrics exposure configuration."""

    prometheus_port: int = 9_308


class LoggingConfig(BaseModel):
    """Logging settings."""

    level: str = "INFO"


class Settings(BaseModel):
    """Top level application settings."""

    polymarket: PolymarketConfig
    strategy: StrategyConfig
    risk: RiskConfig
    persistence: PersistenceConfig
    metrics: MetricsConfig
    logging: LoggingConfig

    model_config = {
        "extra": "ignore",
    }

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> "Settings":
        return cls.model_validate(data)


def _load_yaml(path: Path) -> dict[str, Any]:
    """Load raw YAML data from *path* and expand environment variables."""

    text = path.read_text(encoding="utf-8")
    expanded_text = _expand_env(text)
    data = yaml.safe_load(expanded_text) or {}
    if not isinstance(data, dict):
        raise ValueError("Configuration file must produce a mapping")
    return data


def load_settings(path: str | Path) -> Settings:
    """Load :class:`Settings` from a YAML file."""

    cfg_path = Path(path)
    if not cfg_path.exists():
        raise FileNotFoundError(f"Configuration file not found: {cfg_path}")
    data = _load_yaml(cfg_path)
    return Settings.from_mapping(data)


def _expand_env(value: Any) -> Any:
    import os

    if isinstance(value, str):
        return os.path.expandvars(value)
    if isinstance(value, dict):
        return {k: _expand_env(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand_env(v) for v in value]
    return value
