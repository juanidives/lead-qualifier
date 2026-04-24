"""
agent_tools.py
--------------
Ferramentas Python disponíveis para o agente Agno (Juani).

O Agno passa automaticamente `run_context` às funções que o declaram como
primeiro parâmetro. `run_context.session_id` contém o número de telefone do
cliente atual, que usamos para associar o pedido ao contato no banco.

Nota de schema: a OpenAI exige que arrays no schema de tools tenham um campo
`items` definindo o tipo dos elementos. Para evitar esse problema, o parâmetro
de itens é recebido como string JSON e parseado internamente.

Como registrar uma nova tool:
  1. Defina a função com docstring clara (o LLM usa para decidir quando chamar)
  2. Adicione-a à lista `tools` em app/agent.py
  3. Adicione instrução no prompt (prompts/beverages.py) quando e como chamá-la
"""

import json
import logging
from decimal import Decimal

from agno.run import RunContext

from app.database import SessionLocal
from app.models import Contact, CustomerOrder
from app.company_config import config as client_config

logger = logging.getLogger(__name__)


def confirmar_pedido(
    run_context: RunContext,
    items_json: str,
    total: float,
    address: str,
    payment_method: str = "transferencia",
) -> str:
    """
    Guarda el pedido del cliente en la base de datos cuando confirma la compra.

    Llamá esta función UNA SOLA VEZ cuando el cliente confirme todos los
    productos, cantidades y la forma de entrega. El comportamiento varía
    según la forma de pago:

    - payment_method="transferencia" (default): pedido queda en estado
      'pending', esperando el comprobante. Llamá ANTES de enviar el alias.
      La función devuelve el alias de pago para que lo comuniques al cliente.
    - payment_method="efectivo": notifica al dueño automáticamente y devuelve
      mensaje de confirmación para enviar al cliente. Llamá SOLO cuando
      el cliente confirme explícitamente.

    Args:
        items_json: JSON string con la lista de productos del pedido.
                    Cada objeto debe tener: product_name (str), quantity (int),
                    price (float) y subtotal (float).
                    Ejemplo:
                    '[{"product_name":"Fernet 750ml - Branca","quantity":1,"price":16000,"subtotal":16000},{"product_name":"Coca-Cola 2.25L","quantity":2,"price":4500,"subtotal":9000}]'
        total:      Monto total del pedido en ARS. Ejemplo: 25000
        address:    Dirección de entrega completa, o la palabra "retiro" si el
                    cliente pasa a buscar al local.
                    Ejemplo: "Av. Sarmiento 400" o "retiro"
        payment_method: Forma de pago. Valores válidos: "transferencia" o "efectivo".

    Returns:
        Para transferencia: el alias de pago para comunicar al cliente.
        Para efectivo: mensaje de confirmación para enviar al cliente.
        En caso de error: string que empieza con "error:".
    """
    phone = run_context.session_id

    if not phone:
        logger.error("[AgentTool] confirmar_pedido: session_id (phone) vacío en RunContext")
        return "error: phone no disponible"

    # Parsea la lista de items desde el JSON string
    try:
        items = json.loads(items_json)
        if not isinstance(items, list):
            raise ValueError("items_json debe ser un array JSON")
    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f"[AgentTool] confirmar_pedido: items_json inválido — {e}")
        return f"error: items_json inválido ({e})"

    is_efectivo = payment_method.lower().strip() == "efectivo"

    db = SessionLocal()
    try:
        # ── 1. Busca el contacto por teléfono ─────────────────────────
        contact = db.query(Contact).filter(Contact.phone == phone).first()

        if not contact:
            logger.warning(f"[AgentTool] confirmar_pedido: contacto no encontrado para {phone}")
            return "error: cliente no encontrado en BD"

        # ── 2. Cancela pedidos 'pending' anteriores del mismo contacto ─
        #       (evita duplicados si el cliente cambia el pedido)
        old_orders = (
            db.query(CustomerOrder)
            .filter(
                CustomerOrder.contact_id == contact.id,
                CustomerOrder.status == 'pending',
            )
            .all()
        )
        for old in old_orders:
            old.status = 'cancelled'
            logger.info(f"[AgentTool] Pedido #{old.id} anterior → cancelado (reemplazado)")

        # ── 3. Crea el nuevo pedido siempre con status 'pending' ──────
        order = CustomerOrder(
            contact_id=contact.id,
            items=items,
            address=address or "—",
            total=Decimal(str(round(total, 2))),
            status='pending',
        )
        db.add(order)
        db.commit()
        db.refresh(order)

        logger.info(
            f"[AgentTool] Pedido #{order.id} guardado — "
            f"contacto: {contact.name} | pago: {payment_method} | "
            f"status: pending | items: {len(items)} | "
            f"total: ${total} | dirección: {address}"
        )

        # ── 4. Flujo según forma de pago ──────────────────────────────

        if is_efectivo:
            # Notifica al dueño y actualiza status a 'payment_confirmed'
            # Import lazy para evitar circular imports
            from app.services.order_commands_service import handle_efectivo_order
            handle_efectivo_order(contact_id=contact.id, order_id=order.id)

            return (
                "¡Perfecto! Pedido confirmado ✅ "
                "Lo estamos preparando para que lo pases a buscar. "
                "Te avisamos cuando esté listo 🙌"
            )

        else:
            # Transferencia: devuelve el alias para que el agente lo comunique
            payment_alias = client_config.get("payment_alias", "").strip()
            alias_text = f"*{payment_alias}*" if payment_alias else "[alias no configurado]"
            return f"ok: pedido #{order.id} guardado. Alias para transferencia: {alias_text}"

    except Exception:
        logger.exception(f"[AgentTool] Error al guardar pedido para {phone}")
        db.rollback()
        return "error interno al guardar pedido"

    finally:
        db.close()
