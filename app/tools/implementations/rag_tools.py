# app/tools/implementations/rag_tools.py
from pydantic import Field
from typing import List, Dict, Any

from app.tools.core import BaseTool, ToolInput, ToolOutput, register_tool
from app.core.report_generator.retrieval import RAGRetriever

@register_tool
class EvidenceRetrievalTool(BaseTool):
    """
    Recupera evidencia estructurada de defectos.
    Reutiliza RAGRetriever.get_defect_evidence_structured()
    """
    
    class Input(ToolInput):
        defect_ids: List[str] = Field(
            ...,
            description="Lista de IDs de defectos (ej: ['8000002015', '8000001916'])"
        )
        consultant_name: str = Field(
            ...,
            description="Nombre del consultor responsable"
        )
    
    @property
    def name(self) -> str:
        return "evidence_retrieval"
    
    @property
    def description(self) -> str:
        return (
            "Recupera evidencia multimodal estructurada (control, evidencia, solución) "
            "para una lista de defectos desde ChromaDB"
        )
    
    @property
    def input_schema(self) -> type[ToolInput]:
        return self.Input
    
    def __init__(self):
        self.retriever = RAGRetriever()
    
    async def execute(
        self,
        defect_ids: List[str],
        consultant_name: str
    ) -> ToolOutput:
        """
        Recupera evidencia estructurada por secciones.
        
        Returns:
            ToolOutput con estructura:
            {
                "defect_id": {
                    "control": [...],
                    "evidencia": [...],
                    "solucion": [...]
                }
            }
        """
        try:
            if not defect_ids:
                return ToolOutput(
                    success=False,
                    data=None,
                    error="Lista de defect_ids vacía"
                )
            
            # Recuperar evidencia estructurada
            evidence = await self.retriever.get_defect_evidence_structured(
                defect_ids=defect_ids,
                responsable=consultant_name,
                chunks_per_defect=20
            )
            
            # Calcular estadísticas
            total_chunks = 0
            stats_by_defect = {}
            
            for defect_id, sections in evidence.items():
                defect_total = sum(len(chunks) for chunks in sections.values())
                total_chunks += defect_total
                stats_by_defect[defect_id] = {
                    "control": len(sections.get("control", [])),
                    "evidencia": len(sections.get("evidencia", [])),
                    "solucion": len(sections.get("solucion", [])),
                    "total": defect_total
                }
            
            return ToolOutput(
                success=True,
                data=evidence,
                metadata={
                    "total_chunks": total_chunks,
                    "defects_processed": len(defect_ids),
                    "stats_by_defect": stats_by_defect
                }
            )
            
        except Exception as e:
            return ToolOutput(
                success=False,
                data=None,
                error=f"Error recuperando evidencia: {str(e)}"
            )