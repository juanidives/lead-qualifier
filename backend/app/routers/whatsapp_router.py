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
from datetime import datetime

from app.workers.tasks import process_whatsapp_message
from app.database import SessionLocal
from app.models import Contact, Conversation

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


def _detect_audio_message(data: dict) -> bool:
    """
    Detecta se a mensagem é áudio.
    Evolution API v2 envia como 'audioMessage' ou 'pttMessage' (push-to-talk).
    """
    msg = data.get("message", {})
    return bool(msg.get("audioMessage") or msg.get("pttMessage"))


def _detect_image_message(data: dict) -> bool:
    """
    Detecta se a mensagem é imagem.
    """
    msg = data.get("message", {})
    return bool(msg.get("imageMessage"))


def _save_or_update_contact(phone: str, push_name: str = "") -> Contact:
    """
    Salva ou atualiza um contato no banco de dados.
    Contatos inbound chegam como is_active=true e source='inbound_whatsapp'.

    Args:
        phone: número no formato internacional
        push_name: nome do contato (do WhatsApp)

    Returns:
        Instância de Contact
    """
    db = SessionLocal()

    try:
        # Busca contato existente
        contact = db.query(Contact).filter(Contact.phone == phone).first()

        if not contact:
            # Novo contato
            contact = Contact(
                name=push_name or phone,  # usa nome se disponível, senão número
                phone=phone,
                source='inbound_whatsapp',
                is_active=True
            )
            db.add(contact)
            logger.info(f"[WhatsApp] Novo contato criado: {phone} ({push_name})")
        else:
            # Contato existente — atualiza nome se vazio
            if not contact.name or contact.name == contact.phone:
                contact.name = push_name or contact.name

        db.commit()
        db.refresh(contact)
        return contact

    except Exception as e:
        logger.exception(f"[WhatsApp] Erro ao salvar contato {phone}")
        db.rollback()
        return None

    finally:
        db.close()


def _save_conversation(contact_id: int, role: str, content: str, msg_type: str = 'text'):
    """
    Salva mensagem no histórico de conversa.

    Args:
        contact_id: ID do contato
        role: 'user' ou 'agent'
        content: conteúdo da mensagem
        msg_type: 'text', 'audio', 'image'
    """
    db = SessionLocal()

    try:
        conversation = Conversation(
            contact_id=contact_id,
            role=role,
            content=content,
            type=msg_type
        )
        db.add(conversation)
        db.commit()
        logger.debug(f"[WhatsApp] Conversa salva: {contact_id} ({role})")

    except Exception as e:
        logger.warning(f"[WhatsApp] Erro ao salvar conversa: {e}")
        db.rollback()

    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# Webhook principal
# ─────────────────────────────────────────────────────────────

@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Recebe todos os eventos da Evolution API.
    Filtra apenas mensagens recebidas (não enviadas por nós).

    Tipos de mensagem:
    - Texto normal: process via agent (Sofia/Juani)
    - Áudio: responde com auto-resposta em espanhol
    - Imagem com caption: trata caption como texto
    - Imagem sem caption: ignora
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

    push_name = data.get("pushName", "")

    # ─── DETECÇÃO DE TIPO DE MENSAGEM ──────────────────────
    # Áudio/PTT: responde com auto-resposta
    if _detect_audio_message(data):
        logger.info(f"[WhatsApp] Mensagem de áudio de {phone}, enviando auto-resposta")

        # Salva contato se novo
        contact = _save_or_update_contact(phone, push_name)

        # Log da mensagem de áudio
        if contact:
            _save_conversation(contact.id, 'user', '[Áudio não transcrito]', msg_type='audio')

        # Enfileira envio de auto-resposta
        from app.workers.tasks import send_audio_autoresponse
        send_audio_autoresponse.delay(phone)

        return {"status": "queued", "phone": phone, "type": "audio"}

    # ─── MENSAGEM DE TEXTO/CAPTION ──────────────────────────
    text = _extract_text(data)

    if not text:
        # Imagem sem caption — ignorar
        if _detect_image_message(data):
            logger.warning(f"[WhatsApp] Imagem sem caption de {phone}, ignorando.")
            return {"status": "ignored", "reason": "image_no_caption"}

        logger.warning(f"[WhatsApp] Mensagem sem texto de {phone}, ignorando.")
        return {"status": "ignored", "reason": "no_text"}

    logger.info(f"[WhatsApp] {push_name} ({phone}): {text[:80]}")

    # Salva contato se novo
    contact = _save_or_update_contact(phone, push_name)

    # Log da mensagem do usuário
    if contact:
        msg_type = 'image' if _detect_image_message(data) else 'text'
        _save_conversation(contact.id, 'user', text, msg_type=msg_type)

    # ─── Enfileira a tarefa no Celery ──────────────────────
    # .delay() retorna imediatamente — o processamento acontece em background
    process_whatsapp_message.delay(
        phone=phone,
        text=text,
        push_name=push_name,
    )

    # Responde 200 imediatamente — a Evolution API não fica esperando
    return {"status": "queued", "phone": phone}
