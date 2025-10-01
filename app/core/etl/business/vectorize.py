import asyncio
import logging
import uuid
from pathlib import Path
from typing import Dict
import chromadb

from app.config.settings_etl import (
    VECTOR_STORE_DIR,
    BUSINESS_RULES_DIR,
    BUSINESS_RULES_COLLECTION_NAME,
    BUSINESS_RULES_LOG_FILE,
)
from app.core.ia.embeddings import get_embedding_provider
from .ingest import ingest_business_rules

logger = logging.getLogger(__name__)



async def vectorize_business_rules(
    root_dir: Path | None = None,
    *,
    rule_type: str = "general",
    category: str = "default",
    reset: bool = False,
) -> Dict:
    result = {"success": True, "added": 0, "errors": []}
    root = root_dir or BUSINESS_RULES_DIR
    logger.info(f"Vectorizando Business Rules desde: {root}")

    docs, metadatas = ingest_business_rules(root, rule_type=rule_type, category=category)
    if not docs:
        logger.info("No se encontraron documentos/chunks para procesar.")
        return result

    client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
    collection = client.get_or_create_collection(
        name=BUSINESS_RULES_COLLECTION_NAME,
        metadata={"description": "Base de conocimiento de Reglas de Negocio"},
    )

    if reset:
        logger.info("Limpiando la colección por petición de 'reset=True'...")
        try:
            count = collection.count()
            if count > 0:
                ids = collection.get(limit=count)['ids']
                collection.delete(ids=ids)
                logger.info(f"Se eliminaron {len(ids)} documentos de la colección.")
        except Exception as e:
            logger.warning(f"No se pudo limpiar la colección: {e}")

    embedder = get_embedding_provider()
    logger.info(f"Usando proveedor de embeddings: {type(embedder).__name__}")

    try:
        logger.info(f"Generando embeddings para {len(docs)} chunks...")
        vectors = []
        for i, doc in enumerate(docs):
            vector = await embedder.get_embedding_async(doc)
            vectors.append(vector)
            if (i + 1) % 10 == 0:
                logger.info(f"Procesados {i + 1}/{len(docs)} embeddings...")
        logger.info("Embeddings generados exitosamente.")
    except Exception as e:
        result["success"] = False
        result["errors"].append(f"Fallo al generar embeddings: {e}")
        return result

    ids = [str(uuid.uuid4()) for _ in docs]
    
    for i in range(len(metadatas)):
        metadatas[i]["embedding_size"] = len(vectors[i])

    try:
        logger.info(f"Añadiendo {len(ids)} chunks a la colección '{BUSINESS_RULES_COLLECTION_NAME}'...")
        await asyncio.to_thread(
            collection.add,
            ids=ids,
            documents=docs,
            metadatas=metadatas,
            embeddings=vectors,
        )
        result["added"] = len(ids)
        logger.info("¡Proceso completado exitosamente!")
    except Exception as e:
        result["success"] = False
        result["errors"].append(f"Fallo al insertar en Chroma: {e}")

    return result