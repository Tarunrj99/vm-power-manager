"""Configuration loader with 3-layer merging: bundled_defaults → deployment config → runtime."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

from vm_power_manager.models import Config


_BUNDLED_DEFAULTS_PATH = Path(__file__).parent / "bundled_defaults.yaml"


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base. Override values win."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_bundled_defaults() -> dict[str, Any]:
    """Load Layer 1: bundled defaults shipped with the library."""
    with open(_BUNDLED_DEFAULTS_PATH) as f:
        return yaml.safe_load(f) or {}


def load_config(config_path: str | Path) -> Config:
    """
    Load and merge configuration from all layers.

    Layer 1: bundled_defaults.yaml (library)
    Layer 2: user's config.yaml (deployment)

    Returns a fully validated Config object.
    """
    config_path = Path(config_path)
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    defaults = load_bundled_defaults()

    with open(config_path) as f:
        user_config = yaml.safe_load(f) or {}

    merged = _deep_merge(defaults, user_config)

    return Config.model_validate(merged)


def get_slack_token(config: Config) -> str:
    """Retrieve Slack bot token from environment variable."""
    env_var = config.slack.bot_token_env
    token = os.environ.get(env_var)
    if not token:
        raise EnvironmentError(f"Slack bot token not found in env var: {env_var}")
    return token


def get_slack_signing_secret(config: Config) -> str:
    """Retrieve Slack signing secret from environment variable."""
    env_var = config.slack.signing_secret_env
    secret = os.environ.get(env_var)
    if not secret:
        raise EnvironmentError(f"Slack signing secret not found in env var: {env_var}")
    return secret
