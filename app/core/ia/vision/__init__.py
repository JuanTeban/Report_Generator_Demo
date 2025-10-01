import logging
from app.config.settings import (
    VISION_PROVIDER,
    VISION_MODEL_NAME,
    OLLAMA_HOST
)
from .base import VisionProvider

logger = logging.getLogger(__name__)

def get_vision_provider() -> VisionProvider:
    """Factory function para obtener el proveedor de visión configurado."""
    provider_name = VISION_PROVIDER.lower()
    logger.info(f"Cargando proveedor de visión: '{provider_name}'")

    if provider_name == "ollama":
        from .ollama_provider import OllamaVisionProvider
        return OllamaVisionProvider(model_name=VISION_MODEL_NAME, host=OLLAMA_HOST)
    
    else:
        error_msg = f"Proveedor de visión desconocido: '{provider_name}'. Opciones válidas: 'ollama'."
        logger.error(error_msg)
        raise ValueError(error_msg)
