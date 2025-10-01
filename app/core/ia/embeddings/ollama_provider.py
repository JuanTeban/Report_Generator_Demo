import ollama
from typing import List
from .base import EmbeddingProvider
import logging

logger = logging.getLogger(__name__)

class OllamaProvider(EmbeddingProvider):
    def __init__(self, model_name: str, host: str = None):
        self.model_name = model_name
        self.client = ollama.AsyncClient(host=host)
        logger.info(f"Proveedor Ollama inicializado con el modelo: {self.model_name}")

    async def get_embedding_async(self, text: str) -> List[float]:
        try:
            response = await self.client.embeddings(
                model=self.model_name,
                prompt=text
            )
            return response.get("embedding", [])
        except Exception as e:
            logger.error(f"Error al generar embedding con Ollama ({self.model_name}): {e}")
            raise
