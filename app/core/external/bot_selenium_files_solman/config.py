import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

DEBUGGER_ADDRESS = os.getenv("DEBUGGER_ADDRESS")

PROJECT_ROOT = Path(__file__).resolve().parents[4]
UPLOADS_MULTIMODAL_DIR = PROJECT_ROOT / "data_store/etl_store/uploads_multimodal"

DOWNLOAD_FOLDER = str(UPLOADS_MULTIMODAL_DIR / "by_responsable")

DOWNLOAD_FOLDER_TICKETS = str(UPLOADS_MULTIMODAL_DIR / "by_ticket")

DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() in ('true', '1', 't')