import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
#--------------------------------------------------
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
#--------------------------------------------------
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "ollama")
VISION_MODEL_NAME = os.getenv("VISION_MODEL_NAME", "gemma3:4b")
#--------------------------------------------------
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
#--------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "cerebras")
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "llama-3.3-70b")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
#--------------------------------------------------
REPORT_MAX_EVIDENCE = int(os.getenv("REPORT_MAX_EVIDENCE", "50"))
REPORT_MAX_DEFECTS = int(os.getenv("REPORT_MAX_DEFECTS", "10"))
#--------------------------------------------------
REPORTS_DIR = PROJECT_ROOT / "data_store" / "reports"
REPORTS_DIR.mkdir(parents=True, exist_ok=True)
#--------------------------------------------------
