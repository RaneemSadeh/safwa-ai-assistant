"""
Central configuration for Safwa Bank RAG System.
"""
import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent.parent
load_dotenv(BASE_DIR / ".env")

DATA_DIR    = BASE_DIR / "Data"
CHROMA_DIR  = BASE_DIR / "chroma_db"
DB_FILE     = BASE_DIR / "safwa_users.db"

OLLAMA_BASE_URL    = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
LLM_MODEL          = os.getenv("LLM_MODEL", "mistral")
LLM_TEMPERATURE    = 0.05          
LLM_MAX_TOKENS     = 1024
LLM_CONTEXT_LENGTH = 8192          

EMBEDDING_MODEL  = "paraphrase-multilingual-mpnet-base-v2"
COLLECTION_NAME  = "safwa_policies"

CHUNK_SIZE      = 800
CHUNK_OVERLAP   = 150
TOP_K_RESULTS   = 3

SECRET_KEY     = os.getenv("SECRET_KEY", "safwa-default-secret")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin123")

ROLES = {
    "it":         {"ar": "تقنية المعلومات",     "en": "IT / Technical"},
    "business":   {"ar": "الأعمال",              "en": "Business"},
    "management": {"ar": "الإدارة",              "en": "Management / Executive"},
    "hr":         {"ar": "الموارد البشرية",      "en": "HR"},
    "legal":      {"ar": "القانوني / الامتثال",  "en": "Legal / Compliance"},
    "general":    {"ar": "موظف عام",             "en": "General Staff"},
}

DEPARTMENTS = [
    "تقنية المعلومات / IT",
    "إدارة المخاطر / Risk Management",
    "الأمن السيبراني / Cybersecurity",
    "الموارد البشرية / HR",
    "المالية / Finance",
    "العمليات / Operations",
    "الامتثال / Compliance",
    "القانوني / Legal",
    "خدمة العملاء / Customer Service",
    "الإدارة العليا / Senior Management",
    "أخرى / Other",
]
