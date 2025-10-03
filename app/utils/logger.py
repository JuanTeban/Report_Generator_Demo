"""
Sistema de logging modular y profesional para el proyecto.
Permite logging detallado de diferentes flujos con estructura organizada.
"""

import logging
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional, List
from contextlib import contextmanager, asynccontextmanager
import traceback
import sys

class FlowLogger:
    """
    Logger especializado para flujos de procesamiento.
    Genera logs estructurados y detallados para debugging profesional.
    """
    
    def __init__(
        self, 
        flow_name: str, 
        log_dir: Path,
        log_level: int = logging.DEBUG,
        enable_console: bool = True
    ):
        self.flow_name = flow_name
        self.log_dir = log_dir
        self.log_level = log_level
        self.enable_console = enable_console
        
        self.log_dir.mkdir(parents=True, exist_ok=True)
        
        self.logger = self._setup_logger()
        
        self.flow_metadata = {
            "flow_name": flow_name,
            "start_time": datetime.now().isoformat(),
            "session_id": self._generate_session_id(),
            "steps": []
        }
        
        self.current_step = None
        self.step_counter = 0
    
    def _generate_session_id(self) -> str:
        """Genera un ID único para la sesión."""
        return f"{self.flow_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    
    def _setup_logger(self) -> logging.Logger:
        """Configura el logger con handlers para archivo y consola."""
        logger = logging.getLogger(f"flow_{self.flow_name}")
        logger.setLevel(self.log_level)
        
        if logger.handlers:
            return logger
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)s | %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        
        log_file = self.log_dir / f"{self.flow_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(self.log_level)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        if self.enable_console:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(logging.INFO)
            console_formatter = logging.Formatter(
                '%(asctime)s | %(levelname)-8s | %(message)s',
                datefmt='%H:%M:%S'
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)
        
        return logger
    
    def start_flow(self, metadata: Optional[Dict[str, Any]] = None):
        """Inicia el logging del flujo."""
        self.flow_metadata["start_time"] = datetime.now().isoformat()
        if metadata:
            self.flow_metadata.update(metadata)
        
        self.logger.info("=" * 80)
        self.logger.info(f"INICIANDO FLUJO: {self.flow_name}")
        self.logger.info("=" * 80)
        self.logger.info(f"Session ID: {self.flow_metadata['session_id']}")
        self.logger.info(f"Metadata inicial: {json.dumps(metadata or {}, indent=2, ensure_ascii=False)}")
    
    def end_flow(self, success: bool = True, error: Optional[str] = None):
        """Finaliza el logging del flujo."""
        self.flow_metadata["end_time"] = datetime.now().isoformat()
        self.flow_metadata["success"] = success
        self.flow_metadata["total_steps"] = len(self.flow_metadata["steps"])
        
        if error:
            self.flow_metadata["error"] = error
        
        start = datetime.fromisoformat(self.flow_metadata["start_time"])
        end = datetime.fromisoformat(self.flow_metadata["end_time"])
        duration = (end - start).total_seconds()
        self.flow_metadata["duration_seconds"] = duration
        
        self.logger.info("=" * 80)
        self.logger.info(f"FINALIZANDO FLUJO: {self.flow_name}")
        self.logger.info(f"Estado: {'ÉXITO' if success else 'ERROR'}")
        self.logger.info(f"Duración: {duration:.2f} segundos")
        self.logger.info(f"Total de pasos: {len(self.flow_metadata['steps'])}")
        if error:
            self.logger.error(f"Error: {error}")
        self.logger.info("=" * 80)
        
        metadata_file = self.log_dir / f"{self.flow_metadata['session_id']}_metadata.json"
        with open(metadata_file, 'w', encoding='utf-8') as f:
            json.dump(self.flow_metadata, f, indent=2, ensure_ascii=False)
    
    @asynccontextmanager
    async def step(self, step_name: str, description: str = ""):
        """Context manager para logging de pasos individuales."""
        self.step_counter += 1
        step_id = f"step_{self.step_counter:03d}"
        
        step_metadata = {
            "step_id": step_id,
            "step_name": step_name,
            "description": description,
            "start_time": datetime.now().isoformat(),
            "logs": []
        }
        
        self.current_step = step_metadata
        
        self.logger.info("-" * 60)
        self.logger.info(f"PASO {self.step_counter}: {step_name}")
        if description:
            self.logger.info(f"Descripción: {description}")
        self.logger.info("-" * 60)
        
        try:
            yield self
        except Exception as e:
            step_metadata["error"] = str(e)
            step_metadata["traceback"] = traceback.format_exc()
            self.logger.error(f"Error en paso {step_name}: {e}")
            self.logger.debug(f"Traceback: {traceback.format_exc()}")
            raise
        finally:
            step_metadata["end_time"] = datetime.now().isoformat()
            
            start = datetime.fromisoformat(step_metadata["start_time"])
            end = datetime.fromisoformat(step_metadata["end_time"])
            step_metadata["duration_seconds"] = (end - start).total_seconds()
            
            self.flow_metadata["steps"].append(step_metadata)
            self.current_step = None
    
    def log_data(self, data_type: str, data: Any, description: str = ""):
        """Log de datos estructurados."""
        if self.current_step:
            self.current_step["logs"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "data",
                "data_type": data_type,
                "description": description,
                "data": self._serialize_data(data)
            })
        
        self.logger.debug(f"[DATA] {data_type}: {description}")
        if isinstance(data, (dict, list)) and len(str(data)) < 1000:
            self.logger.debug(f"[DATA] Contenido: {json.dumps(data, indent=2, ensure_ascii=False)}")
    
    def log_llm_request(self, prompt: str, model: str, parameters: Dict[str, Any] = None):
        """Log específico para requests al LLM."""
        if self.current_step:
            self.current_step["logs"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "llm_request",
                "model": model,
                "parameters": parameters or {},
                "prompt_length": len(prompt),
                "prompt_preview": prompt[:500] + "..." if len(prompt) > 500 else prompt
            })
        
        self.logger.info(f"[LLM REQUEST] Modelo: {model}")
        if parameters:
            self.logger.info(f"[LLM REQUEST] Parámetros: {json.dumps(parameters, indent=2)}")
        self.logger.info(f"[LLM REQUEST] Prompt ({len(prompt)} chars): {prompt[:200]}...")
    
    def log_llm_response(self, response: str, model: str, usage: Dict[str, Any] = None):
        """Log específico para responses del LLM."""
        if self.current_step:
            self.current_step["logs"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "llm_response",
                "model": model,
                "response_length": len(response),
                "response_preview": response[:500] + "..." if len(response) > 500 else response,
                "usage": usage or {}
            })
        
        self.logger.info(f"[LLM RESPONSE] Modelo: {model}")
        if usage:
            self.logger.info(f"[LLM RESPONSE] Usage: {json.dumps(usage, indent=2)}")
        self.logger.info(f"[LLM RESPONSE] Respuesta ({len(response)} chars): {response[:200]}...")
    
    def log_rag_query(self, query: str, collection: str, filters: Dict[str, Any] = None):
        """Log específico para queries RAG."""
        if self.current_step:
            self.current_step["logs"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "rag_query",
                "collection": collection,
                "query": query,
                "filters": filters or {}
            })
        
        self.logger.info(f"[RAG QUERY] Colección: {collection}")
        self.logger.info(f"[RAG QUERY] Query: {query}")
        if filters:
            self.logger.info(f"[RAG QUERY] Filtros: {json.dumps(filters, indent=2)}")
    
    def log_rag_results(self, results: List[Dict[str, Any]], collection: str):
        """Log específico para resultados RAG."""
        if self.current_step:
            self.current_step["logs"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "rag_results",
                "collection": collection,
                "result_count": len(results),
                "results_preview": [{"content_preview": r.get("content", "")[:200]} for r in results[:3]]
            })
        
        self.logger.info(f"[RAG RESULTS] Colección: {collection}")
        self.logger.info(f"[RAG RESULTS] Documentos encontrados: {len(results)}")
        for i, result in enumerate(results[:3]):  # Solo primeros 3
            content_preview = result.get("content", "")[:100]
            self.logger.info(f"[RAG RESULTS] Doc {i+1}: {content_preview}...")
    
    def log_sql_execution(self, sql: str, result_count: int, execution_time: float = None):
        """Log específico para ejecución de SQL."""
        if self.current_step:
            self.current_step["logs"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "sql_execution",
                "sql": sql,
                "result_count": result_count,
                "execution_time": execution_time
            })
        
        self.logger.info(f"[SQL] Query: {sql[:200]}...")
        self.logger.info(f"[SQL] Resultados: {result_count} filas")
        if execution_time:
            self.logger.info(f"[SQL] Tiempo: {execution_time:.3f}s")
    
    def log_chart_generation(self, chart_name: str, chart_type: str, data_points: int):
        """Log específico para generación de gráficos."""
        if self.current_step:
            self.current_step["logs"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "chart_generation",
                "chart_name": chart_name,
                "chart_type": chart_type,
                "data_points": data_points
            })
        
        self.logger.info(f"[CHART] {chart_name} ({chart_type}): {data_points} puntos de datos")
    
    def log_error(self, error: Exception, context: str = ""):
        """Log específico para errores."""
        error_info = {
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context,
            "traceback": traceback.format_exc()
        }
        
        if self.current_step:
            self.current_step["logs"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "error",
                **error_info
            })
        
        self.logger.error(f"[ERROR] {context}: {error}")
        self.logger.debug(f"[ERROR] Traceback: {traceback.format_exc()}")
    
    def log_info(self, message: str, data: Any = None):
        """Log de información general."""
        if self.current_step:
            self.current_step["logs"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "info",
                "message": message,
                "data": self._serialize_data(data) if data else None
            })
        
        self.logger.info(f"[INFO] {message}")
        if data:
            self.logger.debug(f"[INFO] Data: {json.dumps(self._serialize_data(data), indent=2, ensure_ascii=False)}")
    
    def log_warning(self, message: str, data: Any = None):
        """Log de advertencias."""
        if self.current_step:
            self.current_step["logs"].append({
                "timestamp": datetime.now().isoformat(),
                "type": "warning",
                "message": message,
                "data": self._serialize_data(data) if data else None
            })
        
        self.logger.warning(f"[WARNING] {message}")
        if data:
            self.logger.debug(f"[WARNING] Data: {json.dumps(self._serialize_data(data), indent=2, ensure_ascii=False)}")
    
    def _serialize_data(self, data: Any) -> Any:
        """Serializa datos para logging."""
        try:
            if isinstance(data, (dict, list, str, int, float, bool, type(None))):
                return data
            else:
                return str(data)
        except Exception:
            return f"<Non-serializable: {type(data).__name__}>"


