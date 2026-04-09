"""
order_commands_service.py
--------------------------
Processa comandos do dono recebidos via WhatsApp.
Lógica determinística — nunca passa pelo agente Agno (LLM).

Comandos suportados:
  CONFIRMAR PAGO [nombre] — confirma que o pagamento entrou
  LISTO [nombre]          — pedido pronto para retiro en local
  ENVIADO [nombre]        — pedido enviado para entrega a domicílio
"""

import re
import logging
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import CustomerOrder, Contact
from app.services.evolution_service import send_text_message

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Parser de comandos do dono
# ─────────────────────────────────────────────────────────────

def parse_owner_command(message: str) -> tuple[str | None, str | None]:
    """
    Extrai o tipo de comando e o nome do cliente de uma mensagem do dono.

    Retorna:
        ("CONFIRMAR PAGO", "Juan")  — para "CONFIRMAR PAGO Juan"
        ("LISTO", "Juan Carlos")    — para "LISTO Juan Carlos"
        ("ENVIADO", "Martín")       — para "ENVIADO Martín"
        (None, None)                — se não for um comando reconhecido
    """
    msg = message.strip()

    # CONFIRMAR PAGO [nombre]
    m = re.match(r'^confirmar\s+pago\s+(.+)$', msg, re.IGNORECASE)
    if m:
        return "CONFIRMAR PAGO", m.group(1).strip()

    # LISTO [nombre]
    m = re.match(r'^listo\s+(.+)$', msg, re.IGNORECASE)
    if m:
        return "LISTO", m.group(1).strip()

    # ENVIADO [nombre]
    m = re.match(r'^enviado\s+(.+)$', msg, re.IGNORECASE)
    if m:
        return "ENVIADO", m.group(1).strip()

    return None, None


# ─────────────────────────────────────────────────────────────
# Helpers internos
# ─────────────────────────────────────────────────────────────

def _find_contact_by_name(db: Session, nombre: str) -> Contact | None:
    """Busca contato pelo nome (substring, case-insensitive)."""
    return db.query(Contact).filter(
        Contact.name.ilike(f"%{nombre}%")
    ).first()


def _find_order_by_contact_and_status(
    db: Session,
    contact_id: int,
    status: str
) -> CustomerOrder | None:
    """Retorna o pedido mais recente do contato com o status especificado."""
    return (
        db.query(CustomerOrder)
        .filter(
            CustomerOrder.contact_id == contact_id,
            CustomerOrder.status == status
        )
        .order_by(CustomerOrder.created_at.desc())
        .first()
    )


def _aviso_pago_nao_confirmado(owner_phone: str, nombre: str) -> None:
    """Avisa o dono que o pago ainda não foi confirmado."""
    msg = (
        f"⚠️ El pago de {nombre} todavía no fue confirmado.\n"
        f"Confirmá primero con CONFIRMAR PAGO {nombre}"
    )
    send_text_message(phone=owner_phone, text=msg)


# ─────────────────────────────────────────────────────────────
# Etapa 2 — CONFIRMAR PAGO [nombre]
# ─────────────────────────────────────────────────────────────

def handle_confirmar_pago(nombre: str, owner_phone: str) -> bool:
    """
    Processa o comando "CONFIRMAR PAGO [nombre]" enviado pelo dono.

    Fluxo:
      1. Busca contato pelo nome no banco
      2. Busca pedido com status 'waiting_payment_confirm'
      3. Atualiza status para 'payment_confirmed'
      4. Notifica o cliente que o pago foi confirmado

    Retorna True se processado com sucesso.
    """
    db = SessionLocal()

    try:
        contact = _find_contact_by_name(db, nombre)

        if not contact:
            send_text_message(
                phone=owner_phone,
                text=(
                    f"⚠️ No encontré ningún cliente con el nombre '{nombre}'.\n"
                    f"Verificá el nombre e intentá de nuevo."
                )
            )
            logger.warning(f"[OwnerCmd] CONFIRMAR PAGO: contato '{nombre}' não encontrado")
            return False

        order = _find_order_by_contact_and_status(db, contact.id, 'waiting_payment_confirm')

        if not order:
            send_text_message(
                phone=owner_phone,
                text=(
                    f"⚠️ No encontré ningún pago pendiente de {contact.name}.\n"
                    f"Verificá que haya mandado el comprobante."
                )
            )
            logger.warning(f"[OwnerCmd] CONFIRMAR PAGO: pedido waiting_payment_confirm não encontrado para {contact.name}")
            return False

        # Atualiza status
        order.status = 'payment_confirmed'
        db.commit()
        logger.info(f"[OwnerCmd] Pedido #{order.id} → payment_confirmed ({contact.name})")

        # Notifica o cliente
        msg_cliente = (
            f"¡Todo bien {contact.name}! Pago confirmado ✅\n"
            f"Ya estamos preparando tu pedido.\n"
            f"Te avisamos cuando esté listo 🙌"
        )
        send_text_message(phone=contact.phone, text=msg_cliente)

        return True

    except Exception:
        logger.exception(f"[OwnerCmd] Erro ao processar CONFIRMAR PAGO '{nombre}'")
        db.rollback()
        return False

    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# Etapa 3 — LISTO [nombre] (retiro en local)
