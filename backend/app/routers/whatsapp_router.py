"""
whatsapp_router.py
------------------
Webhook da Evolution API v2.

Fluxo de mensagens:
  1. Mensagens do owner_phone — comandos determinísticos sem LLM
       CONFIRMAR PAGO [nombre] → confirma pago, notifica cliente
       LISTO [nombre]          → pedido pronto para retiro
       ENVIADO [nombre]        → pedido enviado para entrega
       (outras mensagens do dono são ignoradas silenciosamente)

  2. Comprovantes de pagamento do cliente (imagem ou keywords)
       → Ack imediato ao cliente
       → Salva pedido no banco (status: waiting_payment_confirm)
       → Envia MSG 1 + MSG 2 ao dono

  3. Mensagens normais de clientes
       → Processadas pelo agente Agno via Celery (assíncrono)
"""

import logging
from decimal import Decimal
from fastapi import APIRouter, Request, HTTPException
from datetime import datetime

from app.workers.tasks import process_whatsapp_message, send_audio_autoresponse
from app.services import order_commands_service
from app.services.evolution_service import send_text_message, send_button_message
from app.database import SessionLocal
from app.models import Contact, Conversation, CustomerOrder
from app.company_config import config as company_config

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook", tags=["whatsapp"])


# ─────────────────────────────────────────────────────────────
# Configuração carregada uma vez no startup
# ─────────────────────────────────────────────────────────────

# Números do dono — recebem notificações e enviam comandos
_owner_cfg = company_config.get("owner_phone", "")
if isinstance(_owner_cfg, list):
    OWNER_PHONES = set(str(p) for p in _owner_cfg if p)
else:
    OWNER_PHONES = {str(_owner_cfg)} if _owner_cfg else set()

# Keywords que indicam comprovante de pagamento (espanhol argentino)
PAYMENT_KEYWORDS = [
    'transferido', 'transferí', 'transferi', 'transf',
    'pagué', 'pague', 'pagado',
    'hecho', 'hice',
    'comprobante',
    'ya pagué', 'ya pague',
    'ya transferí', 'ya transferi',
    'hice la transferencia', 'hice el pago',
    'envié el pago', 'envie el pago',
    'listo el pago',
]


# ─────────────────────────────────────────────────────────────
# Helpers — extração de dados do payload Evolution API v2
# ─────────────────────────────────────────────────────────────

def _extract_phone(remote_jid: str) -> str | None:
    """
    Extrai o número limpo do remoteJid.
    "5511999990000@s.whatsapp.net" → "5511999990000"
    "5511999990000-1234567890@g.us" → None (grupo, ignorar)
    """
    if "@g.us" in remote_jid:
        return None
    return remote_jid.split("@")[0]


def _extract_text(data: dict) -> str | None:
    """Extrai o texto da mensagem (suporta texto, extended text e caption de imagem)."""
    msg = data.get("message", {})
    return (
        msg.get("conversation")
        or msg.get("extendedTextMessage", {}).get("text")
        or msg.get("imageMessage", {}).get("caption")
        or None
    )


def _detect_audio_message(data: dict) -> bool:
    """Detecta mensagem de áudio ou PTT (push-to-talk)."""
    msg = data.get("message", {})
    return bool(msg.get("audioMessage") or msg.get("pttMessage"))


def _detect_image_message(data: dict) -> bool:
    """Detecta mensagem de imagem."""
    msg = data.get("message", {})
    return bool(msg.get("imageMessage"))


def _extract_button_response(data: dict) -> str | None:
    """
    Extrai o ID do botão selecionado quando o owner toca em um botão interativo.
    Evolution API envia buttonsResponseMessage dentro de data.message.
    Retorna o selectedButtonId ou None se não for resposta de botão.
    """
    msg = data.get("message", {})
    resp = msg.get("buttonsResponseMessage", {})
    return resp.get("selectedButtonId") or None


def _is_payment_proof(text: str | None, has_image: bool) -> bool:
    """
    Detecta se a mensagem é um comprovante de pagamento.
    Qualquer imagem OU texto contendo keywords de pagamento é tratado como comprovante.
    """
    if has_image:
        return True
    if not text:
        return False
    text_lower = text.lower()
    return any(kw in text_lower for kw in PAYMENT_KEYWORDS)


# ─────────────────────────────────────────────────────────────
# Helpers — banco de dados
# ─────────────────────────────────────────────────────────────

