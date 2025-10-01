# app/core/ia/llm/__init__.py
import logging
from typing import Optional
from app.config.settings import LLM_PROVIDER, LLM_MODEL_NAME
from .base import LLMProvider

logger = logging.getLogger(__name__)

def get_llm_provider() -> LLMProvider:
    """Factory function para obtener el proveedor de LLM configurado."""
    provider_name = LLM_PROVIDER.lower()
    logger.info(f"Cargando proveedor LLM: '{provider_name}'")

    if provider_name == "cerebras":
        from .cerebras_provider import CerebrasProvider
        return CerebrasProvider(model_name=LLM_MODEL_NAME)
    
    elif provider_name == "ollama":
        from .ollama_provider import OllamaLLMProvider
        return OllamaLLMProvider(model_name=LLM_MODEL_NAME)
    
    else:
        error_msg = f"Proveedor LLM desconocido: '{provider_name}'"
        logger.error(error_msg)
        raise ValueError(error_msg)