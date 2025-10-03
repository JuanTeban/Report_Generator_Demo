# app/tools/core/base_tool.py
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
from pydantic import BaseModel, Field

class ToolInput(BaseModel):
    """Schema base de entrada para tools"""
    pass

class ToolOutput(BaseModel):
    """Schema estandarizado de salida"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        arbitrary_types_allowed = True

class BaseTool(ABC):
    """
    Clase base abstracta para todas las tools del sistema.
    
    Cada tool debe:
    - Definir un nombre único
    - Proveer descripción clara
    - Especificar schema de entrada (Pydantic)
    - Implementar método execute async
    """
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Nombre único de la tool"""
        pass
    
    @property
    @abstractmethod
    def description(self) -> str:
        """Descripción para LLM function calling"""
        pass
    
    @property
    @abstractmethod
    def input_schema(self) -> type[ToolInput]:
        """Schema Pydantic de entrada"""
        pass
    
    @abstractmethod
    async def execute(self, **kwargs) -> ToolOutput:
        """
        Ejecuta la tool con los parámetros validados.
        
        Los kwargs serán validados automáticamente contra input_schema
        antes de llegar aquí.
        """
        pass
    
    def to_llm_schema(self) -> Dict[str, Any]:
        """
        Genera schema JSON compatible con LLM function calling.
        
        Returns:
            {
                "name": "tool_name",
                "description": "...",
                "parameters": {...}  # JSON Schema
            }
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.input_schema.model_json_schema()
        }
    
    def validate_and_execute(self, **kwargs) -> ToolOutput:
        """
        Valida entrada y ejecuta (wrapper para validación).
        En v2 esto será async, por ahora wrapper sync.
        """
        try:
            # Validar con Pydantic
            validated = self.input_schema(**kwargs)
            # Ejecutar (nota: en producción esto debe ser await)
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                # Si ya hay loop, retornar future
                raise RuntimeError("Use execute() directamente en contexto async")
            return loop.run_until_complete(self.execute(**validated.model_dump()))
        except Exception as e:
            return ToolOutput(success=False, error=str(e))