import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class PromptManager:
    """
    Gestiona la carga y construcción de prompts para el LLM
    a partir de un archivo JSON externo.
    """
    _templates: Optional[Dict[str, str]] = None

    def __init__(self, prompts_path: Optional[Path] = None):
        if self.__class__._templates is None:
            if prompts_path is None:
                prompts_path = Path(__file__).parent / "prompts.json"
            self._load_prompts_from_file(prompts_path)

    def _load_prompts_from_file(self, prompts_path: Path):
        try:
            with open(prompts_path, "r", encoding="utf-8") as f:
                self.__class__._templates = json.load(f)
            logger.info(f"Prompts cargados exitosamente desde: {prompts_path}")
        except FileNotFoundError:
            logger.error(f"Archivo de prompts no encontrado en: {prompts_path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Error decodificando el archivo JSON de prompts: {e}")
            raise

    def _get_template(self, key: str) -> str:
        """Obtiene una plantilla de prompt de forma segura."""
        if self._templates is None:
            raise RuntimeError("Los prompts no han sido cargados.")
        template = self._templates.get(key)
        if not template:
            logger.error(f"Clave de prompt '{key}' no encontrada en el archivo JSON.")
            raise KeyError(f"Clave de prompt '{key}' no encontrada.")
        return template

    def get_sql_prompt(self, consultant_name: str, schema_context: List[Dict]) -> str:
        """Construye el prompt para la generación de SQL."""
        template = self._get_template("sql_generation_for_report_prompt")
        context_str = "\n".join([doc.get("content", "") for doc in schema_context])
        
        # El prompt original usa :RESPONSABLE, pero .format() choca con {}.
        # Lo reemplazamos de forma segura.
        formatted_prompt = template.replace(":RESPONSABLE", consultant_name)
        
        return formatted_prompt.format(
            question=f"Datos del consultor {consultant_name}",
            context=context_str
        )

    def get_summary_prompt(self, consultant_name: str, sql_data: List[Dict], rag_context: Dict) -> str:
        """Construye el prompt para el resumen ejecutivo."""
        template = self._get_template("report_summary_prompt")
        
        # Prepara los contextos como texto plano
        business_rules = "\n".join([r.get("content", "") for r in rag_context.get("business_rules", [])])
        
        # La evidencia tabular son los mismos datos de sql_data
        table_evidence = json.dumps(sql_data, indent=2, ensure_ascii=False)

        return template.format(
            consultant_name=consultant_name,
            data_json=table_evidence,
            snippets_text=business_rules,
            table_evidence_text=table_evidence
        )

    def get_recommendations_prompt(self, consultant_name: str, sql_data: List[Dict], rag_context: Dict) -> str:
        """Construye el prompt para las recomendaciones."""
        template = self._get_template("report_recommendations_prompt")
        
        # Prepara los contextos como texto plano
        business_rules = "\n".join([r.get("content", "") for r in rag_context.get("business_rules", [])])
        multimodal_evidence = "\n".join([e.get("content", "")[:500] for e in rag_context.get("evidence", [])[:10]]) # Limita la evidencia
        
        # Asumimos que no hay soluciones históricas por ahora, se puede agregar después
        historical_solutions = "No se encontraron soluciones históricas relevantes."

        return template.format(
            consultant_name=consultant_name,
            data_json=json.dumps(sql_data, indent=2, ensure_ascii=False),
            snippets_text=business_rules,
            multimodal_evidence=multimodal_evidence,
            historical_solutions_text=historical_solutions
        )