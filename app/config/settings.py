import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()
#--------------------------------------------------
EMBEDDING_PROVIDER = os.getenv("EMBEDDING_PROVIDER", "ollama")
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "nomic-embed-text")
#--------------------------------------------------
EMBEDDING_PROVIDER = "ollama"   # HERE CAN CHANGE THE EMBEDDING PROVIDER
EMBEDDING_MODEL_NAME = "nomic-embed-text" # HERE CAN CHANGE THE EMBEDDING MODEL
#--------------------------------------------------
VISION_PROVIDER = os.getenv("VISION_PROVIDER", "ollama")
VISION_MODEL_NAME = os.getenv("VISION_MODEL_NAME", "gemma3:4b")
#--------------------------------------------------
GEMINI_API_KEY = ""
OLLAMA_HOST = "http://localhost:11434"
#--------------------------------------------------
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "cerebras")  # "cerebras" o "ollama"
LLM_MODEL_NAME = os.getenv("LLM_MODEL_NAME", "llama-3.3-70b")
CEREBRAS_API_KEY = os.getenv("CEREBRAS_API_KEY", "")

# Report Generation
REPORT_MAX_EVIDENCE = int(os.getenv("REPORT_MAX_EVIDENCE", "50"))
REPORT_MAX_DEFECTS = int(os.getenv("REPORT_MAX_DEFECTS", "10"))





