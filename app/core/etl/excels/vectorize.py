import asyncio
import chromadb
import logging
from datetime import datetime
from typing import List, Dict
from pathlib import Path
import json
import re

from app.config.settings_etl import (
    VECTOR_STORE_DIR,
    CHROMA_COLLECTION_NAME,
    VECTORIZATION_LOG_FILE,
)
from app.core.ia.embeddings import get_embedding_provider

logger = logging.getLogger(__name__)

def parse_markdown_documentation(file_path: Path) -> List[Dict[str, str]]:
    logger.info("Parseando documentación Markdown...")
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
    except FileNotFoundError:
        logger.error(f"Archivo Markdown no encontrado en: {file_path}")
        return []

    table_sections = re.split(r'(?=### TABLE \d+:)', content)
    
    if len(table_sections) < 2:
        logger.warning("No se encontraron secciones de tabla con el formato '### TABLE ...' en el archivo.")
        return []

    parsed_tables = []
    for section in table_sections[1:]:
        section_content = section.strip()
        first_line = section_content.split('\n', 1)[0]
        match = re.search(r'### TABLE \d+: (.+)', first_line)
        
        if match:
            table_name = match.group(1).strip()
            clean_content = section_content.removesuffix('---').strip()
            parsed_tables.append({
                'table_name': table_name,
                'content': clean_content
            })
            logger.info(f"Tabla parseada: '{table_name}' ({len(clean_content)} caracteres)")
        else:
            logger.warning(f"No se pudo extraer el nombre de la tabla de la sección: {first_line}")

    if not parsed_tables:
        logger.warning("El parseo no encontró tablas válidas a pesar de encontrar secciones.")

    logger.info(f"Parseado completado. {len(parsed_tables)} tablas encontradas.")
    return parsed_tables

def save_log(log_data: Dict):
    try:
        with open(VECTORIZATION_LOG_FILE, 'w', encoding='utf-8') as f:
            json.dump(log_data, f, indent=2, ensure_ascii=False)
        logger.info(f"Log guardado en: {VECTORIZATION_LOG_FILE}")
    except Exception as e:
        logger.error(f"Error al guardar log: {e}")

async def vectorize_markdown_file(markdown_file_path: Path) -> Dict[str, any]:
    result = {
        "success": True,
        "vectorized_count": 0,
        "total_tables": 0,
        "errors": [],
        "start_time": datetime.now().isoformat(),
        "end_time": None
    }
    
    log_data = {
        'timestamp': datetime.now().isoformat(),
        'markdown_file': str(markdown_file_path),
        'chroma_path': str(VECTOR_STORE_DIR),
        'collection_name': Path(str(CHROMA_COLLECTION_NAME)).name,
        'validation': {'success': True},
        'parsing': {'total_tables': 0, 'tables': []},
        'vectorization': {'total_tables': 0, 'successful': 0, 'errors': [], 'details': []}
    }
    
    logger.info("Iniciando proceso de vectorización...")
    
    try:
        if not markdown_file_path.exists() or not markdown_file_path.is_file():
            raise FileNotFoundError("Archivo Markdown no encontrado o formato incorrecto")

        embedding_provider = get_embedding_provider()
        
        table_docs = await asyncio.to_thread(parse_markdown_documentation, markdown_file_path)
        
        result["total_tables"] = len(table_docs)
        log_data['parsing']['total_tables'] = len(table_docs)
        log_data['parsing']['tables'] = [{'table_name': doc['table_name'], 'content_length': len(doc['content'])} for doc in table_docs]
        
        logger.info("Inicializando ChromaDB...")
        chroma_client = chromadb.PersistentClient(path=str(VECTOR_STORE_DIR))
        collection = chroma_client.get_or_create_collection(
            name=Path(str(CHROMA_COLLECTION_NAME)).name,
            metadata={"description": "SQL Knowledge Base for Text-to-SQL queries"}
        )
        
        count = collection.count()
        if count > 0:
            logger.info(f"Colección existente '{CHROMA_COLLECTION_NAME}' encontrada con {count} elementos. Vaciando contenido...")
            ids_to_delete = collection.get(include=[])['ids']
            if ids_to_delete:
                collection.delete(ids=ids_to_delete)
            logger.info("Contenido anterior eliminado exitosamente.")

        logger.info("Iniciando vectorización de tablas...")
        vectorized_count = 0
        errors = []
        log_data['vectorization']['total_tables'] = len(table_docs)
        
        for i, doc in enumerate(table_docs, 1):
            table_name = doc['table_name']
            text_context = doc['content']
            
            try:
                start_time = datetime.now()
                logger.info(f"[{i}/{len(table_docs)}] Vectorizando: {table_name}")
                
                embedding = await embedding_provider.get_embedding_async(text_context)
                
                if not embedding:
                    raise ValueError("El proveedor de embedding devolvió un resultado vacío.")

                embedding_size = len(embedding)
                logger.debug(f"Embedding generado ({embedding_size} dimensiones)")
                
                await asyncio.to_thread(
                    collection.add,
                    embeddings=[embedding],
                    documents=[text_context],
                    ids=[table_name],
                    metadatas=[{
                        'table_name': table_name,
                        'content_length': len(text_context),
                        'embedding_size': embedding_size,
                        'created_at': datetime.now().isoformat()
                    }]
                )
                
                processing_time = (datetime.now() - start_time).total_seconds()
                vectorized_count += 1
                logger.info(f"[{i}/{len(table_docs)}] ✓ {table_name} vectorizado exitosamente ({processing_time:.2f}s)")
                
                log_data['vectorization']['details'].append({
                    'table_name': table_name, 'status': 'success',
                    'processing_time': processing_time, 'embedding_size': embedding_size
                })
                
            except Exception as e:
                error_msg = f"Error vectorizando {table_name}: {e}"
                logger.error(f"[{i}/{len(table_docs)}] ✗ {error_msg}")
                errors.append(error_msg)
                log_data['vectorization']['details'].append({
                    'table_name': table_name, 'status': 'error', 'error_message': str(e)
                })

        result["vectorized_count"] = vectorized_count
        result["errors"] = errors
        if errors:
            result["success"] = False
        
        log_data['vectorization']['successful'] = vectorized_count
        log_data['vectorization']['errors'] = errors
        
        logger.info("="*80)
        logger.info("VECTORIZACIÓN COMPLETADA")
        logger.info("="*80)
        logger.info(f"✓ Tablas vectorizadas exitosamente: {vectorized_count}/{len(table_docs)}")
        logger.info(f"✗ Errores: {len(errors)}")
        
    except Exception as e:
        error_msg = f"Error crítico durante vectorización: {e}"
        logger.error(error_msg)
        result["errors"].append(error_msg)
        result["success"] = False
        log_data['validation']['success'] = False
        log_data['validation']['error'] = error_msg
        
    finally:
        result["end_time"] = datetime.now().isoformat()
        log_data['vectorization']['completion_time'] = result["end_time"]
        save_log(log_data)
    
    return result