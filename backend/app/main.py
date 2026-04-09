"""
main.py
-------
Aplicação FastAPI principal.
Integra webhooks WhatsApp e endpoints de chat.

Mercado Pago foi removido — o cliente usa transferência bancária com alias.
"""

import logging
import uuid
from typing import Optional
from pydantic import BaseModel
from agno.os import AgentOS
from app.agent import agent
from app.routers.whatsapp_router import router as whatsapp_router

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from app.company_config import config as company_config

# AgentOS cria o app FastAPI com todas as rotas do Agno (incluindo /agui)
agent_os = AgentOS(agents=[agent], cors_allowed_origins=["http://localhost:3000"])
app = agent_os.get_app()

# Registra o webhook do WhatsApp
app.include_router(whatsapp_router)


# -------------------------------------------------------------------
# Endpoint /agent-info — retorna dados do agente ativo para o frontend
# -------------------------------------------------------------------
@app.get("/agent-info")
def get_config():
    """
    Retorna o nome e a descrição do agente ativo.
    O frontend usa isso para exibir o nome correto do agente.
    """
    return {
        "agent_name": company_config.get("agent_name", "Agente"),
        "niche": company_config.get("niche", ""),
        "company_name": company_config.get("company_name", ""),
    }


# -------------------------------------------------------------------
# Endpoint /chat — usado pelo Agent UI (Next.js)
# -------------------------------------------------------------------
class ChatInput(BaseModel):
    message: str
    session_id: Optional[str] = None  # mantém memória entre mensagens


@app.post("/chat")
def chat(payload: ChatInput):
    """
    Endpoint para chat via Agent UI.
    Mantém contexto de sessão usando session_id.
    """
    session_id = payload.session_id or str(uuid.uuid4())
    response = agent.run(payload.message, session_id=session_id)
    return {
        "response": response.content,
        "session_id": session_id,
    }
