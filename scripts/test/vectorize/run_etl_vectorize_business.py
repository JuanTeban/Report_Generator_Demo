#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Script para probar la ingesta y vectorización de Business Rules.

Utiliza la carpeta uploads_business para procesar archivos PDF, TXT, MD
y los vectoriza en la colección business_rules de ChromaDB.
"""

import asyncio
import argparse
import logging
from pathlib import Path
import sys

# Ensure project root is on sys.path when running as a script
try:
    import app  # type: ignore
except ModuleNotFoundError:
    project_root = Path(__file__).resolve().parents[3]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

from app.core.etl.business.vectorize import vectorize_business_rules
from app.config import settings_etl as etl_settings


def setup_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )


async def ensure_dirs() -> None:
    """Asegura que todos los directorios necesarios existan."""
    etl_settings.DATA_STORE_PATH.mkdir(parents=True, exist_ok=True)
    etl_settings.DATA_LOG_PATH.mkdir(parents=True, exist_ok=True)
    etl_settings.VECTOR_STORE_DIR.mkdir(parents=True, exist_ok=True)
    etl_settings.UPLOADS_BUSINESS_DIR.mkdir(parents=True, exist_ok=True)


async def run(args) -> int:
    """Ejecuta el pipeline de business rules."""
    logger = logging.getLogger("business_runner")
    await ensure_dirs()

    logger.info("="*80)
    logger.info("BUSINESS RULES ETL PIPELINE")
    logger.info("="*80)
    logger.info(f"Directorio de business rules: {etl_settings.UPLOADS_BUSINESS_DIR}")
    logger.info(f"Colección destino: {etl_settings.BUSINESS_RULES_COLLECTION_NAME}")
    logger.info(f"Tipo de regla: {args.rule_type}")
    logger.info(f"Categoría: {args.category}")
    logger.info(f"Reset colección: {args.reset}")
    logger.info("="*80)

    # Verificar que hay archivos para procesar
    business_files = list(etl_settings.UPLOADS_BUSINESS_DIR.rglob("*"))
    business_files = [f for f in business_files if f.is_file() and f.suffix.lower() in {".pdf", ".txt", ".md"}]
    
    if not business_files:
        logger.warning(f"No se encontraron archivos PDF/TXT/MD en {etl_settings.UPLOADS_BUSINESS_DIR}")
        logger.info("Coloca archivos en la carpeta uploads_business para procesarlos.")
        return 1

    logger.info(f"Archivos encontrados para procesar: {len(business_files)}")
    for f in business_files:
        logger.info(f"  - {f.name}")

    # Ejecutar vectorización
    logger.info("Iniciando vectorización de business rules...")
    try:
        result = await vectorize_business_rules(
            root_dir=etl_settings.UPLOADS_BUSINESS_DIR,
            rule_type=args.rule_type,
            category=args.category,
            reset=args.reset
        )
        
        logger.info("="*80)
        logger.info("RESULTADO DE VECTORIZACIÓN")
        logger.info("="*80)
        logger.info(f"Éxito: {result.get('success', False)}")
        logger.info(f"Documentos añadidos: {result.get('added', 0)}")
        
        if result.get('errors'):
            logger.error("Errores encontrados:")
            for error in result['errors']:
                logger.error(f"  - {error}")
        
        if not result.get('success'):
            logger.error("La vectorización falló.")
            if not args.force:
                return 1
        
        logger.info("¡Vectorización completada exitosamente!")
        
    except Exception as e:
        logger.error(f"Error crítico durante la vectorización: {e}")
        if not args.force:
            return 1

    logger.info("="*80)
    logger.info("PIPELINE COMPLETADO")
    logger.info("="*80)
    logger.info(f"Para inspeccionar la colección '{etl_settings.BUSINESS_RULES_COLLECTION_NAME}':")
    logger.info(f"python -m scripts.test.vectorize.inspect_vector_store --collection {etl_settings.BUSINESS_RULES_COLLECTION_NAME}")
    
    return 0


def main() -> None:
    setup_logging()
    parser = argparse.ArgumentParser(
        description="ETL pipeline para Business Rules - Procesa archivos desde uploads_business"
    )
    parser.add_argument(
        "--rule-type", 
        type=str, 
        default="general", 
        help="Tipo de regla de negocio (default: general)"
    )
    parser.add_argument(
        "--category", 
        type=str, 
        default="default", 
        help="Categoría de la regla (default: default)"
    )
    parser.add_argument(
        "--reset", 
        action="store_true", 
        help="Limpiar la colección antes de añadir nuevos documentos"
    )
    parser.add_argument(
        "--force", 
        action="store_true", 
        help="Continuar aunque haya errores"
    )
    args = parser.parse_args()

    exit_code = asyncio.run(run(args))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()











