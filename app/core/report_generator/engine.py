# app/core/report_generator/engine.py
"""
Motor principal de generación de reportes.
"""

import logging
import time
from typing import Dict, Any, List
from datetime import datetime
import pandas as pd

from app.core.ia.llm import get_llm_provider
from app.tools.tools import execute_duckdb_query
from app.utils.logger import get_flow_logger
from .retrieval import RAGRetriever
from .prompts import PromptManager
from .charts import ChartBuilder

logger = logging.getLogger(__name__)

class ReportEngine:
    """Motor principal para generación de reportes."""
    
    def __init__(self):
        self.llm = get_llm_provider()
        self.retriever = RAGRetriever()
        self.prompt_manager = PromptManager()
        self.chart_builder = ChartBuilder()
        
        # Inicializar logger de flujo
        self.flow_logger = get_flow_logger(
            flow_name="report_generator",
            sub_dir="logs_report_generator",
            log_level=logging.DEBUG,
            enable_console=True
        )
    
    async def generate_report(
        self,
        consultant_name: str,
        report_type: str = "preview"
    ) -> Dict[str, Any]:
        """
        Genera un reporte completo para un consultor.
        
        Args:
            consultant_name: Nombre del consultor
            report_type: Tipo de reporte ("preview" o "final")
        
        Returns:
            Dict con las secciones del reporte
        """
        # Iniciar logging del flujo
        self.flow_logger.start_flow({
            "consultant_name": consultant_name,
            "report_type": report_type,
            "llm_provider": type(self.llm).__name__,
            "timestamp": datetime.now().isoformat()
        })
        
        try:
            # 1. Obtener datos SQL
            async with self.flow_logger.step("sql_data_extraction", "Extracción de datos SQL del consultor"):
                sql_data = await self._get_consultant_data(consultant_name)
                
                if not sql_data:
                    self.flow_logger.log_warning(f"No se encontraron datos para: {consultant_name}")
                    return self._empty_report(consultant_name)
                
                self.flow_logger.log_data("sql_data", sql_data, f"Datos SQL extraídos: {len(sql_data)} filas")
            
            # 2. Recuperar contexto RAG
            async with self.flow_logger.step("rag_context_retrieval", "Recuperación de contexto RAG"):
                rag_context = await self._get_rag_context(consultant_name, sql_data)
                self.flow_logger.log_data("rag_context", rag_context, "Contexto RAG recuperado")
            
            # 3. Generar secciones con LLM
            async with self.flow_logger.step("llm_sections_generation", "Generación de secciones con LLM"):
                sections = await self._generate_sections(
                    consultant_name,
                    sql_data,
                    rag_context
                )
                self.flow_logger.log_data("sections", sections, "Secciones generadas por LLM")
            
            # 4. Generar gráficos
            async with self.flow_logger.step("charts_generation", "Generación de gráficos"):
                charts = await self._generate_charts(sql_data)
                self.flow_logger.log_data("charts", charts, f"Gráficos generados: {len(charts)}")
            
            # 5. Compilar reporte final
            async with self.flow_logger.step("report_compilation", "Compilación del reporte final"):
                report = {
                    "consultant": consultant_name,
                    "generated_at": datetime.now().isoformat(),
                    "type": report_type,
                    "data": {
                        "sql_rows": len(sql_data),
                        "evidence_count": sum(
                            len(sections.get("control", [])) + 
                            len(sections.get("evidencia", [])) + 
                            len(sections.get("solucion", []))
                            for sections in rag_context.get("evidence_by_defect", {}).values()
                        )
                    },
                    "sections": sections,
                    "charts": charts,
                    "metadata": {
                        "sql_template": rag_context.get("sql_template"),
                        "version": "2.0"
                    }
                }
                
                self.flow_logger.log_data("final_report", report, "Reporte final compilado")
            
            self.flow_logger.end_flow(success=True)
            return report
            
        except Exception as e:
            self.flow_logger.log_error(e, "Error durante generación de reporte")
            self.flow_logger.end_flow(success=False, error=str(e))
            raise
    
    async def _get_consultant_data(self, consultant_name: str) -> List[Dict[str, Any]]:
        """Obtiene datos del consultor desde DuckDB."""
        
        # 1. Obtener contexto de esquema
        self.flow_logger.log_info("Obteniendo contexto de esquema para generación de SQL")
        schema_context = await self.retriever.get_schema_context(
            f"datos del consultor {consultant_name}"
        )
        self.flow_logger.log_data("schema_context", schema_context, f"Contexto de esquema: {len(schema_context)} documentos")
        
        # 2. Generar prompt SQL
        prompt = self.prompt_manager.get_sql_prompt(
            consultant_name,
            schema_context
        )
        self.flow_logger.log_data("sql_prompt", prompt, "Prompt generado para SQL")
        
        # 3. Generar SQL con LLM
        self.flow_logger.log_llm_request(
            prompt=prompt,
            model=type(self.llm).__name__,
            parameters={"task": "sql_generation"}
        )
        
        start_time = time.time()
        sql_response = await self.llm.generate_async(prompt)
        execution_time = time.time() - start_time
        
        self.flow_logger.log_llm_response(
            response=sql_response.content,
            model=type(self.llm).__name__,
            usage=sql_response.usage or {}
        )
        
        # 4. Limpiar SQL
        sql = self._clean_sql(sql_response.content)
        self.flow_logger.log_data("cleaned_sql", sql, "SQL limpio generado por LLM")
        
        # 5. Ejecutar SQL
        self.flow_logger.log_info("Ejecutando consulta SQL en DuckDB")
        start_time = time.time()
        result = execute_duckdb_query.invoke({"sql_query": sql})
        execution_time = time.time() - start_time
        
        # 6. Parsear resultado
        import json
        data = json.loads(result)
        
        if "json_data" in data:
            row_count = len(data["json_data"])
            self.flow_logger.log_sql_execution(sql, row_count, execution_time)
            return data["json_data"]
        
        self.flow_logger.log_warning("No se encontraron datos en la respuesta SQL")
        return []
    
    async def _get_rag_context(
        self, 
        consultant_name: str,
        sql_data: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Recupera contexto relevante desde las bases vectoriales."""
        
        context = {
            "evidence_by_defect": {},  # Organizado por defecto
            "business_rules": [],
            "schemas": []
        }
        
        # 1. Extraer IDs de defectos de los datos
        defect_ids = self._extract_defect_ids(sql_data)
        self.flow_logger.log_data("defect_ids", defect_ids, f"IDs de defectos extraídos: {len(defect_ids)}")
        
        if not defect_ids:
            self.flow_logger.log_warning("No se encontraron IDs de defectos en los datos SQL")
            return context
        
        # 2. Recuperar evidencia estructurada por defecto
        self.flow_logger.log_info(f"Recuperando evidencia estructurada para {len(defect_ids)} defectos")
        
        evidence_structured = await self.retriever.get_defect_evidence_structured(
            defect_ids=defect_ids,
            responsable=consultant_name,
            chunks_per_defect=20  # Límite por defecto y sección
        )
        
        context["evidence_by_defect"] = evidence_structured
        
        # Calcular totales para logging
        total_chunks = 0
        for defect_id, sections in evidence_structured.items():
            defect_total = sum(len(chunks) for chunks in sections.values())
            total_chunks += defect_total
            self.flow_logger.log_data(
                f"defect_{defect_id}_evidence",
                {
                    "control_chunks": len(sections.get("control", [])),
                    "evidencia_chunks": len(sections.get("evidencia", [])),
                    "solucion_chunks": len(sections.get("solucion", [])),
                    "total": defect_total
                },
                f"Chunks recuperados para defecto {defect_id}"
            )
        
        self.flow_logger.log_info(f"Total de chunks recuperados: {total_chunks}")
        
        # 3. Recuperar reglas de negocio
        query = self._build_context_query(sql_data)
        self.flow_logger.log_rag_query(
            query=query,
            collection="business_rules",
            filters={}
        )
        
        rules = await self.retriever.get_business_rules(query, top_k=5)
        self.flow_logger.log_rag_results(rules, "business_rules")
        context["business_rules"] = rules
        
        return context
    
    async def _generate_sections(
        self,
        consultant_name: str,
        sql_data: List[Dict[str, Any]],
        rag_context: Dict[str, Any]
    ) -> Dict[str, str]:
        """Genera las secciones del reporte con el LLM."""
        
        sections = {}
        
        # 1. Generar resumen ejecutivo
        self.flow_logger.log_info("Generando resumen ejecutivo")
        summary_prompt = self.prompt_manager.get_summary_prompt(
            consultant_name,
            sql_data,
            rag_context
        )
        
        self.flow_logger.log_llm_request(
            prompt=summary_prompt,
            model=type(self.llm).__name__,
            parameters={"section": "summary", "prompt_type": "summary_prompt"}
        )
        
        start_time = time.time()
        summary_response = await self.llm.generate_async(summary_prompt)
        execution_time = time.time() - start_time
        
        self.flow_logger.log_llm_response(
            response=summary_response.content,
            model=type(self.llm).__name__,
            usage=summary_response.usage or {}
        )
        
        sections["summary"] = summary_response.content
        self.flow_logger.log_data("summary_section", {
            "length": len(summary_response.content),
            "execution_time": execution_time
        }, "Resumen ejecutivo generado")
        
        # 2. Generar recomendaciones
        self.flow_logger.log_info("Generando recomendaciones")
        reco_prompt = self.prompt_manager.get_recommendations_prompt(
            consultant_name,
            sql_data,
            rag_context
        )
        
        self.flow_logger.log_llm_request(
            prompt=reco_prompt,
            model=type(self.llm).__name__,
            parameters={"section": "recommendations", "prompt_type": "recommendations_prompt"}
        )
        
        start_time = time.time()
        reco_response = await self.llm.generate_async(reco_prompt)
        execution_time = time.time() - start_time
        
        self.flow_logger.log_llm_response(
            response=reco_response.content,
            model=type(self.llm).__name__,
            usage=reco_response.usage or {}
        )
        
        sections["recommendations"] = reco_response.content
        self.flow_logger.log_data("recommendations_section", {
            "length": len(reco_response.content),
            "execution_time": execution_time
        }, "Recomendaciones generadas")
        
        return sections
    
    async def _generate_charts(self, sql_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Genera gráficos basados en los datos."""
        
        df = pd.DataFrame(sql_data)
        self.flow_logger.log_data("dataframe_info", {
            "rows": len(df),
            "columns": list(df.columns),
            "empty": df.empty
        }, "Información del DataFrame para gráficos")
        
        if df.empty:
            self.flow_logger.log_warning("DataFrame vacío, no se pueden generar gráficos")
            return {}
        
        charts = {}
        
        # Generar gráficos estándar
        chart_configs = [
            ("estado_distribution", "estado_de_defecto", "pie"),
            ("module_distribution", "modulo", "bar"),
            ("blocker_status", "bloqueante_escenarios", "pie"),
            ("age_by_defect", "antiguedad_del_defecto_promedio_en_dias", "bar")
        ]
        
        self.flow_logger.log_info(f"Generando {len(chart_configs)} gráficos")
        
        for chart_name, column, chart_type in chart_configs:
            if column in df.columns:
                try:
                    # Contar valores únicos para el log
                    unique_values = int(df[column].nunique())
                    self.flow_logger.log_chart_generation(chart_name, chart_type, unique_values)
                    
                    chart = self.chart_builder.build_chart(
                        df,
                        column,
                        chart_type
                    )
                    if chart:
                        charts[chart_name] = chart
                        self.flow_logger.log_data("chart_generated", {
                            "chart_name": chart_name,
                            "chart_type": chart_type,
                            "data_points": unique_values
                        }, f"Gráfico {chart_name} generado exitosamente")
                    else:
                        self.flow_logger.log_warning(f"Gráfico {chart_name} no se pudo generar")
                        
                except Exception as e:
                    self.flow_logger.log_error(e, f"Error generando gráfico {chart_name}")
            else:
                self.flow_logger.log_warning(f"Columna {column} no encontrada para gráfico {chart_name}")
        
        self.flow_logger.log_data("charts_summary", {
            "total_charts": len(charts),
            "chart_names": list(charts.keys())
        }, "Resumen de gráficos generados")
        
        return charts
    
    def _extract_defect_ids(self, sql_data: List[Dict[str, Any]]) -> List[str]:
        """Extrae IDs de defectos de los datos SQL."""
        import re
        
        ids = set()
        for row in sql_data:
            defect = str(row.get("defectos", ""))
            match = re.search(r'\b(\d{6,})\b', defect)
            if match:
                ids.add(match.group(1))
        
        return list(ids)
    
    def _build_context_query(self, sql_data: List[Dict[str, Any]]) -> str:
        """Construye query para búsqueda de contexto."""
        
        # Extraer términos clave
        terms = set()
        
        for row in sql_data[:10]:  # Limitar para eficiencia
            if "modulo" in row:
                terms.add(str(row["modulo"]).lower())
            if "categoria_de_defecto" in row:
                terms.add(str(row["categoria_de_defecto"]).lower())
        
        return " ".join(terms)
    
    def _clean_sql(self, sql: str) -> str:
        """Limpia la respuesta SQL del LLM."""
        import re
        
        # Eliminar markdown
        sql = re.sub(r'```sql\s*', '', sql)
        sql = re.sub(r'```\s*$', '', sql)
        
        # Asegurar punto y coma
        sql = sql.strip()
        if not sql.endswith(';'):
            sql += ';'
        
        return sql
    
    def _empty_report(self, consultant_name: str) -> Dict[str, Any]:
        """Genera un reporte vacío."""
        return {
            "consultant": consultant_name,
            "generated_at": datetime.now().isoformat(),
            "type": "empty",
            "data": {"sql_rows": 0, "evidence_count": 0},
            "sections": {
                "summary": "No se encontraron datos para generar el reporte.",
                "recommendations": "No hay recomendaciones disponibles."
            },
            "charts": {},
            "metadata": {"version": "2.0"}
        }