def _save_or_update_contact(phone: str, push_name: str = "") -> Contact | None:
    """
    Salva ou atualiza um contato no banco.
    Contatos recebidos via WhatsApp chegam como source='inbound_whatsapp'.
    """
    db = SessionLocal()
    try:
        contact = db.query(Contact).filter(Contact.phone == phone).first()

        if not contact:
            contact = Contact(
                name=push_name or phone,
                phone=phone,
                source='inbound_whatsapp',
                is_active=True
            )
            db.add(contact)
            logger.info(f"[WhatsApp] Novo contato criado: {phone} ({push_name})")
        else:
            if not contact.name or contact.name == contact.phone:
                contact.name = push_name or contact.name

        db.commit()
        db.refresh(contact)
        return contact

    except Exception:
        logger.exception(f"[WhatsApp] Erro ao salvar contato {phone}")
        db.rollback()
        return None

    finally:
        db.close()


def _save_conversation(contact_id: int, role: str, content: str, msg_type: str = 'text'):
    """Salva mensagem no histórico de conversa."""
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
    except Exception:
        logger.warning(f"[WhatsApp] Erro ao salvar conversa: contact_id={contact_id}")
        db.rollback()
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# Helpers — histórico de conversa
# ─────────────────────────────────────────────────────────────

def _get_recent_conversation(contact_id: int, limit: int = 6) -> str:
    """
    Retorna as últimas `limit` mensagens da conversa como texto formatado.
    Útil para mostrar ao owner o que foi pedido quando não há pedido no BD.
    """
    db = SessionLocal()
    try:
        messages = (
            db.query(Conversation)
            .filter(Conversation.contact_id == contact_id)
            .order_by(Conversation.created_at.desc())
            .limit(limit)
            .all()
        )
        if not messages:
            return "(sin historial de conversa)"
        lines = []
        for msg in reversed(messages):
            role_label = "Cliente" if msg.role == "user" else "Juani"
            content = (msg.content or "").replace("\n", " ")[:120]
            lines.append(f"{role_label}: {content}")
        return "\n".join(lines)
    except Exception:
        logger.warning(f"[PaymentProof] Erro ao carregar histórico contact_id={contact_id}")
        return "(error al cargar historial)"
    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# Fluxo de comprovante de pagamento — síncrono (sem Celery)
# ─────────────────────────────────────────────────────────────

