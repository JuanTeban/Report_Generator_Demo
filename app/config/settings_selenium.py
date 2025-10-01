import os
from dotenv import load_dotenv

load_dotenv()

DEBUGGER_ADDRESS = os.getenv("DEBUGGER_ADDRESS")  # ej: "localhost:9222"
DOWNLOAD_FOLDER = os.getenv("DOWNLOAD_FOLDER", os.path.join(os.path.dirname(__file__), "descargas"))
# NUEVO: carpeta de descargas para modo por ticket
DOWNLOAD_FOLDER_TICKETS = os.getenv("DOWNLOAD_FOLDER_TICKETS", os.path.join(os.path.dirname(__file__), "descargas_tickets"))
# Modo debug
DEBUG_MODE = os.getenv("DEBUG_MODE", "False").lower() in ('true', '1', 't')