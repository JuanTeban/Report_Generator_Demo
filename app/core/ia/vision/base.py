from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from pathlib import Path

class VisionProvider(ABC):
    """Clase base abstracta para proveedores de visión."""
    
    @abstractmethod
    async def analyze_image_async(self, image_path: Path, prompt: str) -> Dict[str, Any]:
        """
        Analiza una imagen con un prompt específico.
        
        Args:
            image_path: Ruta a la imagen a analizar
            prompt: Prompt/pregunta sobre la imagen
            
        Returns:
            Dict con la respuesta del modelo y metadatos
        """
        pass
    
    @abstractmethod
    async def describe_image_async(self, image_path: Path) -> str:
        """
        Genera una descripción automática de la imagen.
        
        Args:
            image_path: Ruta a la imagen a describir
            
        Returns:
            Descripción de la imagen
        """
        pass