def _handle_payment_proof(phone: str, push_name: str) -> None:
    """
    Processa comprovante de pagamento recebido de um cliente.

    Etapas:
      1. Envia ack imediato ao cliente
      2. Busca ou cria pedido no banco com status 'waiting_payment_confirm'
      3. Envia MSG 1 (notificação de pago) ao dono
      4. Envia MSG 2 (detalhes do pedido) ao dono
    """
    # 1. Ack imediato ao cliente
    try:
        send_text_message(
            phone=phone,
            text="Dejame chequear si entró el pago, ya te confirmo 🙌"
        )
    except Exception:
        logger.warning(f"[PaymentProof] Erro ao enviar ack para {phone}")

    db = SessionLocal()
    try:
        # Busca contato
        contact = db.query(Contact).filter(Contact.phone == phone).first()
        cliente_nome = (contact.name if contact and contact.name else push_name) or phone

        # Busca pedido pendente mais recente
        order = None
        if contact:
            order = (
                db.query(CustomerOrder)
                .filter(
                    CustomerOrder.contact_id == contact.id,
                    CustomerOrder.status == 'pending'
                )
                .order_by(CustomerOrder.created_at.desc())
                .first()
            )

        if order:
            # Atualiza status existente
            order.status = 'waiting_payment_confirm'
            db.commit()
            logger.info(f"[PaymentProof] Pedido #{order.id} → waiting_payment_confirm ({phone})")
        elif contact:
            # Cria registro mínimo para rastreamento (sem itens definidos ainda)
            order = CustomerOrder(
                contact_id=contact.id,
                items=[],
                address="—",
                total=Decimal('0'),
                status='waiting_payment_confirm'
            )
            db.add(order)
            db.commit()
            db.refresh(order)
            logger.info(f"[PaymentProof] Pedido mínimo #{order.id} criado para {phone}")

        # Formata dados para mensagens ao dono
        order_id  = order.id if order else "?"
        total_str = f"${float(order.total):.0f}" if order and order.total else "a confirmar"

        # Monta texto dos itens (se disponíveis)
        if order and order.items:
            items_lines = "\n".join([
                f"• {item['product_name']} x{item['quantity']} = ${item['subtotal']:.0f}"
                for item in order.items
            ])
        elif contact:
            # Sem pedido no BD — mostra histórico de conversa para contexto
            conv = _get_recent_conversation(contact.id, limit=6)
            items_lines = f"💬 Últimas mensajes:\n{conv}"
        else:
            items_lines = "(sin historial disponible)"

        # Monta linha de entrega
        address = order.address if order and order.address not in (None, "—", "") else ""
        if address and address.lower() not in ("retiro", "—"):
            delivery_line = f"Envío a: {address}"
        elif address and address.lower() == "retiro":
            delivery_line = "Retiro en depósito"
        else:
            delivery_line = "(modalidad a confirmar)"

        # MSG 1 — Confirmar / Rechazar pago
        msg1_title       = "💰 PAGO RECIBIDO"
        msg1_description = (
            f"Cliente: {cliente_nome}\n"
            f"Teléfono: {phone}\n"
            f"Monto: {total_str}"
        )
        msg1_footer  = "JB Bebidas · confirmá o rechazá el pago"
        msg1_buttons = [
            {"displayText": "✅ Confirmar pago", "id": f"CP:{cliente_nome}"},
            {"displayText": "❌ Rechazar",        "id": f"RP:{cliente_nome}"},
        ]

        # MSG 2 — Detalhes do pedido + ações de entrega
        msg2_title       = f"🛒 PEDIDO #{order_id}"
        msg2_description = (
            f"{items_lines}\n"
            f"─────────────────\n"
            f"Total: {total_str}\n"
            f"{delivery_line}"
        )
        msg2_footer  = "Tocá cuando esté listo o salga para entrega"
        msg2_buttons = [
            {"displayText": "🏪 Listo para retirar", "id": f"LS:{cliente_nome}"},
            {"displayText": "🚚 Enviado",             "id": f"EV:{cliente_nome}"},
        ]

        def _send_with_fallback(owner_phone: str, title: str, description: str,
                                footer: str, buttons: list, fallback_text: str) -> None:
            """Tenta botões; se a API não suportar usa texto puro."""
            try:
                send_button_message(
                    phone=owner_phone,
                    title=title,
                    description=description,
                    footer=footer,
                    buttons=buttons,
                )
            except Exception as btn_err:
                logger.warning(f"[PaymentProof] Botões falhou ({btn_err}), usando texto")
                send_text_message(phone=owner_phone, text=fallback_text)

        # Envia para cada owner
        for owner_phone in OWNER_PHONES:
            try:
                _send_with_fallback(
                    owner_phone,
                    title=msg1_title,
                    description=msg1_description,
                    footer=msg1_footer,
                    buttons=msg1_buttons,
                    fallback_text=(
                        f"{msg1_title}\n{msg1_description}\n"
                        f"─────────────────\n"
                        f"CONFIRMAR PAGO {cliente_nome}  →  confirma al cliente\n"
                        f"RECHAZAR {cliente_nome}         →  rechazá el pago"
                    ),
                )
                _send_with_fallback(
                    owner_phone,
                    title=msg2_title,
                    description=msg2_description,
                    footer=msg2_footer,
                    buttons=msg2_buttons,
                    fallback_text=(
                        f"{msg2_title}\n{msg2_description}\n"
                        f"─────────────────\n"
                        f"LISTO {cliente_nome}   →  avisa que está listo para retirar\n"
                        f"ENVIADO {cliente_nome}  →  avisa que salió para entrega"
                    ),
                )
                logger.info(f"[PaymentProof] Notificações enviadas para owner {owner_phone}")
            except Exception:
                logger.exception(f"[PaymentProof] Erro ao notificar owner {owner_phone}")

    except Exception:
        logger.exception(f"[PaymentProof] Erro ao processar comprovante de {phone}")
        db.rollback()

    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# Webhook principal
# ─────────────────────────────────────────────────────────────

