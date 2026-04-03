"""
whatsapp_router.py
------------------
Webhook da Evolution API v2.

Fluxo:
  1. Evolution API recebe mensagem do WhatsApp
  2. POST /webhook/whatsapp com o payload
  3. Extraímos remetente + texto
  4. Chamamos a Sofia usando o número como session_id (garante memória por contato)
  5. Enviamos a resposta de volta via evolution_service
"""

import logging
from fastapi import APIRouter, Request, HTTPException

from app.agent import sofia
from app.services.evolution_service import send_text_message, strip_markdown

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

    # ─── Chama o agente Sofia ───────────────────────────────
    # Usa o número de telefone como session_id → memória persistente por contato
    try:
        response = sofia.run(text, session_id=phone)
        reply_text = strip_markdown(response.content)
    except Exception as e:
        logger.exception(f"[WhatsApp] Erro ao processar mensagem de {phone}")
        return {"status": "error", "detail": str(e)}

    # ─── Envia resposta via Evolution API ──────────────────
    try:
        send_text_message(phone=phone, text=reply_text)
        logger.info(f"[WhatsApp] Resposta enviada para {phone}")
    except Exception as e:
        logger.exception(f"[WhatsApp] Erro ao enviar resposta para {phone}")
        return {"status": "error", "detail": f"Falha ao enviar mensagem: {e}"}

    return {"status": "ok", "phone": phone}
