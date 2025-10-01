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
            # Generar embedding para la query
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
            
            # Estructurar respuesta
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
    
    async def get_multimodal_evidence(
        self,
        responsable: Optional[str] = None,
        defecto_id: Optional[str] = None,
        modality: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        Recupera evidencia multimodal con filtros de metadata.
        """
        collection = self.collections.get("multimodal_evidence")
        if not collection:
            return []
        
        # Construir filtro WHERE para ChromaDB
        where_clauses = []
        
        if responsable:
            # Normalizar responsable
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
        
        # Combinar cláusulas
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
            
            # Estructurar respuesta
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
            
            # Ordenar por relevancia
            docs.sort(key=lambda x: x["distance"])
            
            return docs
            
        except Exception as e:
            logger.error(f"Error en recuperación de business rules: {e}")
            return []
    
    def _normalize_text(self, text: str) -> str:
        """Normaliza texto para búsqueda."""
        import unicodedata
        import re
        
        # Eliminar acentos
        text = unicodedata.normalize('NFD', text.lower())
        text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
        
        # Reemplazar espacios y caracteres especiales
        text = re.sub(r'[^a-z0-9]+', '_', text)
        text = text.strip('_')
        
        return text