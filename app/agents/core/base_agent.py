# app/agents/core/base_agent.py
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import logging
import json

from app.utils.logger import get_flow_logger
from app.tools.core import BaseTool, ToolOutput
from .agent_message import AgentMessage

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
        
        Flujo:
        1. THOUGHT: LLM decide qué hacer
        2. ACTION: Ejecuta tool si es necesario  
        3. OBSERVATION: Analiza resultado
        4. Repite hasta resolver o max_iterations
        """
        self.logger.start_flow({
            "agent": self.name,
            "task": task,
            "context": context
        })
        
        context = context or {}
        iteration = 0
        
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
            self.logger.end_flow(success=False, error=str(e))
            return error_result
    
    async def _think(self, task: str, context: Dict) -> Dict[str, Any]:
        """
        Razonamiento: LLM decide el próximo paso.
        
        Returns:
            {
                "reasoning": "...",
                "action": "use_tool" | "final_answer",
                "tool_name": "...",
                "tool_args": {...},
                "answer": "..."
            }
        """
        tools_desc = self._get_tools_description()
        history = self._format_history(context.get("tool_history", []))
        last_obs = context.get("last_observation")
        
        observation_text = "Sin observaciones previas"
        if last_obs:
            if last_obs.success:
                observation_text = f"Última tool ejecutada exitosamente. Datos: {last_obs.data}"
            else:
                observation_text = f"Última tool falló: {last_obs.get('error')}"
        
        prompt = f"""Eres un agente asistente experto. Tu tarea es: {task}

Tienes acceso a las siguientes tools:
{tools_desc}

Historial de acciones ejecutadas:
{history}

Última observación:
{observation_text}

Razona paso a paso:
1. ¿Qué información necesito para completar la tarea?
2. ¿Ya tengo esa información en las observaciones?
3. ¿Debo usar alguna tool o puedo dar la respuesta final?

IMPORTANTE: Responde ÚNICAMENTE en formato JSON válido:
{{
    "reasoning": "tu razonamiento detallado aquí",
    "action": "use_tool" o "final_answer",
    "tool_name": "nombre_exacto_de_la_tool" (solo si action=use_tool),
    "tool_args": {{"param": "value"}} (solo si action=use_tool),
    "answer": "tu respuesta final completa" (solo si action=final_answer)
}}
"""
        
        self.logger.log_llm_request(
            prompt,
            type(self.llm).__name__,
            {"temperature": 0.2, "task": "reasoning"}
        )
        
        response = await self.llm.generate_async(prompt, temperature=0.2)
        
        self.logger.log_llm_response(
            response.content,
            type(self.llm).__name__,
            response.usage or {}
        )
        
        # Parsear JSON
        try:
            decision = json.loads(response.content)
            return decision
        except json.JSONDecodeError as e:
            self.logger.log_warning(f"JSON parse failed: {e}, usando fallback")
            # Fallback: asumir respuesta final
            return {
                "reasoning": "Error parseando JSON, asumiendo respuesta",
                "action": "final_answer",
                "answer": response.content
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
    
    def _get_tools_description(self) -> str:
        """Genera descripción de tools para el prompt"""
        if not self.tools:
            return "No hay tools disponibles"
        
        descriptions = []
        for tool in self.tools.values():
            schema = tool.to_llm_schema()
            params_desc = schema['parameters'].get('properties', {})
            params_list = ', '.join(f"{k}: {v.get('description', 'sin descripción')}" 
                                   for k, v in params_desc.items())
            
            descriptions.append(
                f"• {schema['name']}: {schema['description']}\n"
                f"  Parámetros: {params_list if params_list else 'ninguno'}"
            )
        return "\n".join(descriptions)
    
    def _format_history(self, history: List[Dict]) -> str:
        """Formatea historial para el prompt"""
        if not history:
            return "Sin historial de acciones"
        
        formatted = []
        for i, entry in enumerate(history[-5:], 1):  # Solo últimas 5
            result = entry.get('result', {})
            status = "✓" if result.get('success') else "✗"
            data_preview = str(result.get('data', ''))[:100]
            
            formatted.append(
                f"{i}. {status} Tool: {entry['tool']}\n"
                f"   Argumentos: {entry['args']}\n"
                f"   Resultado: {data_preview}..."
            )
        return "\n".join(formatted)