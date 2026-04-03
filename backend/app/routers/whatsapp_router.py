"""
whatsapp_router.py
------------------
Webhook da Evolution API v2.

Fluxo COM Celery (assíncrono):
  1. Evolution API recebe mensagem do WhatsApp
  2. POST /webhook/whatsapp com o payload
  3. FastAPI extrai phone + texto
  4. FastAPI enfileira a tarefa no Redis (.delay) → responde 200 IMEDIATAMENTE
  5. Celery Worker processa em background: chama Sofia → envia resposta

Vantagem: o webhook nunca trava nem dá timeout, independente de quanto
a OpenAI demore para responder.
"""

import logging
from fastapi import APIRouter, Request, HTTPException

from app.workers.tasks import process_whatsapp_message

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["whatsapp"])


# ─────────────────────────────────────────────────────────────
# Helpers para parsear o payload da Evolution API v2
# ─────────────────────────────────────────────────────────────

def _extract_phone(remote_jid: str) -> str | None:
    """
    Extrai o número limpo do remoteJid.
    "5511999990000@s.whatsapp.net" → "5511999990000"
    "5511999990000-1234567890@g.us" → None (grupo, ignoramos)
    """
    if "@g.us" in remote_jid:
        return None  # mensagem de grupo — ignorar por enquanto
    return remote_jid.split("@")[0]


def _extract_text(data: dict) -> str | None:
    """
    Extrai o texto da mensagem.
    Evolution API v2 pode trazer texto em vários campos dependendo do tipo.
    """
    msg = data.get("message", {})
    return (
        msg.get("conversation")
        or msg.get("extendedTextMessage", {}).get("text")
        or msg.get("imageMessage", {}).get("caption")
        or None
    )


# ─────────────────────────────────────────────────────────────
# Webhook principal
# ─────────────────────────────────────────────────────────────

@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Recebe todos os eventos da Evolution API.
    Filtra apenas mensagens recebidas (não enviadas por nós).
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido")

    event = payload.get("event", "")
    logger.info(f"[WhatsApp webhook] evento: {event}")

    # Só processamos mensagens recebidas
    if event != "MESSAGES_UPSERT":
        return {"status": "ignored", "event": event}

    data = payload.get("data", {})
    key = data.get("key", {})

    # Ignorar mensagens enviadas pelo próprio bot
    if key.get("fromMe", False):
        return {"status": "ignored", "reason": "fromMe"}

    remote_jid = key.get("remoteJid", "")
    phone = _extract_phone(remote_jid)

    if not phone:
        return {"status": "ignored", "reason": "group_message"}

    text = _extract_text(data)
    if not text:
        logger.warning(f"[WhatsApp] Mensagem sem texto de {phone}, ignorando.")
        return {"status": "ignored", "reason": "no_text"}

    push_name = data.get("pushName", "")
    logger.info(f"[WhatsApp] {push_name} ({phone}): {text[:80]}")

    # ─── Enfileira a tarefa no Celery ──────────────────────
    # .delay() retorna imediatamente — o processamento acontece em background
    process_whatsapp_message.delay(
        phone=phone,
        text=text,
        push_name=push_name,
    )

    # Responde 200 imediatamente — a Evolution API não fica esperando
    return {"status": "queued", "phone": phone}
