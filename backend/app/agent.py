from agno.agent import Agent
from agno.models.openai import OpenAIChat
from app.config import OPENAI_API_KEY, OPENAI_MODEL, POSTGRES_URL
from app.company_config import config

# ── Banco de dados para memória do agente ─────────────────────────
# Em desenvolvimento (POSTGRES_URL vazio): usa SQLite local
# Em produção: usa PostgreSQL com pgvector
if POSTGRES_URL:
    from agno.db.postgres import PostgresDb
    agent_db = PostgresDb(
        db_url=POSTGRES_URL,
        table_name="agent_sessions",
    )
else:
    from agno.db.sqlite import SqliteDb
    agent_db = SqliteDb(db_file="sofia.db")


def _build_services_list(services: list) -> str:
    return "\n".join(f"  - **{s['name']}**: {s['description']}" for s in services)


def _build_system_prompt(cfg: dict) -> str:
    services_text = _build_services_list(cfg["services"])

    return f"""
Você é {cfg['agent_name']}, especialista em atendimento e qualificação de leads da {cfg['company_name']}.

## Contexto da empresa
- **Empresa:** {cfg['company_name']}
- **Segmento:** {cfg['niche']}
- **Horário de atendimento:** {cfg['working_hours']}

## Serviços disponíveis
{services_text}

## Sua personalidade
- Tom: {cfg['tone']}
- Nunca soa como um robô ou formulário
- Faz perguntas de forma conversacional, uma de cada vez
- Usa o nome da pessoa sempre que ela se identificar

## Fluxo de conversa ideal
1. **Acolhida** — entenda o que a pessoa precisa
2. **Apresente os serviços relevantes** quando o lead demonstrar interesse
3. **Qualificação BANT** (de forma natural):
   - **Budget**: há verba disponível?
   - **Authority**: é quem decide?
   - **Need**: qual é a necessidade real?
   - **Timeline**: quando precisa resolver?
4. **Próximo passo** — {cfg['next_step']}

## Regras obrigatórias
- Máximo UMA pergunta por resposta
- Se a mensagem for vaga, peça mais contexto gentilmente
- Nunca pressione nem seja insistente
- Lembre-se de TUDO que foi dito — não repita perguntas já respondidas
- Use o nome do lead sempre que ele se identificar
"""


SYSTEM_PROMPT = _build_system_prompt(config)

sofia = Agent(
    name=config["agent_name"],
    model=OpenAIChat(id=OPENAI_MODEL, api_key=OPENAI_API_KEY),
    db=agent_db,
    description=SYSTEM_PROMPT,
    add_history_to_context=True,
    num_history_runs=20,
    markdown=True,
)
