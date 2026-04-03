import uuid
from typing import Optional
from pydantic import BaseModel
from agno.os import AgentOS
from app.agent import sofia

# AgentOS cria o app FastAPI com todas as rotas do Agno (incluindo /agui)
agent_os = AgentOS(agents=[sofia], cors_allowed_origins=["http://localhost:3000"])
app = agent_os.get_app()


# -------------------------------------------------------------------
# Endpoint /chat — usado pelo Agent UI (Next.js)
# -------------------------------------------------------------------
class ChatInput(BaseModel):
    message: str
    session_id: Optional[str] = None  # mantém memória entre mensagens


@app.post("/chat")
def chat(payload: ChatInput):
    session_id = payload.session_id or str(uuid.uuid4())
    response = sofia.run(payload.message, session_id=session_id)
    return {
        "response": response.content,
        "session_id": session_id,
    }
