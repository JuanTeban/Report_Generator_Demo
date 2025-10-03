# app/agents/specialized/report_agent.py
from typing import Dict, Any, List
from datetime import datetime
import re

from app.agents.core import BaseAgent, AgentMessage
from app.tools.core import ToolRegistry

class ReportAgent(BaseAgent):
    """
    Agente especializado en generación de reportes.
    Reemplaza a ReportEngine usando arquitectura de tools.
    """
    
    def __init__(self):
        # Cargar todas las tools necesarias
        tools = [
            ToolRegistry.get("sql_data_extraction"),
            ToolRegistry.get("evidence_retrieval"),
            ToolRegistry.get("business_rules"),
            ToolRegistry.get("summary_generation"),
            ToolRegistry.get("recommendations_generation"),
            ToolRegistry.get("chart_generation")
        ]
        
        # Filtrar None (por si alguna tool no está registrada)
        tools = [t for t in tools if t is not None]
        
        super().__init__(
            name="ReportAgent",
            tools=tools,
            max_iterations=15  # Más iteraciones para reportes complejos
        )
    
    async def process_task(self, task: str, context: Dict[str, Any]) -> AgentMessage:
        """
        Genera reporte completo para un consultor.
        
        Context debe contener:
            - consultant_name: str
            - report_type: str (opcional, default="preview")
        """
        consultant_name = context.get("consultant_name")
        report_type = context.get("report_type", "preview")
        
        if not consultant_name:
            return AgentMessage(
                sender=self.name,
                content="Error: consultant_name es requerido",
                metadata={"error": "missing_consultant_name"},
                success=False
            )
        
        # Ejecutar con el loop de razonamiento del BaseAgent
        task_description = (
            f"Genera un reporte completo tipo '{report_type}' para el consultor: {consultant_name}. "
            f"Debes: 1) Extraer datos SQL, 2) Recuperar evidencia RAG, "
            f"3) Obtener reglas de negocio, 4) Generar resumen y recomendaciones, "
            f"5) Crear gráficos. Al final, compila todo en un reporte JSON estructurado."
        )
        
        return await self.run(task_description, context)
    
    async def generate_report(
        self,
        consultant_name: str,
        report_type: str = "preview"
    ) -> Dict[str, Any]:
        """
        Interfaz compatible con ReportEngine.generate_report()
        
        Returns:
            Dict con estructura idéntica al reporte original
        """
        context = {
            "consultant_name": consultant_name,
            "report_type": report_type
        }
        
        # Procesar tarea
        result = await self.process_task(
            task=f"Generar reporte para {consultant_name}",
            context=context
        )
        
        if not result.success:
            # Reporte de error
            return self._error_report(consultant_name, result.content)
        
        # Compilar reporte desde el contexto de tools
        return self._compile_report(consultant_name, report_type, context)
    
    def _compile_report(
        self,
        consultant_name: str,
        report_type: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Compila el reporte final desde el historial de tools.
        """
        tool_history = context.get("tool_history", [])
        
        # Extraer resultados de cada tool
        sql_data = []
        evidence_count = 0
        summary = ""
        recommendations = ""
        charts = {}
        
        for entry in tool_history:
            result = entry.get("result", {})
            if not result.get("success"):
                continue
            
            tool_name = entry.get("tool")
            data = result.get("data")
            
            if tool_name == "sql_data_extraction":
                sql_data = data or []
            
            elif tool_name == "evidence_retrieval":
                if data:
                    for defect_sections in data.values():
                        evidence_count += sum(
                            len(chunks) for chunks in defect_sections.values()
                        )
            
            elif tool_name == "summary_generation":
                summary = data or ""
            
            elif tool_name == "recommendations_generation":
                recommendations = data or ""
            
            elif tool_name == "chart_generation":
                charts = data or {}
        
        # Estructura idéntica a ReportEngine
        return {
            "consultant": consultant_name,
            "generated_at": datetime.now().isoformat(),
            "type": report_type,
            "data": {
                "sql_rows": len(sql_data),
                "evidence_count": evidence_count
            },
            "sections": {
                "summary": summary,
                "recommendations": recommendations
            },
            "charts": charts,
            "metadata": {
                "sql_template": None,
                "version": "2.0-agent",
                "agent": self.name
            }
        }
    
    def _error_report(self, consultant_name: str, error: str) -> Dict[str, Any]:
        """Genera reporte de error"""
        return {
            "consultant": consultant_name,
            "generated_at": datetime.now().isoformat(),
            "type": "error",
            "data": {"sql_rows": 0, "evidence_count": 0},
            "sections": {
                "summary": f"Error generando reporte: {error}",
                "recommendations": "No disponible debido a errores"
            },
            "charts": {},
            "metadata": {"version": "2.0-agent", "error": error}
        }
    
    async def _think(self, task: str, context: Dict) -> Dict[str, Any]:
        """
        Override para mejorar razonamiento específico de reportes.
        """
        tool_history = context.get("tool_history", [])
        
        # Lógica de decisión más inteligente para reportes
        completed_tools = {entry["tool"] for entry in tool_history}
        
        # Plan de ejecución secuencial
        required_sequence = [
            ("sql_data_extraction", "Extraer datos SQL del consultor"),
            ("evidence_retrieval", "Recuperar evidencia multimodal"),
            ("business_rules", "Obtener reglas de negocio"),
            ("summary_generation", "Generar resumen ejecutivo"),
            ("recommendations_generation", "Generar recomendaciones"),
            ("chart_generation", "Crear gráficos")
        ]
        
        # Determinar siguiente paso
        for tool_name, description in required_sequence:
            if tool_name not in completed_tools:
                # Preparar argumentos según la tool
                tool_args = self._prepare_tool_args(
                    tool_name,
                    context,
                    tool_history
                )
                
                return {
                    "reasoning": f"Siguiente paso: {description}",
                    "action": "use_tool",
                    "tool_name": tool_name,
                    "tool_args": tool_args
                }
        
        # Todas las tools ejecutadas, dar respuesta final
        return {
            "reasoning": "Todas las tools ejecutadas exitosamente, compilando reporte",
            "action": "final_answer",
            "answer": "Reporte generado exitosamente. Ver tool_history para detalles."
        }
    
    def _prepare_tool_args(
        self,
        tool_name: str,
        context: Dict,
        tool_history: List[Dict]
    ) -> Dict[str, Any]:
        """Prepara argumentos para cada tool según el contexto"""
        
        consultant_name = context.get("consultant_name")
        
        if tool_name == "sql_data_extraction":
            return {"consultant_name": consultant_name}
        
        elif tool_name == "evidence_retrieval":
            # Necesita defect_ids del SQL
            sql_data = self._get_tool_data(tool_history, "sql_data_extraction")
            defect_ids = self._extract_defect_ids(sql_data)
            return {
                "defect_ids": defect_ids,
                "consultant_name": consultant_name
            }
        
        elif tool_name == "business_rules":
            # Construir query desde SQL data
            sql_data = self._get_tool_data(tool_history, "sql_data_extraction")
            query = self._build_context_query(sql_data)
            return {"query": query, "top_k": 5}
        
        elif tool_name == "summary_generation":
            sql_data = self._get_tool_data(tool_history, "sql_data_extraction")
            evidence = self._get_tool_data(tool_history, "evidence_retrieval")
            rules = self._get_tool_data(tool_history, "business_rules")
            
            rag_context = {
                "evidence_by_defect": evidence or {},
                "business_rules": rules or [],
                "schemas": []
            }
            
            return {
                "consultant_name": consultant_name,
                "sql_data": sql_data or [],
                "rag_context": rag_context
            }
        
        elif tool_name == "recommendations_generation":
            sql_data = self._get_tool_data(tool_history, "sql_data_extraction")
            evidence = self._get_tool_data(tool_history, "evidence_retrieval")
            rules = self._get_tool_data(tool_history, "business_rules")
            
            rag_context = {
                "evidence_by_defect": evidence or {},
                "business_rules": rules or [],
                "schemas": []
            }
            
            return {
                "consultant_name": consultant_name,
                "sql_data": sql_data or [],
                "rag_context": rag_context
            }
        
        elif tool_name == "chart_generation":
            sql_data = self._get_tool_data(tool_history, "sql_data_extraction")
            return {"sql_data": sql_data or []}
        
        return {}
    
    def _get_tool_data(self, tool_history: List[Dict], tool_name: str) -> Any:
        """Extrae data de una tool del historial"""
        for entry in tool_history:
            if entry.get("tool") == tool_name:
                result = entry.get("result", {})
                if result.get("success"):
                    return result.get("data")
        return None
    
    def _extract_defect_ids(self, sql_data: List[Dict]) -> List[str]:
        """Extrae IDs de defectos (copiado de ReportEngine)"""
        if not sql_data:
            return []
        
        ids = set()
        for row in sql_data:
            defect = str(row.get("defectos", ""))
            match = re.search(r'\b(\d{6,})\b', defect)
            if match:
                ids.add(match.group(1))
        
        return list(ids)
    
    def _build_context_query(self, sql_data: List[Dict]) -> str:
        """Construye query para business rules (copiado de ReportEngine)"""
        if not sql_data:
            return ""
        
        terms = set()
        for row in sql_data[:10]:
            if "modulo" in row:
                terms.add(str(row["modulo"]).lower())
            if "categoria_de_defecto" in row:
                terms.add(str(row["categoria_de_defecto"]).lower())
        
        return " ".join(terms)