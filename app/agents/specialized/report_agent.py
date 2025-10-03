from typing import Dict, Any, List
from datetime import datetime
import re

from app.agents.core import BaseAgent, AgentMessage
from app.tools.core import ToolRegistry
from app.config.settings_agents import REPORT_AGENT_INSTRUCTIONS

class ReportAgent(BaseAgent):
    """
    Agente especializado en generación de reportes.
    Usa razonamiento adaptativo LLM (NO secuencia hardcodeada).
    """
    
    def __init__(self):
        tools = [
            ToolRegistry.get("sql_data_extraction"),
            ToolRegistry.get("evidence_retrieval"),
            ToolRegistry.get("business_rules"),
            ToolRegistry.get("summary_generation"),
            ToolRegistry.get("recommendations_generation"),
            ToolRegistry.get("chart_generation")
        ]
        
        tools = [t for t in tools if t is not None]
        
        super().__init__(
            name="ReportAgent",
            tools=tools,
            max_iterations=15
        )
        
        self.agent_instructions = REPORT_AGENT_INSTRUCTIONS
    
    async def process_task(self, task: str, context: Dict[str, Any]) -> AgentMessage:
        """
        Genera reporte completo para un consultor.
        
        Context debe contener:
            - consultant_name: str
            - report_type: str (opcional)
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
        
        task_description = (
            f"Genera un reporte completo tipo '{report_type}' para el consultor: {consultant_name}. "
            f"Usa las tools disponibles de forma inteligente para obtener "
            f"datos SQL, evidencia, reglas de negocio, generar análisis y gráficos."
        )
        
        return await self.run(task_description, context)
    
    async def generate_report(
        self,
        consultant_name: str,
        report_type: str = "preview"
    ) -> Dict[str, Any]:
        """Interfaz compatible con ReportEngine"""
        context = {
            "consultant_name": consultant_name,
            "report_type": report_type
        }
        
        result = await self.process_task(
            task=f"Generar reporte para {consultant_name}",
            context=context
        )
        
        if not result.success:
            return self._error_report(consultant_name, result.content)
        
        final_context = result.metadata.get("context", context)
        return self._compile_report(consultant_name, report_type, final_context)
    
    
    async def _execute_tool(self, tool_name: str, tool_args: Dict) -> Any:
        """
        Override para enriquecer argumentos automáticamente.
        CRÍTICO: NO usar datos del LLM, usar datos REALES del historial.
        """
        
        tool_args = await self._enrich_tool_args_smart(tool_name, tool_args)
        
        self.logger.log_info(
            f"✓ Args finales para {tool_name}",
            {"args_final": self._safe_preview(tool_args)}
        )
        
        
        return await super()._execute_tool(tool_name, tool_args)
    
    async def _enrich_tool_args_smart(
        self,
        tool_name: str,
        tool_args: Dict
    ) -> Dict:
        """
        ESTRATEGIA INTELIGENTE:
        1. Para tools de análisis (summary, recommendations, charts):
        - IGNORAR lo que pasa el LLM
        - OBTENER datos reales del historial
        2. Para otras tools:
        - Solo completar parámetros faltantes
        """
        context = self._current_run_context
        tool_history = context.get("tool_history", [])
        
        self.logger.log_info(
            f"Enriqueciendo tool: {tool_name}",
            {
                "args_llm": tool_args,
                "tool_history_count": len(tool_history)
            }
        )
        
        if tool_name == "sql_data_extraction":
            if "consultant_name" not in tool_args:
                tool_args["consultant_name"] = context.get("consultant_name")
        
        elif tool_name == "evidence_retrieval":
            sql_result = self._find_tool_result(tool_history, "sql_data_extraction")
            
            if sql_result and sql_result.get("success"):
                sql_data = sql_result.get("data", [])
                if sql_data:
                    extracted_ids = self._extract_defect_ids(sql_data)
                    tool_args["defect_ids"] = extracted_ids
                    
                    self.logger.log_info(
                        f"Defect IDs extraídos del SQL: {len(extracted_ids)}",
                        {"ids": extracted_ids, "sql_rows": len(sql_data)}
                    )
            
            if "consultant_name" not in tool_args:
                tool_args["consultant_name"] = context.get("consultant_name")
        
        elif tool_name == "business_rules":
            if "query" not in tool_args or not tool_args["query"]:
                sql_result = self._find_tool_result(tool_history, "sql_data_extraction")
                if sql_result and sql_result.get("success"):
                    sql_data = sql_result.get("data", [])
                    tool_args["query"] = self._build_context_query(sql_data)
            
            if "top_k" not in tool_args:
                tool_args["top_k"] = 5
        
        elif tool_name in ["summary_generation", "recommendations_generation"]:
            sql_result = self._find_tool_result(tool_history, "sql_data_extraction")
            if sql_result and sql_result.get("success"):
                tool_args["sql_data"] = sql_result.get("data", [])
                self.logger.log_info(
                    f"✓ Usando {len(tool_args['sql_data'])} filas reales para {tool_name}"
                )
            else:
                tool_args["sql_data"] = []
                self.logger.log_warning(f"⚠️ No hay datos SQL disponibles para {tool_name}")
            
            evidence_result = self._find_tool_result(tool_history, "evidence_retrieval")
            rules_result = self._find_tool_result(tool_history, "business_rules")
            
            tool_args["rag_context"] = {
                "evidence_by_defect": evidence_result.get("data", {}) if evidence_result and evidence_result.get("success") else {},
                "business_rules": rules_result.get("data", []) if rules_result and rules_result.get("success") else [],
                "schemas": []
            }
            
            if "consultant_name" not in tool_args:
                tool_args["consultant_name"] = context.get("consultant_name")
        
        elif tool_name == "chart_generation":
            sql_result = self._find_tool_result(tool_history, "sql_data_extraction")
            if sql_result and sql_result.get("success"):
                tool_args["sql_data"] = sql_result.get("data", [])
                self.logger.log_info(
                    f"Usando {len(tool_args['sql_data'])} filas reales para gráficos"
                )
            else:
                tool_args["sql_data"] = []
        
        self.logger.log_info(
            f"✓ Args finales para {tool_name}",
            {"has_sql_data": "sql_data" in tool_args, "sql_rows": len(tool_args.get("sql_data", []))}
        )
        
        return tool_args
    
    def _find_tool_result(self, tool_history: List[Dict], tool_name: str) -> Dict:
        """
        Busca resultado de una tool en el historial COMPLETO.
        Retorna el dict result con {success, data, metadata}.
        """
        for entry in reversed(tool_history):
            if entry.get("tool") == tool_name:
                return entry.get("result", {})
        return {}
    
    def _safe_preview(self, data: Any, max_len: int = 100) -> Any:
        """Preview seguro para logging"""
        if isinstance(data, list) and len(data) > 0:
            return f"[{len(data)} items] First: {str(data[0])[:max_len]}..."
        elif isinstance(data, dict):
            keys = list(data.keys())[:5]
            return f"{{keys: {keys}, ...}}"
        else:
            return str(data)[:max_len]
    
    
    def _compile_report(
        self,
        consultant_name: str,
        report_type: str,
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Compila reporte desde historial"""
        tool_history = context.get("tool_history", [])
        
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
                self.logger.log_info(f"✓ SQL data compilado: {len(sql_data)} filas")
            
            elif tool_name == "evidence_retrieval":
                if data:
                    for sections in data.values():
                        evidence_count += sum(len(chunks) for chunks in sections.values())
                self.logger.log_info(f"✓ Evidencia compilada: {evidence_count} chunks")
            
            elif tool_name == "summary_generation":
                summary = data or ""
                self.logger.log_info(f"✓ Summary compilado: {len(summary)} chars")
            
            elif tool_name == "recommendations_generation":
                recommendations = data or ""
                self.logger.log_info(f"✓ Recommendations compiladas: {len(recommendations)} chars")
            
            elif tool_name == "chart_generation":
                charts = data or {}
                self.logger.log_info(f"✓ Charts compilados: {len(charts)} gráficos")
        
        report = {
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
                "version": "2.0-adaptive-llm",
                "agent": self.name
            }
        }
        
        self.logger.log_info("📋 Reporte compilado", {
            "sql_rows": len(sql_data),
            "evidence_count": evidence_count,
            "charts": len(charts)
        })
        
        return report
    
    def _error_report(self, consultant_name: str, error: str) -> Dict[str, Any]:
        """Reporte de error"""
        return {
            "consultant": consultant_name,
            "generated_at": datetime.now().isoformat(),
            "type": "error",
            "data": {"sql_rows": 0, "evidence_count": 0},
            "sections": {
                "summary": f"Error: {error}",
                "recommendations": "No disponible"
            },
            "charts": {},
            "metadata": {"version": "2.0-adaptive-llm", "error": error}
        }
    
    
    def _extract_defect_ids(self, sql_data: List[Dict]) -> List[str]:
        """Extrae IDs de defectos de TODAS las filas"""
        if not sql_data:
            return []
        
        ids = set()
        
        for i, row in enumerate(sql_data):
            defect_col = row.get("defectos", "")
            defect_str = str(defect_col)
            
            match = re.search(r'\b(\d{6,})\b', defect_str)
            if match:
                ids.add(match.group(1))
        
        return list(ids)
    
    def _build_context_query(self, sql_data: List[Dict]) -> str:
        """Construye query para business rules"""
        if not sql_data:
            return ""
        
        terms = set()
        
        for row in sql_data:
            if "modulo" in row:
                modulo = str(row["modulo"]).lower()
                if modulo and modulo != "nan":
                    terms.add(modulo)
            
            if "categoria_de_defecto" in row:
                categoria = str(row["categoria_de_defecto"]).lower()
                if categoria and categoria != "nan":
                    terms.add(categoria)
        
        return " ".join(terms)