# app/utils/embedding_manager.py
from typing import List, Optional
from app.core.ia.embeddings import get_embedding_provider

class EmbeddingManager:
    """Manager centralizado para embeddings."""
    
    def __init__(self):
        self.provider = get_embedding_provider()
    
    async def embed_content(
        self, 
        texts: List[str], 
        task_type: str = "RETRIEVAL_DOCUMENT"
    ) -> List[List[float]]:
        """
        Genera embeddings para una lista de textos.
        """
        embeddings = []
        for text in texts:
            emb = await self.provider.get_embedding_async(text)
            embeddings.append(emb)
        return embeddings

# Singleton
_embedder = None

def get_embedder():
    global _embedder
    if _embedder is None:
        _embedder = EmbeddingManager()
    return _embedder