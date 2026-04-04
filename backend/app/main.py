"""
main.py
-------
Aplicação FastAPI principal.
Integra webhooks WhatsApp, endpoints de chat, e webhooks de pagamento.
"""

import logging
import uuid
import os
from typing import Optional
from pydantic import BaseModel
from fastapi import Request, HTTPException
from agno.os import AgentOS
from app.agent import agent
from app.routers.whatsapp_router import router as whatsapp_router
from app.services.payment_service import PaymentService
from app.database import SessionLocal
from app.models import CustomerOrder

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# AgentOS cria o app FastAPI com todas as rotas do Agno (incluindo /agui)
agent_os = AgentOS(agents=[agent], cors_allowed_origins=["http://localhost:3000"])
app = agent_os.get_app()

# Registra o webhook do WhatsApp
app.include_router(whatsapp_router)


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


# -------------------------------------------------------------------
# Webhooks de Mercado Pago
# -------------------------------------------------------------------

@app.post("/webhooks/mercadopago")
async def mercadopago_webhook(request: Request):
    """
    Webhook do Mercado Pago para notificações de pagamento.

    Fluxo:
    1. Cliente clica no link de pagamento
    2. Cliente realiza pagamento no Mercado Pago
    3. Mercado Pago notifica este endpoint
    4. Atualiza status do pedido no banco
    5. Envia confirmação ao cliente

    Headers esperados:
    - X-Request-ID: id único da requisição
    - X-Request-Timestamp: timestamp
    - X-Signature: hmac-sha256 assinado

    Body esperado:
    {
        "action": "payment.created" ou "payment.updated",
        "data": {
            "id": "123456789",
            "status": "approved" | "rejected" | "pending",
            "external_reference": "order_123"
        }
    }
    """
    try:
        payload = await request.json()
    except Exception as e:
        logger.error(f"[MercadoPago] Erro ao parsear webhook: {e}")
        raise HTTPException(status_code=400, detail="Payload inválido")

    # Extrai headers
    request_id = request.headers.get("X-Request-ID", "")
    timestamp = request.headers.get("X-Request-Timestamp", "")
    signature = request.headers.get("X-Signature", "")
    webhook_secret = os.getenv("MERCADOPAGO_WEBHOOK_SECRET", "")

    logger.info(f"[MercadoPago] Webhook recebido: action={payload.get('action')}")

    # Valida assinatura se secret estiver configurado
    if webhook_secret:
        mp_service = PaymentService(os.getenv("MERCADOPAGO_ACCESS_TOKEN", ""))
        if not mp_service.verify_webhook_signature(request_id, timestamp, signature, webhook_secret):
            logger.warning("[MercadoPago] Assinatura inválida — rejeitando webhook")
            raise HTTPException(status_code=401, detail="Assinatura inválida")

    # Processa notificação
    action = payload.get("action", "")
    data = payload.get("data", {})
    payment_id = data.get("id")
    payment_status = data.get("status", "")
    external_ref = data.get("external_reference", "")

    if not external_ref or not external_ref.startswith("order_"):
        logger.warning(f"[MercadoPago] external_reference inválida: {external_ref}")
        return {"status": "ignored", "reason": "invalid_reference"}

    # Extrai order_id
    try:
        order_id = int(external_ref.replace("order_", ""))
    except Exception:
        return {"status": "ignored", "reason": "invalid_order_id"}

    db = SessionLocal()
    mp_service = PaymentService(os.getenv("MERCADOPAGO_ACCESS_TOKEN", ""))
    owner_phone = os.getenv("OWNER_PHONE", "")  # opcional

    try:
        # Processa baseado no status do pagamento
        if payment_status == "approved":
            logger.info(f"[MercadoPago] Pagamento aprovado para order_id={order_id}")
            mp_service.handle_payment_approved(order_id, db, owner_phone)

        elif payment_status == "rejected":
            reason = data.get("reason", "desconocido")
            logger.info(f"[MercadoPago] Pagamento rejeitado para order_id={order_id}: {reason}")
            mp_service.handle_payment_rejected(order_id, db, reason)

        elif payment_status == "expired":
            logger.info(f"[MercadoPago] Pagamento expirado para order_id={order_id}")
            mp_service.handle_payment_expired(order_id, db)

        elif payment_status == "pending":
            logger.info(f"[MercadoPago] Pagamento pendente para order_id={order_id}")
            # Pode enviar lembretes periodicamente

        return {"status": "processed", "order_id": order_id}

    except Exception as e:
        logger.exception(f"[MercadoPago] Erro ao processar webhook para order_id={order_id}")
        db.rollback()
        return {"status": "error", "message": str(e)}

    finally:
        db.close()