@router.post("/whatsapp")
async def whatsapp_webhook(request: Request):
    """
    Recebe todos os eventos da Evolution API e roteia conforme o tipo.
    """
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Payload inválido")

    # Normaliza nome do evento (Evolution API v2.3.7 usa minúsculas com ponto)
    event = payload.get("event", "").upper().replace(".", "_")
    logger.info(f"[WhatsApp webhook] evento: {event}")

    # Só processa mensagens recebidas
    if event != "MESSAGES_UPSERT":
        return {"status": "ignored", "event": event}

    data = payload.get("data", {})
    key  = data.get("key", {})

    # Ignora mensagens enviadas pelo próprio bot
    if key.get("fromMe", False):
        return {"status": "ignored", "reason": "fromMe"}

    remote_jid = key.get("remoteJid", "")
    phone = _extract_phone(remote_jid)

    if not phone:
        return {"status": "ignored", "reason": "group_message"}

    push_name = data.get("pushName", "")

    # ─── PRIORIDADE 1: comandos do dono ────────────────────
    # Mensagens do owner_phone são processadas deterministicamente,
    # nunca passam pelo agente Agno (LLM).
    if phone in OWNER_PHONES:
        # Detecta resposta de botão interativo (owner tocou no botão)
        button_id = _extract_button_response(data)
        if button_id:
            # Mapeia ID do botão para comando de texto equivalente
            # Formato dos IDs: "CP:Nome", "RP:Nome", "LS:Nome", "EV:Nome"
            if button_id.startswith("CP:"):
                nombre = button_id[3:]
                logger.info(f"[WhatsApp] Owner botão CONFIRMAR PAGO '{nombre}' de {phone}")
                order_commands_service.handle_confirmar_pago(nombre, owner_phone=phone)
                return {"status": "ok", "command": "CONFIRMAR PAGO (button)"}
            elif button_id.startswith("RP:"):
                nombre = button_id[3:]
                logger.info(f"[WhatsApp] Owner botão RECHAZAR '{nombre}' de {phone}")
                # Por enquanto apenas loga — pode ser expandido depois
                return {"status": "ok", "command": "RECHAZAR (button)"}
            elif button_id.startswith("LS:"):
                nombre = button_id[3:]
                logger.info(f"[WhatsApp] Owner botão LISTO '{nombre}' de {phone}")
                order_commands_service.handle_listo(nombre, owner_phone=phone)
                return {"status": "ok", "command": "LISTO (button)"}
            elif button_id.startswith("EV:"):
                nombre = button_id[3:]
                logger.info(f"[WhatsApp] Owner botão ENVIADO '{nombre}' de {phone}")
                order_commands_service.handle_enviado(nombre, owner_phone=phone)
                return {"status": "ok", "command": "ENVIADO (button)"}
            else:
                logger.info(f"[WhatsApp] Owner tocou botão desconhecido: '{button_id}'")
                return {"status": "ignored", "reason": "unknown_button"}

        text = _extract_text(data)
        if not text:
            return {"status": "ignored", "reason": "owner_no_text"}

        command, nombre = order_commands_service.parse_owner_command(text)

        if command == "CONFIRMAR PAGO":
            logger.info(f"[WhatsApp] Owner cmd CONFIRMAR PAGO '{nombre}' de {phone}")
            order_commands_service.handle_confirmar_pago(nombre, owner_phone=phone)
            return {"status": "ok", "command": "CONFIRMAR PAGO"}

        elif command == "LISTO":
            logger.info(f"[WhatsApp] Owner cmd LISTO '{nombre}' de {phone}")
            order_commands_service.handle_listo(nombre, owner_phone=phone)
            return {"status": "ok", "command": "LISTO"}

        elif command == "ENVIADO":
            logger.info(f"[WhatsApp] Owner cmd ENVIADO '{nombre}' de {phone}")
            order_commands_service.handle_enviado(nombre, owner_phone=phone)
            return {"status": "ok", "command": "ENVIADO"}

        else:
            # Mensagem do dono que não é um comando — ignorar silenciosamente
            logger.info(f"[WhatsApp] Mensagem do owner sem comando reconhecido: '{text[:40]}'")
            return {"status": "ignored", "reason": "owner_non_command"}

    # ─── PRIORIDADE 2: áudio — auto-resposta ───────────────
    if _detect_audio_message(data):
        logger.info(f"[WhatsApp] Áudio de {phone}, enviando auto-resposta")
        contact = _save_or_update_contact(phone, push_name)
        if contact:
            _save_conversation(contact.id, 'user', '[Áudio não transcrito]', msg_type='audio')
        send_audio_autoresponse.delay(phone)
        return {"status": "queued", "phone": phone, "type": "audio"}

    # ─── PRIORIDADE 3: comprovante de pagamento ─────────────
    # Qualquer imagem OU texto com keywords de pagamento
    is_image = _detect_image_message(data)
    text      = _extract_text(data)

    if _is_payment_proof(text, is_image):
        logger.info(f"[WhatsApp] Comprovante de pagamento de {phone} ({push_name})")
        contact = _save_or_update_contact(phone, push_name)
        if contact:
            _save_conversation(
                contact.id, 'user',
                '[Comprovante de pagamento]' if is_image else text,
                msg_type='image' if is_image else 'text'
            )
        _handle_payment_proof(phone=phone, push_name=push_name)
        return {"status": "ok", "phone": phone, "type": "payment_proof"}

    # ─── PRIORIDADE 4: mensagem de texto normal ─────────────
    if not text:
        logger.warning(f"[WhatsApp] Mensagem sem texto de {phone}, ignorando.")
        return {"status": "ignored", "reason": "no_text"}

    logger.info(f"[WhatsApp] {push_name} ({phone}): {text[:80]}")

    contact = _save_or_update_contact(phone, push_name)
    if contact:
        msg_type = 'image' if is_image else 'text'
        _save_conversation(contact.id, 'user', text, msg_type=msg_type)

    # Enfileira para o agente Agno via Celery
    process_whatsapp_message.delay(
        phone=phone,
        text=text,
        push_name=push_name,
    )

    return {"status": "queued", "phone": phone}