class LoggerManager:
    """Manager centralizado para diferentes tipos de loggers."""
    
    def __init__(self, base_log_dir: Path):
        self.base_log_dir = base_log_dir
        self.loggers = {}
    
    def get_flow_logger(
        self, 
        flow_name: str, 
        sub_dir: str = "",
        log_level: int = logging.DEBUG,
        enable_console: bool = True
    ) -> FlowLogger:
        """Obtiene o crea un logger para un flujo específico."""
        logger_key = f"{flow_name}_{sub_dir}"
        
        if logger_key not in self.loggers:
            log_dir = self.base_log_dir / sub_dir if sub_dir else self.base_log_dir
            self.loggers[logger_key] = FlowLogger(
                flow_name=flow_name,
                log_dir=log_dir,
                log_level=log_level,
                enable_console=enable_console
            )
        
        return self.loggers[logger_key]
    
    def cleanup_old_logs(self, days_to_keep: int = 30):
        """Limpia logs antiguos."""
        cutoff_date = datetime.now().timestamp() - (days_to_keep * 24 * 60 * 60)
        
        for log_file in self.base_log_dir.rglob("*.log"):
            if log_file.stat().st_mtime < cutoff_date:
                try:
                    log_file.unlink()
                except Exception as e:
                    print(f"Error eliminando {log_file}: {e}")


_logger_manager = None

def get_logger_manager(base_log_dir: Path = None) -> LoggerManager:
    """Obtiene la instancia global del LoggerManager."""
    global _logger_manager
    
    if _logger_manager is None:
        if base_log_dir is None:
            base_log_dir = Path("data_store/logs")
        _logger_manager = LoggerManager(base_log_dir)
    
    return _logger_manager

def get_flow_logger(
    flow_name: str, 
    sub_dir: str = "",
    log_level: int = logging.DEBUG,
    enable_console: bool = True
) -> FlowLogger:
    """Función de conveniencia para obtener un flow logger."""
    manager = get_logger_manager()
    return manager.get_flow_logger(flow_name, sub_dir, log_level, enable_console)
