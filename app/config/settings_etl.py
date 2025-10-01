from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
print(PROJECT_ROOT)
DATA_STORE_PATH = PROJECT_ROOT / "data_store/etl_store"
DATA_LOG_PATH = PROJECT_ROOT / "data_store/logs_vectorization"
DATA_KNOWLEDGE_SCHEMA_PATH = PROJECT_ROOT / "data_store/knowledge_base"
DATA_LOGS_PATH = PROJECT_ROOT / "data_store/logs"
print(DATA_STORE_PATH)
#--------------------------------------------------
# Directorios de uploads (todos al mismo nivel)
UPLOADS_EXCEL_DIR = DATA_STORE_PATH / "uploads_excel"
UPLOADS_BUSINESS_DIR = DATA_STORE_PATH / "uploads_business"
UPLOADS_MULTIMODAL_DIR = DATA_STORE_PATH / "uploads_multimodal"
UPLOADS_DIR = UPLOADS_EXCEL_DIR #Here can change this variable to the excel, but for now we keep in this way.
#--------------------------------------------------

DUCKDB_DATA_DIR = DATA_STORE_PATH / "duckdb_data"
KNOWLEDGE_BASE_DIR = DATA_STORE_PATH / "knowledge_base"
DUCKDB_PATH = DUCKDB_DATA_DIR / "analytics.duckdb"
DUCKDB_LOG_TABLE = "_ingestion_log"
#--------------------------------------------------
VECTOR_STORE_DIR = DATA_STORE_PATH / "vector_store"
CHROMA_COLLECTION_NAME = DATA_KNOWLEDGE_SCHEMA_PATH / "sql_knowledge_base" #Change the name of the colection is here
print(Path(str(CHROMA_COLLECTION_NAME)).name)
VECTORIZATION_LOG_FILE = DATA_LOG_PATH / "vectorization_log.json"
#--------------------------------------------------
CHROMA_COLLECTIONS = {
    "schema_knowledge": "sql_knowledge_base",      
    "business_rules": "business_rules",          
    "external_docs": "external_docs",
    "multimodal_evidence": "multimodal_evidence",
    "historical_solutions": "historical_solutions",        
}
#----------------business rules---------------------------
BUSINESS_RULES_DIR = DATA_STORE_PATH / "business_rules"
BUSINESS_RULES_COLLECTION_NAME = "business_rules"
BUSINESS_RULES_LOG_FILE = DATA_LOG_PATH / "business_rules_log.json"

