import logging
from app.config.settings import (
    EMBEDDING_PROVIDER,
    GEMINI_API_KEY,
    EMBEDDING_MODEL_NAME,
    OLLAMA_HOST
)
from .base import EmbeddingProvider

logger = logging.getLogger(__name__)

def get_embedding_provider() -> EmbeddingProvider:
    provider_name = EMBEDDING_PROVIDER.lower()
    logger.info(f"Cargando proveedor de embedding: '{provider_name}'")

    if provider_name == "gemini":
        from .gemini_provider import GeminiProvider
        return GeminiProvider(api_key=GEMINI_API_KEY, model_name=EMBEDDING_MODEL_NAME)
    
    elif provider_name == "ollama":
        from .ollama_provider import OllamaProvider
        return OllamaProvider(model_name=EMBEDDING_MODEL_NAME, host=OLLAMA_HOST)
        
    else:
        error_msg = f"Proveedor de embedding desconocido: '{provider_name}'. Opciones válidas: 'gemini', 'ollama'."
        logger.error(error_msg)
        raise ValueError(error_msg)