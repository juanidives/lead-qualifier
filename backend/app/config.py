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

# ── Redis (broker Celery) ─────────────────────────────
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# ── PostgreSQL (memória do agente — Fase 3) ───────────
# Vazio em dev → usa SQLite. Preenchido em produção → usa PostgreSQL.
POSTGRES_URL = os.getenv("POSTGRES_URL", "")

# ── Mercado Pago (pagamentos) ─────────────────────────────────────
MERCADOPAGO_ACCESS_TOKEN = os.getenv("MERCADOPAGO_ACCESS_TOKEN", "")
MERCADOPAGO_WEBHOOK_SECRET = os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "")

# ── Informações do Negócio ────────────────────────────────────────
OWNER_PHONE = os.getenv("OWNER_PHONE", "")