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
from app.company_config import config as client_config

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# Efectivo — notificação ao dono quando pedido é confirmado
# ─────────────────────────────────────────────────────────────

def handle_efectivo_order(contact_id: int, order_id: int) -> bool:
    """
    Processa pedido pago em efectivo:
      a) Atualiza status do pedido para 'payment_confirmed'
      b) Envia notificação a todos os owner_phones configurados

    Chamado por agent_tools.confirmar_pedido quando payment_method='efectivo'.

    Retorna True se processado com sucesso.
    """
    # Obtém phones dos donos da config
    owner_phones = client_config.get("owner_phone", [])
    if isinstance(owner_phones, str):
        owner_phones = [owner_phones] if owner_phones else []

    if not owner_phones:
        logger.warning("[EfectivoOrder] Nenhum owner_phone configurado — notificação não enviada")
        return False

    db = SessionLocal()
    try:
        contact = db.query(Contact).filter(Contact.id == contact_id).first()
        order   = db.query(CustomerOrder).filter(CustomerOrder.id == order_id).first()

        if not contact or not order:
            logger.error(f"[EfectivoOrder] Contato ou pedido não encontrado: contact_id={contact_id}, order_id={order_id}")
            return False

        # Atualiza status para payment_confirmed
        order.status = 'payment_confirmed'
        db.commit()
        logger.info(f"[EfectivoOrder] Pedido #{order.id} → payment_confirmed (efectivo)")

        # Formata itens do pedido
        items_lines = "\n".join([
            f"{item.get('product_name', 'Producto')} x{item.get('quantity', 1)} = ${int(item.get('subtotal', 0)):,}".replace(",", ".")
            for item in (order.items or [])
        ])
        total_fmt = f"${int(float(order.total)):,}".replace(",", ".")

        msg = (
            f"🛒 NUEVO PEDIDO - EFECTIVO\n"
            f"Cliente: {contact.name} ({contact.phone})\n"
            f"─────────────────\n"
            f"{items_lines}\n"
            f"─────────────────\n"
            f"Total: {total_fmt}\n"
            f"Retiro en local 📦\n"
            f"─────────────────\n"
            f"Respondé: LISTO {contact.name}\n"
            f"cuando esté preparado para que pase a buscar"
        )

        for phone in owner_phones:
            try:
                send_text_message(phone=str(phone), text=msg)
                logger.info(f"[EfectivoOrder] Notificación enviada al dueño {phone}")
            except Exception as e:
                logger.error(f"[EfectivoOrder] Erro ao notificar dueño {phone}: {e}")

        return True

    except Exception:
        logger.exception(f"[EfectivoOrder] Erro ao processar pedido efectivo order_id={order_id}")
        db.rollback()
        return False

    finally:
        db.close()


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
