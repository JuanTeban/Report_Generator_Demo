# app/tools/implementations/llm_tools.py
from pydantic import Field
from typing import List, Dict, Any

from app.tools.core import BaseTool, ToolInput, ToolOutput, register_tool
from app.core.ia.llm import get_llm_provider
from app.core.report_generator.prompts import PromptManager

@register_tool
class BusinessRulesTool(BaseTool):
    """
    Recupera reglas de negocio relevantes.
    Reutiliza RAGRetriever.get_business_rules()
    """
    
    class Input(ToolInput):
        query: str = Field(
            ...,
            description="Query de búsqueda (módulos, categorías, etc.)"
        )
        top_k: int = Field(
            default=5,
            description="Número de reglas a recuperar"
        )
    
    @property
    def name(self) -> str:
        return "business_rules"
    
    @property
    def description(self) -> str:
        return "Recupera reglas de negocio relevantes desde ChromaDB usando búsqueda semántica"
    
    @property
    def input_schema(self) -> type[ToolInput]:
        return self.Input
    
    def __init__(self):
        from app.core.report_generator.retrieval import RAGRetriever
        self.retriever = RAGRetriever()
    
    async def execute(self, query: str, top_k: int = 5) -> ToolOutput:
        try:
            rules = await self.retriever.get_business_rules(query, top_k)
            
            return ToolOutput(
                success=True,
                data=rules,
                metadata={
                    "count": len(rules),
                    "query": query
                }
            )
        except Exception as e:
            return ToolOutput(
                success=False,
                data=None,
                error=f"Error recuperando business rules: {str(e)}"
            )


@register_tool
class TextGenerationTool(BaseTool):
    """
    Genera texto usando LLM con un prompt específico.
    Tool genérica para cualquier generación de texto.
    """
    
    class Input(ToolInput):
        prompt: str = Field(..., description="Prompt completo para el LLM")
        temperature: float = Field(default=0.7, description="Temperatura (0-1)")
        max_tokens: int = Field(default=2048, description="Tokens máximos")
    
    @property
    def name(self) -> str:
        return "text_generation"
    
    @property
    def description(self) -> str:
        return "Genera texto usando el LLM configurado con un prompt personalizado"
    
    @property
    def input_schema(self) -> type[ToolInput]:
        return self.Input
    
    def __init__(self):
        self.llm = get_llm_provider()
    
    async def execute(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048
    ) -> ToolOutput:
        try:
            response = await self.llm.generate_async(
                prompt,
                temperature=temperature,
                max_tokens=max_tokens
            )
            
            return ToolOutput(
                success=True,
                data=response.content,
                metadata={
                    "model": response.model,
                    "usage": response.usage or {}
                }
            )
        except Exception as e:
            return ToolOutput(
                success=False,
                data=None,
                error=f"Error generando texto: {str(e)}"
            )


@register_tool
class SummaryGenerationTool(BaseTool):
    """
    Genera resumen ejecutivo del reporte.
    Usa PromptManager para construir el prompt.
    """
    
    class Input(ToolInput):
        consultant_name: str = Field(..., description="Nombre del consultor")
        sql_data: List[Dict] = Field(..., description="Datos SQL extraídos")
        rag_context: Dict = Field(..., description="Contexto RAG recuperado")
    
    @property
    def name(self) -> str:
        return "summary_generation"
    
    @property
    def description(self) -> str:
        return "Genera resumen ejecutivo del reporte basado en datos SQL y contexto RAG"
    
    @property
    def input_schema(self) -> type[ToolInput]:
        return self.Input
    
    def __init__(self):
        self.llm = get_llm_provider()
        self.prompt_manager = PromptManager()
    
    async def execute(
        self,
        consultant_name: str,
        sql_data: List[Dict],
        rag_context: Dict
    ) -> ToolOutput:
        try:
            prompt = self.prompt_manager.get_summary_prompt(
                consultant_name,
                sql_data,
                rag_context
            )
            
            response = await self.llm.generate_async(prompt)
            
            return ToolOutput(
                success=True,
                data=response.content,
                metadata={
                    "model": response.model,
                    "usage": response.usage or {},
                    "section": "summary"
                }
            )
        except Exception as e:
            return ToolOutput(
                success=False,
                data=None,
                error=f"Error generando resumen: {str(e)}"
            )


@register_tool
class RecommendationsGenerationTool(BaseTool):
    """
    Genera recomendaciones técnicas.
    Usa PromptManager para construir el prompt.
    """
    
    class Input(ToolInput):
        consultant_name: str = Field(..., description="Nombre del consultor")
        sql_data: List[Dict] = Field(..., description="Datos SQL extraídos")
        rag_context: Dict = Field(..., description="Contexto RAG recuperado")
    
    @property
    def name(self) -> str:
        return "recommendations_generation"
    
    @property
    def description(self) -> str:
        return "Genera recomendaciones técnicas basadas en diagnóstico de defectos"
    
    @property
    def input_schema(self) -> type[ToolInput]:
        return self.Input
    
    def __init__(self):
        self.llm = get_llm_provider()
        self.prompt_manager = PromptManager()
    
    async def execute(
        self,
        consultant_name: str,
        sql_data: List[Dict],
        rag_context: Dict
    ) -> ToolOutput:
        try:
            prompt = self.prompt_manager.get_recommendations_prompt(
                consultant_name,
                sql_data,
                rag_context
            )
            
            response = await self.llm.generate_async(prompt)
            
            return ToolOutput(
                success=True,
                data=response.content,
                metadata={
                    "model": response.model,
                    "usage": response.usage or {},
                    "section": "recommendations"
                }
            )
        except Exception as e:
            return ToolOutput(
                success=False,
                data=None,
                error=f"Error generando recomendaciones: {str(e)}"
            )