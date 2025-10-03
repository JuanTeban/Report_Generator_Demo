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
            "Ejecuta consulta SQL optimizada para extraer TODOS los datos "
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
            # 1. Obtener contexto de esquema
            schema_context = await self.retriever.get_schema_context(
                f"datos del consultor {consultant_name}"
            )
            
            if not schema_context:
                return ToolOutput(
                    success=False,
                    data=None,
                    error="No se encontró contexto de esquema en la base de datos"
                )
            
            # 2. Generar SQL con LLM - PROMPT MEJORADO
            prompt = self._build_sql_prompt(consultant_name, schema_context)
            
            sql_response = await self.llm.generate_async(prompt)
            
            # 3. Limpiar SQL
            sql = self._clean_sql(sql_response.content)
            
            print(f"\n{'='*80}")
            print(f"SQL GENERADO POR LLM:")
            print(sql)
            print(f"{'='*80}\n")
            # 4. VALIDAR que no tenga LIMIT
            sql = self._ensure_no_limit(sql)


            
            # 5. Ejecutar consulta
            result = execute_duckdb_query.invoke({"sql_query": sql})
            data = json.loads(result)
            
            if "json_data" in data and data["json_data"]:
                row_count = len(data["json_data"])
                print(f"✓ SQL extrajo {row_count} filas para {consultant_name}")
                
                return ToolOutput(
                    success=True,
                    data=data["json_data"],
                    metadata={
                        "row_count": row_count,
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
    
    def _build_sql_prompt(self, consultant_name: str, schema_context: str) -> str:
        """Construye prompt específico sin usar PromptManager"""
        return f"""Eres un experto en SQL y DuckDB. Devuelve UNA sola consulta SQL ejecutable.

REGLAS CRÍTICAS:
1) Filtro por responsable: usa UPPER(responsable_del_defecto) LIKE UPPER('%{consultant_name}%')
2) NUNCA uses LIMIT - queremos TODOS los registros del consultor
3) Ordena por antigüedad descendente: ORDER BY CAST(REPLACE(antiguedad_del_defecto_promedio_en_dias, ',', '.') AS FLOAT) DESC
4) Devuelve SOLO el SQL, sin explicaciones

ESQUEMA:
{schema_context}

TAREA: 
Genera SQL que extraiga TODOS los defectos de "{consultant_name}" sin límite de filas.

SQL:"""
    
    def _clean_sql(self, sql: str) -> str:
        """Limpia respuesta SQL del LLM"""
        sql = re.sub(r'```sql\s*', '', sql)
        sql = re.sub(r'```\s*$', '', sql)
        sql = sql.strip()
        if not sql.endswith(';'):
            sql += ';'
        return sql
    
    def _ensure_no_limit(self, sql: str) -> str:
        """Asegura que no haya LIMIT en la query"""
        # Remover cualquier LIMIT que el LLM haya agregado
        sql = re.sub(r'\s+LIMIT\s+\d+', '', sql, flags=re.IGNORECASE)
        return sql
