# app/core/report_generator/retrieval.py
"""
Sistema de recuperación RAG limpio y modular.
Separa la recuperación de la presentación.
"""

import logging
from typing import List, Dict, Any, Optional
from pathlib import Path
import chromadb
from app.config.settings_etl import VECTOR_STORE_DIR, CHROMA_COLLECTIONS
from app.utils.embedding_manager import get_embedder

logger = logging.getLogger(__name__)

class RAGRetriever:
    """Gestiona la recuperación de información desde ChromaDB."""
    
    def __init__(self):
        self.client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        self.embedder = get_embedder()
        self.collections = {}
        self._init_collections()
    
    def _init_collections(self):
        """Inicializa las colecciones disponibles."""
        for key, name in CHROMA_COLLECTIONS.items():
            try:
                self.collections[key] = self.client.get_collection(name=name)
                logger.info(f"Colección '{name}' cargada")
            except Exception as e:
                logger.warning(f"No se pudo cargar colección '{name}': {e}")
    
    async def get_schema_context(self, query: str, top_k: int = 3) -> List[Dict[str, Any]]:
        """
        Recupera contexto de esquemas de base de datos.
        Retorna lista de documentos con metadata.
        """
        collection = self.collections.get("schema_knowledge")
        if not collection:
            return []
        
        try:
            query_embedding = await self.embedder.embed_content(
                [query], 
                task_type="RETRIEVAL_QUERY"
            )
            
            if not query_embedding:
                return []
            
            results = collection.query(
                query_embeddings=query_embedding,
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )
            
            docs = []
            for i in range(len(results["documents"][0])):
                docs.append({
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i]
                })
            
            return docs
            
        except Exception as e:
            logger.error(f"Error en recuperación de esquemas: {e}")
            return []
    
    async def get_defect_chunks_by_section(
        self,
        defect_id: str,
        section_title_norm: str,
        responsable: Optional[str] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """
        Recupera chunks de un defecto específico filtrados por sección.
        
        Args:
            defect_id: ID del defecto (ej: "8000002015")
            section_title_norm: Sección normalizada (ej: "control_de_la_plantilla_y_documento")
            responsable: Nombre del responsable (opcional, filtro adicional)
            limit: Máximo de chunks a recuperar
        
        Returns:
            Lista de chunks con su contenido y metadata
        """
        collection = self.collections.get("multimodal_evidence")
        if not collection:
            logger.warning("Colección multimodal_evidence no disponible")
            return []
        
        # Construir filtro WHERE
        where_clauses = [
            {"defect_id_digits": {"$eq": defect_id}},
            {"section_title_norm": {"$eq": section_title_norm}}
        ]
        
        if responsable:
            responsable_norm = self._normalize_text(responsable)
            where_clauses.append({
                "responsable_norm": {"$eq": responsable_norm}
            })
        
        where = {"$and": where_clauses} if len(where_clauses) > 1 else where_clauses[0]
        
        try:
            results = collection.get(
                where=where,
                limit=limit,
                include=["documents", "metadatas"]
            )
            
            docs = []
            for i in range(len(results["documents"])):
                docs.append({
                    "content": results["documents"][i],
                    "metadata": results["metadatas"][i]
                })
            
            logger.info(f"Recuperados {len(docs)} chunks para defecto {defect_id}, sección {section_title_norm}")
            return docs
            
        except Exception as e:
            logger.error(f"Error recuperando chunks: {e}")
            return []
    
    async def get_defect_evidence_structured(
        self,
        defect_ids: List[str],
        responsable: Optional[str] = None,
        chunks_per_defect: int = 50
    ) -> Dict[str, Dict[str, List[Dict[str, Any]]]]:
        """
        Recupera evidencia estructurada por defecto y por sección.
        
        Args:
            defect_ids: Lista de IDs de defectos
            responsable: Nombre del responsable (filtro opcional)
            chunks_per_defect: Límite de chunks por defecto y sección
        
        Returns:
            Diccionario estructurado:
            {
                "defect_id": {
                    "control": [chunks de control],
                    "evidencia": [chunks de evidencia],
                    "solucion": [chunks de solución]
                }
            }
        """
        structured_evidence = {}
        
        # Secciones relevantes para cada propósito
        sections_map = {
            "control": "control_de_la_plantilla_y_documento",
            "evidencia": "descripcion_y_evidencia_hallazgo",
            "solucion": "respuesta_consultoria"  # Si existe
        }
        
        for defect_id in defect_ids:
            structured_evidence[defect_id] = {}
            
            for key, section_norm in sections_map.items():
                chunks = await self.get_defect_chunks_by_section(
                    defect_id=defect_id,
                    section_title_norm=section_norm,
                    responsable=responsable,
                    limit=chunks_per_defect
                )
                structured_evidence[defect_id][key] = chunks
            
            # Log resumen
            total = sum(len(chunks) for chunks in structured_evidence[defect_id].values())
            logger.info(
                f"Defecto {defect_id}: {len(structured_evidence[defect_id]['control'])} control, "
                f"{len(structured_evidence[defect_id]['evidencia'])} evidencia, "
                f"{len(structured_evidence[defect_id]['solucion'])} solución"
            )
        
        return structured_evidence
    
    async def get_multimodal_evidence(
        self,
        responsable: Optional[str] = None,
        defecto_id: Optional[str] = None,
        modality: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Recupera evidencia multimodal con filtros de metadata.
        DEPRECATED: Usar get_defect_evidence_structured para casos de uso estructurados.
        """
        collection = self.collections.get("multimodal_evidence")
        if not collection:
            return []
        
        where_clauses = []
        
        if responsable:
            responsable_norm = self._normalize_text(responsable)
            where_clauses.append({
                "responsable_norm": {"$eq": responsable_norm}
            })
        
        if defecto_id:
            where_clauses.append({
                "defect_id_digits": {"$eq": defecto_id}
            })
        
        if modality:
            where_clauses.append({
                "element_type": {"$eq": modality}
            })
        
        where = None
        if where_clauses:
            if len(where_clauses) == 1:
                where = where_clauses[0]
            else:
                where = {"$and": where_clauses}
        
        try:
            results = collection.get(
                where=where,
                limit=limit,
                include=["documents", "metadatas"]
            )
            
            docs = []
            for i in range(len(results["documents"])):
                docs.append({
                    "content": results["documents"][i],
                    "metadata": results["metadatas"][i]
                })
            
            return docs
            
        except Exception as e:
            logger.error(f"Error en recuperación multimodal: {e}")
            return []
    
    async def get_business_rules(
        self, 
        query: str, 
        top_k: int = 5
    ) -> List[Dict[str, Any]]:
        """Recupera reglas de negocio relevantes."""
        collection = self.collections.get("business_rules")
        if not collection:
            return []
        
        try:
            query_embedding = await self.embedder.embed_content(
                [query],
                task_type="RETRIEVAL_QUERY"
            )
            
            if not query_embedding:
                return []
            
            results = collection.query(
                query_embeddings=query_embedding,
                n_results=top_k,
                include=["documents", "metadatas", "distances"]
            )
            
            docs = []
            for i in range(len(results["documents"][0])):
                docs.append({
                    "content": results["documents"][0][i],
                    "metadata": results["metadatas"][0][i],
                    "distance": results["distances"][0][i]
                })
            
            docs.sort(key=lambda x: x["distance"])
            
            return docs
            
        except Exception as e:
            logger.error(f"Error en recuperación de business rules: {e}")
            return []
    
    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para busqueda."""
        import unicodedata
        import re

        text = re.sub(r'\s*\(\d+\)\s*$', '', text).strip()
        text = unicodedata.normalize('NFD', text.lower())
        text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
        text = re.sub(r'[^a-z0-9]+', '_', text)
        text = text.strip('_')
        
        return text