import google.generativeai as genai
from typing import List
from .base import EmbeddingProvider
import logging
import asyncio

logger = logging.getLogger(__name__)

class GeminiProvider(EmbeddingProvider):
    def __init__(self, api_key: str, model_name: str):
        self.model_name = model_name
        if not api_key:
            raise ValueError("API key de Gemini no fue proporcionada.")
        genai.configure(api_key=api_key)
        logger.info(f"Proveedor Gemini inicializado con el modelo: {self.model_name}")

    async def get_embedding_async(self, text: str) -> List[float]:
        try:
            result = await asyncio.to_thread(
                genai.embed_content,
                model=self.model_name,
                content=text,
                task_type="RETRIEVAL_DOCUMENT"
            )
            return result.get("embedding", [])
        except Exception as e:
            logger.error(f"Error al generar embedding con Gemini ({self.model_name}): {e}")
            raise