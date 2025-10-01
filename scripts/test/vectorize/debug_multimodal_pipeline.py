#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script de debug para pipeline multimodal completo:
- Extrae metadata del path y del documento
- Genera chunks con visión
- Muestra metadatos enriquecidos COMPLETOS
- Vectoriza en ChromaDB
- Genera archivo de debug con todo
"""

import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

# Agregar el directorio raíz del proyecto al path de Python
project_root = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(project_root))

from app.core.etl.multimodal.ingest import (
    partition_file,
    process_document_by_section_async,
    _extract_metadata_from_path,
    _extract_business_metadata,
)
from app.core.etl.multimodal.vectorize import (
    vectorize_content,
    prepare_metadata,
)
from app.config.settings_etl import CHROMA_COLLECTIONS, DATA_LOG_PATH

# --- CONFIGURACIÓN ---
# Cambia esta ruta al archivo que quieras probar
DOCUMENTO_A_PROBAR = Path(
    "C:/Users/JuanEstebanGarciaGal/Documents/IBM/Report-generator/data_store/etl_store/"
    "uploads_multimodal/by_ticket/YARLEN_ASTRID_ALVAREZ_BUILES_(203)/"
    "8000002015-D1_RE__CONTRATOS__ERROR_IND_DE_RETENCIÓN/2025-09-24/"
    "EvidenciaHallazgoM�dulo_RE_N�_3_Carga_213.docx"
)

# Directorio donde se guardarán los archivos de debug
DEBUG_DIR = DATA_LOG_PATH / "debug_multimodal"
DEBUG_DIR.mkdir(parents=True, exist_ok=True)


def _clean_meta_value(value):
    """Limpia valores de metadata para ChromaDB"""
    if value is None:
        return ""
    if isinstance(value, list):
        return str(value)
    if isinstance(value, (int, float, str, bool)):
        return value
    return str(value)


def save_debug_output(
    doc_path: Path,
    elements_count: int,
    images_count: int,
    path_meta: dict,
    business_meta: dict,
    chunks: list,
    metadatas_partial: list,
    metadatas_final: list,
    vectorized_count: int,
):
    """Guarda archivo de debug completo con toda la información del pipeline"""
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"debug_full_{doc_path.stem}_{timestamp}.txt"
    output_path = DEBUG_DIR / filename
    
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("=" * 100 + "\n")
        f.write("PIPELINE MULTIMODAL - DEBUG COMPLETO\n")
        f.write("=" * 100 + "\n\n")
        
        f.write(f"📄 Archivo procesado: {doc_path}\n")
        f.write(f"🕐 Fecha de procesamiento: {datetime.now().isoformat()}\n")
        f.write(f"📊 Elementos extraídos: {elements_count}\n")
        f.write(f"🖼️  Imágenes detectadas: {images_count}\n")
        f.write(f"📦 Chunks generados: {len(chunks)}\n")
        f.write(f"✅ Chunks vectorizados: {vectorized_count}/{len(chunks)}\n")
        f.write("\n" + "=" * 100 + "\n\n")
        
        # METADATA EXTRAÍDA DEL PATH
        f.write("=" * 100 + "\n")
        f.write("METADATA EXTRAÍDA DEL PATH\n")
        f.write("=" * 100 + "\n")
        f.write(json.dumps(path_meta, indent=2, ensure_ascii=False))
        f.write("\n\n")
        
        # METADATA EXTRAÍDA DEL DOCUMENTO
        f.write("=" * 100 + "\n")
        f.write("METADATA EXTRAÍDA DEL DOCUMENTO (Tablas)\n")
        f.write("=" * 100 + "\n")
        f.write(json.dumps(business_meta, indent=2, ensure_ascii=False))
        f.write("\n\n")
        
        # CHUNKS CON METADATOS COMPLETOS
        for idx, (chunk, meta_partial, meta_final) in enumerate(
            zip(chunks, metadatas_partial, metadatas_final), start=1
        ):
            f.write("=" * 100 + "\n")
            f.write(f"CHUNK #{idx}\n")
            f.write("=" * 100 + "\n\n")
            
            f.write("-" * 100 + "\n")
            f.write("METADATA PARCIAL (desde process_document_by_section_async):\n")
            f.write("-" * 100 + "\n")
            f.write(json.dumps(meta_partial, indent=2, ensure_ascii=False))
            f.write("\n\n")
            
            f.write("-" * 100 + "\n")
            f.write("METADATA FINAL ENRIQUECIDA (la que va a ChromaDB):\n")
            f.write("-" * 100 + "\n")
            f.write(json.dumps(meta_final, indent=2, ensure_ascii=False))
            f.write("\n\n")
            
            f.write("-" * 100 + "\n")
            f.write("CONTENIDO DEL CHUNK:\n")
            f.write("-" * 100 + "\n")
            f.write(chunk)
            f.write("\n\n")
    
    print(f"\n✅ Archivo de debug guardado en: {output_path}")
    return output_path


async def test_full_pipeline(doc_path: Path):
    """Ejecuta el pipeline completo con debug detallado"""
    
    if not doc_path.exists():
        print(f"❌ Error: El archivo no existe en la ruta: {doc_path}")
        return
    
    print("\n" + "=" * 100)
    print("🚀 INICIANDO PIPELINE MULTIMODAL COMPLETO")
    print("=" * 100)
    print(f"📄 Documento: {doc_path.name}\n")
    
    try:
        # PASO 1: EXTRACCIÓN DE METADATA DEL PATH
        print("=" * 100)
        print("PASO 1: EXTRACCIÓN DE METADATA DEL PATH")
        print("=" * 100)
        path_meta = _extract_metadata_from_path(doc_path)
        print(json.dumps(path_meta, indent=2, ensure_ascii=False))
        print()
        
        # PASO 2: PARTICIONADO DEL DOCUMENTO
        print("=" * 100)
        print("PASO 2: PARTICIONADO DEL DOCUMENTO")
        print("=" * 100)
        elements = partition_file(doc_path)
        images_count = sum(1 for e in elements if "Image" in type(e).__name__)
        print(f"📊 Elementos extraídos: {len(elements)}")
        print(f"🖼️  Imágenes detectadas: {images_count}")
        print()
        
        if not elements:
            print("❌ No se extrajo ningún elemento. Abortando.")
            return
        
        # PASO 3: EXTRACCIÓN DE METADATA DEL DOCUMENTO
        print("=" * 100)
        print("PASO 3: EXTRACCIÓN DE METADATA DEL DOCUMENTO")
        print("=" * 100)
        business_meta = _extract_business_metadata(elements)
        print(json.dumps(business_meta, indent=2, ensure_ascii=False))
        print()
        
        # PASO 4: PROCESAMIENTO DE SECCIONES Y VISIÓN
        print("=" * 100)
        print("PASO 4: PROCESAMIENTO DE SECCIONES Y GENERACIÓN DE CHUNKS")
        print("=" * 100)
        print("⚙️  Procesando secciones y ejecutando modelo de visión (si hay imágenes)...\n")
        
        chunks, metadatas_partial = await process_document_by_section_async(elements)
        
        print(f"\n✅ Chunks generados: {len(chunks)}")
        print()
        
        if not chunks:
            print("❌ No se generaron chunks. Abortando.")
            return
        
        # PASO 5: ENRIQUECIMIENTO DE METADATOS
        print("=" * 100)
        print("PASO 5: ENRIQUECIMIENTO DE METADATOS")
        print("=" * 100)
        
        # Calcular IDs y normalizaciones
        from app.core.etl.multimodal.vectorize import _norm
        
        id_reporte = path_meta.get("defecto_id_digits", "")
        responsable_clean = path_meta.get("responsable_clean", "")
        responsable_norm = _norm(responsable_clean) if responsable_clean else ""
        document_id = f"{responsable_norm}::{id_reporte or 'na'}::{doc_path.stem}"
        
        metadatas_final = []
        for i, meta_partial in enumerate(metadatas_partial):
            # Construir metadata enriquecida (igual que en _process_dir)
            raw = {
                # Campos básicos
                "element_type": meta_partial.get("chunk_type", ""),
                "source_file": doc_path.name,
                "chunk_index": i,
                
                # Responsable
                "responsable": responsable_clean,
                "responsable_norm": responsable_norm,
                "responsable_original": path_meta.get("responsable_original", ""),
                
                # Defecto/Caso
                "defecto": path_meta.get("defecto_original", ""),
                "defecto_original": path_meta.get("defecto_original", ""),
                "defect_id_digits": id_reporte,
                
                # Metadata de negocio
                "modulo": business_meta.get("modulo", ""),
                "proyecto": business_meta.get("proyecto", ""),
                
                # IDs
                "id_reporte": id_reporte,
                "document_id": document_id,
                "tipo_organizacion": path_meta.get("tipo_organizacion", ""),
                
                # Metadata del chunk (desde process_document_by_section_async)
                **{k: v for k, v in meta_partial.items() if k not in {"element_type"}},
            }
            
            # Limpiar valores para ChromaDB
            clean_raw = {k: _clean_meta_value(v) for k, v in raw.items()}
            
            # Aplicar prepare_metadata
            final_meta = prepare_metadata(clean_raw)
            metadatas_final.append(final_meta)
        
        print(f"✅ Metadatos enriquecidos para {len(metadatas_final)} chunks")
        print("\nEjemplo de metadata final (primer chunk):")
        print(json.dumps(metadatas_final[0], indent=2, ensure_ascii=False))
        print()
        
        # PASO 6: VECTORIZACIÓN EN CHROMADB
        print("=" * 100)
        print("PASO 6: VECTORIZACIÓN EN CHROMADB")
        print("=" * 100)
        collection_name = CHROMA_COLLECTIONS["multimodal_evidence"]
        print(f"📦 Colección destino: {collection_name}")
        print(f"⚙️  Vectorizando {len(chunks)} chunks...\n")
        
        vectorized_count = await vectorize_content(
            chunks, metadatas_final, collection_name
        )
        
        print(f"✅ Vectorización completada: {vectorized_count}/{len(chunks)} chunks")
        print()
        
        # PASO 7: GUARDAR ARCHIVO DE DEBUG
        print("=" * 100)
        print("PASO 7: GENERANDO ARCHIVO DE DEBUG")
        print("=" * 100)
        
        debug_path = save_debug_output(
            doc_path=doc_path,
            elements_count=len(elements),
            images_count=images_count,
            path_meta=path_meta,
            business_meta=business_meta,
            chunks=chunks,
            metadatas_partial=metadatas_partial,
            metadatas_final=metadatas_final,
            vectorized_count=vectorized_count,
        )
        
        print("\n" + "=" * 100)
        print("🎉 PIPELINE COMPLETADO EXITOSAMENTE")
        print("=" * 100)
        print(f"\n📄 Archivo de debug: {debug_path}")
        print(f"📊 Total de chunks: {len(chunks)}")
        print(f"✅ Vectorizados: {vectorized_count}")
        print(f"📦 Colección: {collection_name}\n")
        
    except Exception as e:
        print(f"\n💥 Error durante el procesamiento: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("\n" + "=" * 100)
    print("DEBUG PIPELINE MULTIMODAL - METADATA ENRIQUECIDA")
    print("=" * 100)
    print(f"📍 Documento a probar: {DOCUMENTO_A_PROBAR}")
    print(f"📁 Directorio de debug: {DEBUG_DIR}")
    print("=" * 100 + "\n")
    
    asyncio.run(test_full_pipeline(DOCUMENTO_A_PROBAR))