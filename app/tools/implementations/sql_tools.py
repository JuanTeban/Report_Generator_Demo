# app/tools/implementations/sql_tools.py
import json
import re
from pydantic import Field
from typing import List, Dict, Any

from app.tools.core import BaseTool, ToolInput, ToolOutput, register_tool
from app.core.report_generator.retrieval import RAGRetriever
from app.core.ia.llm import get_llm_provider
from app.core.report_generator.prompts import PromptManager
from app.tools.tools import execute_duckdb_query

@register_tool
class SqlDataExtractionTool(BaseTool):
    """
    Extrae datos SQL de un consultor.
    """
    
    class Input(ToolInput):
        consultant_name: str = Field(
            ...,
            description="Nombre completo del consultor responsable"
        )
    
    @property
    def name(self) -> str:
        return "sql_data_extraction"
    
    @property
    def description(self) -> str:
        return (
            "Ejecuta consulta SQL optimizada para extraer todos los datos "
            "de defectos asignados a un consultor específico desde DuckDB"
        )
    
    @property
    def input_schema(self) -> type[ToolInput]:
        return self.Input
    
    def __init__(self):
        self.retriever = RAGRetriever()
        self.llm = get_llm_provider()
        self.prompt_manager = PromptManager()
    
    async def execute(self, consultant_name: str) -> ToolOutput:
        """
        Ejecuta extracción SQL.
        
        Returns:
            ToolOutput con json_data, row_count, sql_executed
        """
        try:
            schema_context = await self.retriever.get_schema_context(
                f"datos del consultor {consultant_name}"
            )
            
            if not schema_context:
                return ToolOutput(
                    success=False,
                    data=None,
                    error="No se encontró contexto de esquema en la base de datos"
                )
            
            # 2. Generar SQL con LLM
            prompt = self.prompt_manager.get_sql_prompt(
                consultant_name,
                schema_context
            )
            
            sql_response = await self.llm.generate_async(prompt)
            
            # 3. Limpiar SQL
            sql = self._clean_sql(sql_response.content)
            
            # 4. Ejecutar consulta
            result = execute_duckdb_query.invoke({"sql_query": sql})
            data = json.loads(result)
            
            if "json_data" in data and data["json_data"]:
                return ToolOutput(
                    success=True,
                    data=data["json_data"],
                    metadata={
                        "row_count": len(data["json_data"]),
                        "sql_executed": sql,
                        "consultant": consultant_name
                    }
                )
            else:
                return ToolOutput(
                    success=False,
                    data=[],
                    error=f"No se encontraron datos para el consultor: {consultant_name}",
                    metadata={"sql_executed": sql}
                )
                
        except Exception as e:
            return ToolOutput(
                success=False,
                data=None,
                error=f"Error en extracción SQL: {str(e)}"
            )
    
    def _clean_sql(self, sql: str) -> str:
        """Limpia respuesta SQL del LLM (copiado de ReportEngine)"""
        sql = re.sub(r'```sql\s*', '', sql)
        sql = re.sub(r'```\s*$', '', sql)
        sql = sql.strip()
        if not sql.endswith(';'):
            sql += ';'
        return sql