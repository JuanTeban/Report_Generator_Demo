from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import unicodedata
import uuid
from pathlib import Path
from typing import Dict, List, Literal, Optional

import chromadb
from pydantic import BaseModel

from app.config.settings_etl import VECTOR_STORE_DIR
from app.core.ia.embeddings import get_embedding_provider

log = logging.getLogger(__name__)
Modality = Literal["text", "table", "image", "mixed"]


def _strip_accents(s: str) -> str:
    return "".join(
        c for c in unicodedata.normalize("NFKD", s or "") if not unicodedata.combining(c)
    )


def _norm(s: str) -> str:
    s2 = _strip_accents(str(s or ""))
    s2 = re.sub(r"\s+", "_", s2.strip().lower())
    s2 = re.sub(r"[^a-z0-9_\-\.]+", "", s2)
    return s2


def _digits(s: str) -> str:
    m = re.search(r"\d+", str(s or ""))
    return m.group(0) if m else ""


def _content_sha(s: str) -> str:
    return hashlib.sha256((s or "").encode("utf-8")).hexdigest()


class IngestionResult(BaseModel):
    responsable: str
    defecto: str
    processed_files: int
    successful_files: int
    total_chunks: int
    successful_chunks: int
    log_file: Optional[str] = None


def prepare_metadata(meta: dict) -> dict:
    """
    Mantiene metadatos adicionales que vengan desde ingest.py.
    Enriquecemos con normalizaciones y IDs estables.
    """
    responsable = str(meta.get("responsable", "") or "")
    responsable_norm = meta.get("responsable_norm") or _norm(responsable)
    defecto = str(meta.get("defecto", "") or "")
    element_type = str(meta.get("element_type", "") or "")
    chunk_index = int(meta.get("chunk_index", 0) or 0)
    source_file = str(meta.get("source_file", "") or "")

    id_reporte = str(meta.get("id_reporte", "") or "")
    document_id = str(
        meta.get("document_id", "")
        or f"{responsable_norm}::{id_reporte or 'na'}::{Path(source_file).stem}"
    )

    base = {
        "element_type": element_type,
        "responsable": responsable,
        "responsable_norm": responsable_norm,
        "defecto": defecto,
        "source_file": source_file,
        "chunk_index": chunk_index,
        "id_reporte": id_reporte,
        "document_id": document_id,
    }

    extras = {k: v for k, v in meta.items() if k not in base}
    return {**base, **extras}


def prepare_solution_metadata(meta: dict) -> dict:
    """
    Versión para la colección de soluciones históricas.
    Mantiene pass-through y agrega campos típicos de solución.
    """
    responsable = str(meta.get("responsable", "") or "")
    responsable_norm = meta.get("responsable_norm") or _norm(responsable)
    defecto = str(meta.get("defecto", "") or "")
    element_type = str(meta.get("element_type", "") or "")
    chunk_index = int(meta.get("chunk_index", 0) or 0)
    source_file = str(meta.get("source_file", "") or "")

    id_reporte = str(meta.get("id_reporte", "") or "")
    document_id = str(
        meta.get("document_id", "")
        or f"{responsable_norm}::{id_reporte or 'na'}::{Path(source_file).stem}"
    )

    base = {
        "parent_defect_id": _digits(defecto),
        "status": "solved",
        "responsable_norm": responsable_norm,
        "defect_text_norm": _norm(defecto),
        "solution_section": element_type,
        "step_number": chunk_index,
        "source_file": source_file,
        "id_reporte": id_reporte,
        "document_id": document_id,
    }

    extras = {k: v for k, v in meta.items() if k not in base}
    return {**base, **extras}


async def _ensure_collection(client: chromadb.ClientAPI, name: str):
    try:
        return client.get_collection(name=name)
    except Exception:
        return client.create_collection(name=name)


async def vectorize_content(
    content_chunks: List[str],
    metadatas: List[Dict],
    collection_name: str,
) -> int:
    """
    - Calcula embeddings (async) con el provider configurado.
    - Inserta documentos + metadatos en la colección de Chroma persistente.
    - Devuelve cuántos chunks se añadieron con éxito (len(content_chunks) si todo ok).
    """
    if not content_chunks:
        return 0
    if len(content_chunks) != len(metadatas):
        raise ValueError("content_chunks y metadatas deben tener la misma longitud")

    provider = get_embedding_provider()  # Debe exponer get_embedding_async(text)
    client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
    collection = await _ensure_collection(client, collection_name)

    try:
        embeddings: List[List[float]] = []
        for chunk in content_chunks:
            emb = await provider.get_embedding_async(chunk)
            embeddings.append(emb)

        ids_list = [str(uuid.uuid4()) for _ in content_chunks]

        await asyncio.to_thread(
            collection.add,
            embeddings=embeddings,
            documents=content_chunks,
            ids=ids_list,
            metadatas=metadatas,
        )

        return len(content_chunks)
    except Exception:
        log.exception("vectorize_content error")
        return 0
