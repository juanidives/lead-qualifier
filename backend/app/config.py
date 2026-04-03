import os
from dotenv import load_dotenv

load_dotenv()

# ── OpenAI ────────────────────────────────────────────
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
CLIENT = os.getenv("CLIENT", "clinica-estetica")

# ── Evolution API (WhatsApp gateway) ──────────────────
EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "minha-chave-secreta")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "clinica-estetica")