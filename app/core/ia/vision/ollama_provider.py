import ollama
import base64
from typing import Dict, Any
from pathlib import Path
from .base import VisionProvider
import logging
import asyncio

logger = logging.getLogger(__name__)

class OllamaVisionProvider(VisionProvider):
    """Proveedor de visión usando Ollama con modelo gemma3:4b."""
    
    def __init__(self, model_name: str = "gemma3:4b", host: str = None):
        self.model_name = model_name
        self.client = ollama.AsyncClient(host=host)
        logger.info(f"Proveedor Ollama Vision inicializado con el modelo: {self.model_name}")
    
    def _encode_image_to_base64(self, image_path: Path) -> str:
        """Convierte una imagen a base64 para envío a Ollama."""
        try:
            with open(image_path, 'rb') as image_file:
                image_data = image_file.read()
                base64_string = base64.b64encode(image_data).decode('utf-8')
                return base64_string
        except Exception as e:
            logger.error(f"Error al codificar imagen {image_path}: {e}")
            raise
    
    async def analyze_image_async(self, image_path: Path, prompt: str) -> Dict[str, Any]:
        """
        Analiza una imagen con un prompt específico usando Ollama.
        
        Args:
            image_path: Ruta a la imagen a analizar
            prompt: Prompt/pregunta sobre la imagen
            
        Returns:
            Dict con la respuesta del modelo y metadatos
        """
        try:
            if not image_path.exists():
                raise FileNotFoundError(f"Imagen no encontrada: {image_path}")
            
            logger.info(f"Analizando imagen: {image_path.name} con prompt: '{prompt[:50]}...'")
            
            # Codificar imagen a base64
            base64_image = self._encode_image_to_base64(image_path)
            
            # Preparar el mensaje para Ollama
            messages = [
                {
                    "role": "user",
                    "content": prompt,
                    "images": [base64_image]
                }
            ]
            
            # Llamar al modelo de visión
            response = await self.client.chat(
                model=self.model_name,
                messages=messages,
                stream=False
            )
            
            result = {
                "response": response.get("message", {}).get("content", ""),
                "model": self.model_name,
                "image_path": str(image_path),
                "prompt": prompt,
                "success": True,
                "error": None
            }
            
            logger.info(f"Análisis completado para {image_path.name}")
            return result
            
        except Exception as e:
            error_msg = f"Error al analizar imagen con Ollama ({self.model_name}): {e}"
            logger.error(error_msg)
            return {
                "response": "",
                "model": self.model_name,
                "image_path": str(image_path),
                "prompt": prompt,
                "success": False,
                "error": error_msg
            }
    
    async def describe_image_async(self, image_path: Path) -> str:
        """
        Genera una descripción automática de la imagen.
        
        Args:
            image_path: Ruta a la imagen a describir
            
        Returns:
            Descripción de la imagen
        """
        prompt = "Describe en detalle lo que ves en esta imagen. Incluye objetos, personas, texto visible, colores, composición y cualquier detalle relevante."
        
        result = await self.analyze_image_async(image_path, prompt)
        
        if result["success"]:
            return result["response"]
        else:
            logger.error(f"Error en descripción automática: {result['error']}")
            return f"Error al describir la imagen: {result['error']}"
