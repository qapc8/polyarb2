"""Helpers for loading configuration from disk or environment."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from .settings import Settings, load_settings

DEFAULT_CONFIG_PATH = Path("config.yaml")


def load(path: Optional[str | Path] = None) -> Settings:
    """Load settings from *path* or the default location."""

    target = Path(path) if path is not None else DEFAULT_CONFIG_PATH
    return load_settings(target)
