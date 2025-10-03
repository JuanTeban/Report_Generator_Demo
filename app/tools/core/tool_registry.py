# app/tools/core/tool_registry.py
from typing import Dict, List, Optional, Any
from .base_tool import BaseTool
import logging

logger = logging.getLogger(__name__)

class ToolRegistry:
    """
    Registro centralizado de tools.
    
    Permite:
    - Registro dinámico de tools
    - Recuperación por nombre
    - Generación de schemas para LLM
    """
    
    _tools: Dict[str, BaseTool] = {}
    
    @classmethod
    def register(cls, tool: BaseTool) -> None:
        """Registra una tool en el catálogo"""
        if tool.name in cls._tools:
            logger.warning(f"Tool '{tool.name}' ya registrada, sobrescribiendo")
        cls._tools[tool.name] = tool
        logger.info(f"Tool registrada: {tool.name}")
    
    @classmethod
    def get(cls, name: str) -> Optional[BaseTool]:
        """Obtiene tool por nombre"""
        return cls._tools.get(name)
    
    @classmethod
    def list_all(cls) -> List[BaseTool]:
        """Lista todas las tools registradas"""
        return list(cls._tools.values())
    
    @classmethod
    def list_names(cls) -> List[str]:
        """Lista nombres de tools"""
        return list(cls._tools.keys())
    
    @classmethod
    def get_llm_schemas(cls) -> List[Dict[str, Any]]:
        """
        Genera lista de schemas para LLM function calling.
        
        Returns:
            [
                {"name": "tool1", "description": "...", "parameters": {...}},
                {"name": "tool2", ...}
            ]
        """
        return [tool.to_llm_schema() for tool in cls._tools.values()]
    
    @classmethod
    def clear(cls) -> None:
        """Limpia registro (útil para testing)"""
        cls._tools.clear()

# Decorador para auto-registro
def register_tool(cls):
    """
    Decorador que auto-registra una tool al importarse.
    
    Uso:
        @register_tool
        class MyTool(BaseTool):
            ...
    """
    instance = cls()
    ToolRegistry.register(instance)
    return cls