# ─────────────────────────────────────────────────────────────

def handle_listo(nombre: str, owner_phone: str) -> bool:
    """
    Processa o comando "LISTO [nombre]" enviado pelo dono.

    Fluxo:
      1. Verifica que o pedido tem status 'payment_confirmed'
      2. Se não tiver: avisa o dono para confirmar o pago primeiro
      3. Se tiver: atualiza para 'ready' e notifica o cliente

    Retorna True se processado com sucesso.
    """
    db = SessionLocal()

    try:
        contact = _find_contact_by_name(db, nombre)

        if not contact:
            send_text_message(
                phone=owner_phone,
                text=(
                    f"⚠️ No encontré ningún cliente con el nombre '{nombre}'.\n"
                    f"Verificá el nombre e intentá de nuevo."
                )
            )
            logger.warning(f"[OwnerCmd] LISTO: contato '{nombre}' não encontrado")
            return False

        order = _find_order_by_contact_and_status(db, contact.id, 'payment_confirmed')

        if not order:
            # Verifica se o pago está pendente de confirmação
            order_waiting = _find_order_by_contact_and_status(
                db, contact.id, 'waiting_payment_confirm'
            )
            if order_waiting:
                _aviso_pago_nao_confirmado(owner_phone, contact.name)
            else:
                send_text_message(
                    phone=owner_phone,
                    text=(
                        f"⚠️ No encontré ningún pedido confirmado de {contact.name}.\n"
                        f"Verificá el nombre e intentá de nuevo."
                    )
                )
            logger.warning(f"[OwnerCmd] LISTO: pedido payment_confirmed não encontrado para {contact.name}")
            return False

        # Atualiza status
        order.status = 'ready'
        db.commit()
        logger.info(f"[OwnerCmd] Pedido #{order.id} → ready ({contact.name})")

        # Notifica o cliente
        msg_cliente = (
            f"¡{contact.name}, tu pedido está listo! 🎉\n"
            f"Podés pasar a buscarlo cuando quieras. ¡Te esperamos!"
        )
        send_text_message(phone=contact.phone, text=msg_cliente)

        return True

    except Exception:
        logger.exception(f"[OwnerCmd] Erro ao processar LISTO '{nombre}'")
        db.rollback()
        return False

    finally:
        db.close()


# ─────────────────────────────────────────────────────────────
# Etapa 3 — ENVIADO [nombre] (envío a domicílio)
# ─────────────────────────────────────────────────────────────

def handle_enviado(nombre: str, owner_phone: str) -> bool:
    """
    Processa o comando "ENVIADO [nombre]" enviado pelo dono.

    Fluxo:
      1. Verifica que o pedido tem status 'payment_confirmed'
      2. Se não tiver: avisa o dono para confirmar o pago primeiro
      3. Se tiver: atualiza para 'shipped' e notifica o cliente

    Retorna True se processado com sucesso.
    """
    db = SessionLocal()

    try:
        contact = _find_contact_by_name(db, nombre)

        if not contact:
            send_text_message(
                phone=owner_phone,
                text=(
                    f"⚠️ No encontré ningún cliente con el nombre '{nombre}'.\n"
                    f"Verificá el nombre e intentá de nuevo."
                )
            )
            logger.warning(f"[OwnerCmd] ENVIADO: contato '{nombre}' não encontrado")
            return False

        order = _find_order_by_contact_and_status(db, contact.id, 'payment_confirmed')

        if not order:
            # Verifica se o pago está pendente de confirmação
            order_waiting = _find_order_by_contact_and_status(
                db, contact.id, 'waiting_payment_confirm'
            )
            if order_waiting:
                _aviso_pago_nao_confirmado(owner_phone, contact.name)
            else:
                send_text_message(
                    phone=owner_phone,
                    text=(
                        f"⚠️ No encontré ningún pedido confirmado de {contact.name}.\n"
                        f"Verificá el nombre e intentá de nuevo."
                    )
                )
            logger.warning(f"[OwnerCmd] ENVIADO: pedido payment_confirmed não encontrado para {contact.name}")
            return False

        # Atualiza status
        order.status = 'shipped'
        db.commit()
        logger.info(f"[OwnerCmd] Pedido #{order.id} → shipped ({contact.name})")

        # Notifica o cliente
        msg_cliente = (
            f"¡{contact.name}, tu pedido ya está en camino! 🛵\n"
            f"En breve llega. Cualquier cosa avisame 😊"
        )
        send_text_message(phone=contact.phone, text=msg_cliente)

        return True

    except Exception:
        logger.exception(f"[OwnerCmd] Erro ao processar ENVIADO '{nombre}'")
        db.rollback()
        return False

    finally:
        db.close()
