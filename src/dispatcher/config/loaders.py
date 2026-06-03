"""Functions to load and parse models.yml and agent.yml files."""

from __future__ import annotations

import logging
import os

import yaml

from config.models import AgentConfig, ConfigError, ModelsConfig

logger = logging.getLogger("[DISPATCHER]")

def load_models_config(path: str = "models.yml") -> ModelsConfig:
    """Load and validate models.yml.

    Args:
        path: Filesystem path to models.yml.

    Returns:
        Validated ModelsConfig instance.

    Raises:
        ConfigError: If the file does not exist or has an invalid format.
    """
    if not os.path.isfile(path):
        raise ConfigError(f"models.yml not found at '{path}'")

    try:
        with open(path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Invalid YAML in models.yml: {exc}") from exc

    if not isinstance(raw, dict) or "models" not in raw:
        raise ConfigError("models.yml must have a top-level 'models' key")

    try:
        config = ModelsConfig(**raw)
    except Exception as exc:
        raise ConfigError(f"Validation error in models.yml: {exc}") from exc

    logger.info(
        "Loaded models.yml with %d model(s): %s",
        len(config.models),
        list(config.models.keys()),
    )
    return config

def load_agent_config(agent_dir: str) -> AgentConfig:
    """Load and validate an agent.yml from a given agent directory.

    The YAML file is expected to have an ``agent:`` top-level key that
    wraps the actual configuration.

    Args:
        agent_dir: Path to the agent directory containing ``agent.yml``.

    Returns:
        Validated AgentConfig instance.

    Raises:
        ConfigError: If the file does not exist or has invalid content.
    """
    config_path = os.path.join(agent_dir, "agent.yml")
    if not os.path.isfile(config_path):
        raise ConfigError(f"agent.yml not found in '{agent_dir}'")

    try:
        with open(config_path, "r", encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigError(
            f"Invalid YAML in {config_path}: {exc}"
        ) from exc

    if not isinstance(raw, dict):
        raise ConfigError(f"agent.yml in '{agent_dir}' is not a mapping")

    # Unwrap the 'agent:' top-level key if present
    if "agent" in raw:
        raw = raw["agent"]

    try:
        config = AgentConfig(**raw)
    except Exception as exc:
        raise ConfigError(
            f"Validation error in {config_path}: {exc}"
        ) from exc

    return config
