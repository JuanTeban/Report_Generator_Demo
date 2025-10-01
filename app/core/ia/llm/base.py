# app/core/ia/llm/base.py
from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

class LLMResponse(BaseModel):
    """Respuesta estructurada del LLM."""
    content: str
    model: str
    usage: Optional[Dict[str, Any]] = None
    metadata: Optional[Dict[str, Any]] = None

class LLMProvider(ABC):
    """Clase base abstracta para proveedores de LLM."""
    
    @abstractmethod
    async def generate_async(
        self, 
        prompt: str, 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """Genera una respuesta del LLM."""
        pass
    
    @abstractmethod
    async def generate_with_messages_async(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """Genera respuesta con historial de mensajes."""
        pass