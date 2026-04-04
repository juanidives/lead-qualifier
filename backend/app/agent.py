"""
agent.py
--------
Instância central do agente Agno.

Carrega o cliente ativo (definido por CLIENT no .env),
seleciona o builder de prompt correto pela vertical (client_type),
e instancia o agente com memória persistente.

Para adicionar um novo cliente:
  1. Crie clients/<slug>/config.yaml com client_type declarado
  2. Se for uma nova vertical, adicione o builder em app/prompts/

Para trocar de cliente:
  - Altere CLIENT=<slug> no backend/.env e reinicie o servidor
"""

from agno.agent import Agent
from agno.models.openai import OpenAIChat

from app.config import OPENAI_API_KEY, OPENAI_MODEL, POSTGRES_URL
from app.company_config import config
from app.prompts import get_prompt_builder

# ── Banco de dados para memória do agente ─────────────────────────
# POSTGRES_URL vazio → usa SQLite (desenvolvimento)
# POSTGRES_URL preenchido → usa PostgreSQL (produção)
if POSTGRES_URL:
    from agno.db.postgres import PostgresDb
    agent_db = PostgresDb(
        db_url=POSTGRES_URL,
        table_name="agent_sessions",
    )
else:
    from agno.db.sqlite import SqliteDb
    agent_db = SqliteDb(db_file="sofia.db")

# ── System prompt — selecionado pela vertical do cliente ──────────
# O campo client_type no config.yaml define qual builder usar.
# Ex: "lead_qualifier" → prompts/lead_qualifier.py
#     "beverages"      → prompts/beverages.py
build_prompt = get_prompt_builder(config["client_type"])
SYSTEM_PROMPT = build_prompt(config)

# ── Instância do agente ───────────────────────────────────────────
agent = Agent(
    name=config["agent_name"],
    model=OpenAIChat(id=OPENAI_MODEL, api_key=OPENAI_API_KEY),
    db=agent_db,
    description=SYSTEM_PROMPT,
    add_history_to_context=True,
    num_history_runs=20,
    markdown=True,
)
