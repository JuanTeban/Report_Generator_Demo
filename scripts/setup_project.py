#!/usr/bin/env python3
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from app.config.settings_etl import (
    DATA_STORE_PATH,
    UPLOADS_EXCEL_DIR,
    UPLOADS_BUSINESS_DIR,
    UPLOADS_MULTIMODAL_DIR,
    DATA_LOG_PATH,
    VECTOR_STORE_DIR,
    DUCKDB_DATA_DIR,
    KNOWLEDGE_BASE_DIR
)

def create_directories():
    directories = [
        DATA_STORE_PATH,
        DATA_LOG_PATH,
        UPLOADS_EXCEL_DIR,
        UPLOADS_BUSINESS_DIR,
        UPLOADS_MULTIMODAL_DIR,
        UPLOADS_MULTIMODAL_DIR / "by_responsable",
        UPLOADS_MULTIMODAL_DIR / "by_ticket",
        VECTOR_STORE_DIR,
        DUCKDB_DATA_DIR,
        KNOWLEDGE_BASE_DIR,
        DATA_LOG_PATH / "logs_report_generator",
        DATA_LOG_PATH / "debug_multimodal",
        DATA_LOG_PATH / "tmp_images",
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

if __name__ == "__main__":
    create_directories()