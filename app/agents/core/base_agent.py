# app/agents/core/base_agent.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging
import json

from app.utils.logger import get_flow_logger
from app.tools.core import BaseTool, ToolOutput
from .agent_message import AgentMessage

from app.config.settings_agents import BASE_AGENT_INSTRUCTIONS, RESPONSE_FORMAT_INSTRUCTIONS

class BaseAgent(ABC):
    """
    Agente base con capacidad de razonamiento y uso de tools.
    
    Implementa:
    - Loop de razonamiento (Thought → Action → Observation)
    - Tool calling con validación
    - Logging detallado
    - Memoria de conversación
    """
    
    def __init__(
        self,
        name: str,
        tools: Optional[List[BaseTool]] = None,
        llm_provider: Optional[Any] = None,
        max_iterations: int = 10
    ):
        self.name = name
        self.tools = {t.name: t for t in (tools or [])}
        self.llm = llm_provider or self._get_default_llm()
        self.max_iterations = max_iterations
        
        # Logger específico
        self.logger = get_flow_logger(
            flow_name=f"agent_{name}",
            sub_dir="logs_agents",
            log_level=logging.DEBUG,
            enable_console=True
        )
        
        # Memoria
        self.memory: List[AgentMessage] = []

        self._current_run_context: Dict[str, Any] = {}
        
        self.logger.log_info(
            f"Agent '{name}' initialized",
            {"tools_count": len(self.tools), "tools": list(self.tools.keys())}
        )
    
    def _get_default_llm(self):
        """Obtiene proveedor LLM configurado"""
        from app.core.ia.llm import get_llm_provider
        return get_llm_provider()
    
    @abstractmethod
    async def process_task(self, task: str, context: Dict[str, Any]) -> AgentMessage:
        """
        Método principal que cada agente debe implementar.
        
        Args:
            task: Descripción de la tarea a realizar
            context: Contexto adicional necesario
        
        Returns:
            AgentMessage con el resultado
        """
        pass
    
    async def run(self, task: str, context: Optional[Dict] = None) -> AgentMessage:
        """
        Ejecuta el agente con loop de razonamiento.
        """
        self.logger.start_flow({
            "agent": self.name,
            "task": task,
            "context": context
        })
        
        context = context or {}
        iteration = 0
        
        # NUEVO: Sincronizar contexto actual
        self._current_run_context = context
        
        try:
            async with self.logger.step(
                "agent_reasoning",
                f"Agent {self.name} reasoning loop"
            ):
                while iteration < self.max_iterations:
                    iteration += 1
                    self.logger.log_info(f"Iteration {iteration}/{self.max_iterations}")
                    
                    # THOUGHT: ¿Qué debo hacer?
                    thought = await self._think(task, context)
                    self.logger.log_data(
                        "thought",
                        thought,
                        f"Agent decision (iteration {iteration})"
                    )
                    
                    # ¿Es la respuesta final?
                    if thought.get("action") == "final_answer":
                        self.logger.log_info("Agent reached final answer")
                        result = AgentMessage(
                            sender=self.name,
                            content=thought.get("answer", ""),
                            metadata={
                                "iterations": iteration,
                                "context": context,
                                "reasoning": thought.get("reasoning", "")
                            },
                            success=True
                        )
                        self.memory.append(result)
                        
                        # NUEVO: Limpiar contexto al finalizar
                        self._current_run_context = {}
                        
                        self.logger.end_flow(success=True)
                        return result
                    
                    # ACTION: Usar tool
                    if thought.get("action") == "use_tool":
                        tool_name = thought.get("tool_name")
                        tool_args = thought.get("tool_args", {})
                        
                        observation = await self._execute_tool(tool_name, tool_args)
                        self.logger.log_data(
                            "observation",
                            observation.model_dump(),
                            f"Tool result: {tool_name}"
                        )
                        
                        # Actualizar contexto
                        context["last_observation"] = observation.model_dump()
                        context["tool_history"] = context.get("tool_history", [])
                        context["tool_history"].append({
                            "tool": tool_name,
                            "args": tool_args,
                            "result": observation.model_dump()
                        })
                        
                        # NUEVO: Mantener sincronizado
                        self._current_run_context = context
                
                # Max iterations
                self.logger.log_warning(f"Max iterations ({self.max_iterations}) reached")
                error_result = AgentMessage(
                    sender=self.name,
                    content="No pude completar la tarea en el límite de iteraciones",
                    metadata={
                        "error": "max_iterations",
                        "iterations": iteration,
                        "context": context
                    },
                    success=False
                )
                
                # NUEVO: Limpiar contexto
                self._current_run_context = {}
                
                self.logger.end_flow(success=False, error="Max iterations")
                return error_result
                
        except Exception as e:
            self.logger.log_error(e, "Error in agent execution")
            error_result = AgentMessage(
                sender=self.name,
                content=f"Error durante ejecución: {str(e)}",
                metadata={"error": str(e), "context": context},
                success=False
            )
            
            # NUEVO: Limpiar contexto
            self._current_run_context = {}
            
            self.logger.end_flow(success=False, error=str(e))
            return error_result
    
    async def _think(self, task: str, context: Dict) -> Dict[str, Any]:
        """
        Razonamiento adaptativo: LLM decide basándose en instrucciones detalladas.
        
        Returns:
            {
                "reasoning": "...",
                "action": "use_tool" | "final_answer",
                "tool_name": "...",
                "tool_args": {...},
                "answer": "..."
            }
        """
        # Construir prompt completo y detallado
        full_prompt = self._build_full_prompt(task, context)
        
        self.logger.log_llm_request(
            full_prompt,
            type(self.llm).__name__,
            {"temperature": 0.3, "task": "reasoning"}
        )
        
        # LLM decide qué hacer
        response = await self.llm.generate_async(full_prompt, temperature=0.3)
        
        self.logger.log_llm_response(
            response.content,
            type(self.llm).__name__,
            response.usage or {}
        )
        
        # Parsear decisión
        try:
            decision = self._parse_llm_decision(response.content)
            return decision
        except Exception as e:
            self.logger.log_warning(f"Error parseando decisión LLM: {e}")
            return self._fallback_decision(response.content, context)

    def _build_full_prompt(self, task: str, context: Dict) -> str:
        """Construye prompt COMPLETO y DETALLADO para el LLM"""
        
        # Instrucciones específicas del agente si las tiene
        agent_instructions = getattr(self, 'agent_instructions', '')
        
        # Catálogo de tools con schemas completos
        tools_catalog = self._get_tools_catalog()
        
        # Historial formateado para el LLM - CRÍTICO: Formateo inteligente
        tool_history = context.get("tool_history", [])
        history_text = self._format_history_for_llm(tool_history)
        
        # Última observación
        last_obs = context.get("last_observation")
        observation_text = self._format_last_observation(last_obs)
        
        # Análisis guiado
        analysis_guide = self._get_analysis_guide(tool_history, task)
        
        # Prompt completo
        return f"""
                {BASE_AGENT_INSTRUCTIONS}

                {agent_instructions}

                ## TOOLS DISPONIBLES:
                {tools_catalog}

                ## TU TAREA ACTUAL:
                {task}

                ## CONTEXTO:
                - Consultor: {context.get('consultant_name', 'N/A')}
                - Tipo: {context.get('report_type', 'N/A')}

                ## HISTORIAL DE TOOLS EJECUTADAS:
                {history_text}

                ## ÚLTIMA OBSERVACIÓN:
                {observation_text}

                {analysis_guide}
                   
                ## FORMATO DE RESPUESTA:  
                {RESPONSE_FORMAT_INSTRUCTIONS}
                """

    def _get_tools_catalog(self) -> str:
        """Genera catálogo detallado de tools para el prompt"""
        if not self.tools:
            return "No hay tools disponibles"
        
        catalog = []
        for tool in self.tools.values():
            schema = tool.to_llm_schema()
            params = schema['parameters'].get('properties', {})
            
            param_desc = []
            for param_name, param_info in params.items():
                param_type = param_info.get('type', 'any')
                param_description = param_info.get('description', 'sin descripción')
                required = param_name in schema['parameters'].get('required', [])
                req_marker = " (requerido)" if required else " (opcional)"
                param_desc.append(f"  - {param_name} ({param_type}){req_marker}: {param_description}")
            
            params_text = "\n".join(param_desc) if param_desc else "  - Sin parámetros"
            
            catalog.append(
                f"**{schema['name']}**\n"
                f"  Descripción: {schema['description']}\n"
                f"  Parámetros:\n{params_text}"
            )
        
        return "\n\n".join(catalog)

    def _format_history_for_llm(self, tool_history: List[Dict]) -> str:
        """
        CRÍTICO: Formatea historial de forma INTELIGENTE para el LLM.
        No truncar datos importantes como listas de resultados.
        """
        if not tool_history:
            return "Sin historial (es la primera iteración)"
        
        formatted = []
        for i, entry in enumerate(tool_history, 1):
            tool_name = entry.get("tool")
            args = entry.get("args", {})
            result = entry.get("result", {})
            success = result.get("success")
            status = "✓ ÉXITO" if success else "✗ FALLÓ"
            
            # Mostrar datos de forma inteligente
            if success:
                data = result.get("data")
                metadata = result.get("metadata", {})
                
                # ESTRATEGIA INTELIGENTE DE FORMATEO
                if tool_name == "sql_data_extraction":
                    # Para SQL, mostrar METADATOS, no datos crudos
                    row_count = metadata.get("row_count", len(data) if isinstance(data, list) else 0)
                    formatted.append(
                        f"{i}. {status} - Tool: {tool_name}\n"
                        f"   Args: {args}\n"
                        f"   RESULTADOS: {row_count} filas extraídas\n"
                        f"   SQL ejecutado: {metadata.get('sql_executed', 'N/A')[:100]}...\n"
                        f"   📊 IMPORTANTE: Hay {row_count} defectos en total"
                    )
                elif tool_name == "evidence_retrieval":
                    total_chunks = metadata.get("total_chunks", 0)
                    formatted.append(
                        f"{i}. {status} - Tool: {tool_name}\n"
                        f"   Args: {args}\n"
                        f"   RESULTADOS: {total_chunks} chunks de evidencia\n"
                        f"   Stats: {metadata.get('stats_by_defect', {})}"
                    )
                elif tool_name == "business_rules":
                    count = metadata.get("count", len(data) if isinstance(data, list) else 0)
                    formatted.append(
                        f"{i}. {status} - Tool: {tool_name}\n"
                        f"   Args: {args}\n"
                        f"   RESULTADOS: {count} reglas recuperadas"
                    )
                elif tool_name in ["summary_generation", "recommendations_generation"]:
                    text_len = len(data) if isinstance(data, str) else 0
                    formatted.append(
                        f"{i}. {status} - Tool: {tool_name}\n"
                        f"   Args: consultor={args.get('consultant_name', 'N/A')}\n"
                        f"   RESULTADOS: Texto generado ({text_len} caracteres)\n"
                        f"   Preview: {data[:150] if isinstance(data, str) else 'N/A'}..."
                    )
                elif tool_name == "chart_generation":
                    chart_count = metadata.get("total_charts", 0)
                    chart_names = metadata.get("chart_names", [])
                    formatted.append(
                        f"{i}. {status} - Tool: {tool_name}\n"
                        f"   RESULTADOS: {chart_count} gráficos generados\n"
                        f"   Nombres: {chart_names}"
                    )
                else:
                    # Para otros tools, mostrar preview corto
                    data_str = str(data)[:200] if data else "Sin datos"
                    formatted.append(
                        f"{i}. {status} - Tool: {tool_name}\n"
                        f"   Args: {args}\n"
                        f"   Data: {data_str}...\n"
                        f"   Metadata: {metadata}"
                    )
            else:
                error = result.get("error", "Error desconocido")
                formatted.append(
                    f"{i}. {status} - Tool: {tool_name}\n"
                    f"   Args: {args}\n"
                    f"   Error: {error}"
                )
        
        return "\n\n".join(formatted)

    def _format_last_observation(self, last_obs: Any) -> str:
        """Formatea última observación para el LLM"""
        if not last_obs:
            return "Sin observaciones previas (primera iteración)"
        
        if isinstance(last_obs, dict):
            success = last_obs.get("success")
            if success:
                metadata = last_obs.get("metadata", {})
                return f"✓ Última tool exitosa\nMetadata: {metadata}"
            else:
                error = last_obs.get("error", "Error desconocido")
                return f"✗ Última tool falló\nError: {error}"
        
        return "Observación disponible pero formato no reconocido"

    def _get_analysis_guide(self, tool_history: List[Dict], task: str) -> str:
        """Genera guía de análisis para ayudar al LLM"""
        completed_tools = {entry["tool"] for entry in tool_history}
        
        return f"""
                ## ANÁLISIS PASO A PASO:

                1. **REVISAR HISTORIAL:**
                - Tools ejecutadas: {', '.join(completed_tools) if completed_tools else 'ninguna'}
                - Total de acciones: {len(tool_history)}

                2. **EVALUAR PROGRESO:**
                - ¿He cumplido el objetivo de la tarea?
                - ¿Qué información tengo disponible?
                - ¿Qué me falta para completar?

                3. **DECIDIR SIGUIENTE ACCIÓN:**
                - Si tengo todo lo necesario → final_answer
                - Si falta información → use_tool (decidir cuál)
                - Si algo falló → evaluar si puedo continuar o debo abortar
                """

    def _parse_llm_decision(self, llm_response: str) -> Dict[str, Any]:
        """Parsea respuesta JSON del LLM"""
        import json
        import re
        
        # Limpiar markdown si existe
        cleaned = re.sub(r'```json\s*', '', llm_response)
        cleaned = re.sub(r'```\s*$', '', cleaned)
        cleaned = cleaned.strip()
        
        # Parsear JSON
        decision = json.loads(cleaned)
        
        # Validar estructura mínima
        if "action" not in decision:
            raise ValueError("Falta campo 'action' en decisión")
        
        if decision["action"] == "use_tool":
            if "tool_name" not in decision:
                raise ValueError("action=use_tool pero falta 'tool_name'")
            if decision["tool_name"] not in self.tools:
                available = ', '.join(self.tools.keys())
                raise ValueError(f"Tool '{decision['tool_name']}' no existe. Disponibles: {available}")
            if "tool_args" not in decision:
                decision["tool_args"] = {}
        
        elif decision["action"] == "final_answer":
            if "answer" not in decision:
                raise ValueError("action=final_answer pero falta 'answer'")
        
        return decision

    def _fallback_decision(self, llm_response: str, context: Dict) -> Dict[str, Any]:
        """Decisión de emergencia si falla el parsing"""
        self.logger.log_warning("Usando fallback decision por error de parsing")
        
        # Si menciona una tool específica, intentar usarla
        for tool_name in self.tools.keys():
            if tool_name in llm_response.lower():
                return {
                    "reasoning": "Fallback: detecté mención de tool",
                    "action": "use_tool",
                    "tool_name": tool_name,
                    "tool_args": {}
                }
        
        # Si no, dar respuesta final con lo que dijo el LLM
        return {
            "reasoning": "Fallback: no pude parsear decisión JSON",
            "action": "final_answer",
            "answer": llm_response[:500]
        }
    
    async def _execute_tool(self, tool_name: str, tool_args: Dict) -> ToolOutput:
        """Ejecuta tool con manejo de errores"""
        tool = self.tools.get(tool_name)
        
        if not tool:
            available = ', '.join(self.tools.keys())
            self.logger.log_warning(
                f"Tool '{tool_name}' no encontrada. Disponibles: {available}"
            )
            return ToolOutput(
                success=False,
                data=None,
                error=f"Tool '{tool_name}' no disponible. Tools disponibles: {available}"
            )
        
        self.logger.log_info(f"Executing tool: {tool_name}", tool_args)
        
        try:
            result = await tool.execute(**tool_args)
            status = "✓ success" if result.success else "✗ failed"
            self.logger.log_info(f"Tool {tool_name} {status}")
            return result
        except Exception as e:
            self.logger.log_error(e, f"Tool {tool_name} execution failed")
            return ToolOutput(
                success=False,
                data=None,
                error=f"Error ejecutando tool: {str(e)}"
            )