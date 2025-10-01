# app/core/ia/llm/cerebras_provider.py
import httpx
import logging
from typing import Dict, Any, Optional, List
from .base import LLMProvider, LLMResponse
import os
logger = logging.getLogger(__name__)

class CerebrasProvider(LLMProvider):
    """Proveedor de LLM usando Cerebras Cloud."""
    
    def __init__(
        self, 
        model_name: str = "llama3-70b",
        api_key: Optional[str] = None,
        api_url: str = "https://api.cerebras.ai/v1/chat/completions"
    ):
        self.model_name = model_name
        self.api_key = api_key or os.getenv("CEREBRAS_API_KEY")
        self.api_url = api_url
        
        if not self.api_key:
            raise ValueError("API key de Cerebras no configurada")
        
        logger.info(f"Proveedor Cerebras inicializado con modelo: {self.model_name}")
    
    async def generate_async(
        self, 
        prompt: str, 
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        system_prompt: Optional[str] = None
    ) -> LLMResponse:
        """Genera una respuesta usando Cerebras."""
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        return await self.generate_with_messages_async(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens
        )
    
    async def generate_with_messages_async(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None
    ) -> LLMResponse:
        """Genera respuesta con historial de mensajes."""
        
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens or 2048,
        }
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    self.api_url,
                    json=payload,
                    headers=headers,
                    timeout=60.0
                )
                response.raise_for_status()
                
                data = response.json()
                
                return LLMResponse(
                    content=data["choices"][0]["message"]["content"],
                    model=self.model_name,
                    usage=data.get("usage"),
                    metadata={"finish_reason": data["choices"][0].get("finish_reason")}
                )
                
        except Exception as e:
            logger.error(f"Error en Cerebras API: {e}")
            raise