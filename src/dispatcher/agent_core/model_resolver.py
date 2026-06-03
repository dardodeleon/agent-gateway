"""Resolve a model name from models.yml to a Strands model instance."""

from __future__ import annotations

import logging
import os
from typing import Any

from strands.models.anthropic import AnthropicModel
from strands.models.bedrock import BedrockModel
from strands.models.ollama import OllamaModel
from strands.models.gemini import GeminiModel
from strands.models.openai import OpenAIModel

from config.models import ModelConfig, ModelNotFoundError, ModelsConfig

logger = logging.getLogger("[DISPATCHER]")


def resolve_model(
    model_name: str,
    models_config: ModelsConfig,
) -> AnthropicModel | OllamaModel | BedrockModel | OpenAIModel | GeminiModel:
    """Resolve a model name to a Strands model instance.

    Args:
        model_name: Key into models_config.models.
        models_config: The loaded ModelsConfig.

    Returns:
        A Strands model ready to pass to Agent().

    Raises:
        ModelNotFoundError: If the model name or provider is not recognised.
    """
    if model_name not in models_config.models:
        raise ModelNotFoundError(
            f"Modelo '{model_name}' no encontrado en models.yml"
        )

    mc: ModelConfig = models_config.models[model_name]

    if mc.provider == "anthropic":
        model = AnthropicModel(
            model_id=mc.model_id,
            max_tokens=mc.max_tokens,
            params={"temperature": mc.temperature},
        )
    elif mc.provider == "ollama":
        host = mc.host or os.environ.get(
            "OLLAMA_HOST", "http://localhost:11434"
        )
        model = OllamaModel(
            host=host,
            model_id=mc.model_id,
            temperature=mc.temperature,
            max_tokens=mc.max_tokens,
        )
    elif mc.provider == "bedrock":
        model = BedrockModel(
            model_id=mc.model_id,
            region_name=mc.region_name
            or os.environ.get("AWS_REGION", "us-east-1"),
            temperature=mc.temperature,
            max_tokens=mc.max_tokens,
        )
    elif mc.provider == "openai":
        kwargs: dict[str, Any] = {
            "model_id": mc.model_id,
            "temperature": mc.temperature,
            "max_tokens": mc.max_tokens,
        }
        if mc.host:
            kwargs["client_args"] = {"base_url": mc.host}
        model = OpenAIModel(**kwargs)
    elif mc.provider == "gemini":
        model = GeminiModel(
            model_id=mc.model_id,
            params={
                "temperature": mc.temperature,
                "max_output_tokens": mc.max_tokens,
            },
        )
    else:
        raise ModelNotFoundError(
            f"Provider '{mc.provider}' no soportado "
            "(proveedores disponibles: 'anthropic', 'ollama', "
            "'bedrock', 'openai', 'gemini')"
        )

    logger.debug(
        "Resolved model '%s' -> provider=%s, model_id=%s (temp=%.1f, max_tokens=%d)",
        model_name,
        mc.provider,
        mc.model_id,
        mc.temperature,
        mc.max_tokens,
    )
    return model
