"""
payment_service.py
------------------
Integração com Mercado Pago para geração de links de pagamento.
Cria Checkout Pro links para pedidos e webhook para confirmação de pagamento.
"""

import logging
import hmac
import hashlib
from typing import Optional
import mercadopago
from sqlalchemy.orm import Session
from app.config import OPENAI_API_KEY
from app.models import CustomerOrder, Payment, Contact
from app.services.evolution_service import send_text_message

logger = logging.getLogger(__name__)


class PaymentService:
    """
    Gerencia pagamentos via Mercado Pago.
    """

    def __init__(self, mp_access_token: str):
        """
        Inicializa o cliente Mercado Pago.

        Args:
            mp_access_token: chave de acesso do Mercado Pago
        """
        self.sdk = mercadopago.SDK(mp_access_token)

    def generate_checkout_link(self, order_id: int, db: Session) -> tuple[Optional[str], str]:
        """
        Gera um link de Checkout Pro para um pedido.

        Args:
            order_id: ID do pedido
            db: sessão SQLAlchemy

        Returns:
            (link_url, error_message) ou (url, "") se sucesso
        """
        order = db.query(CustomerOrder).filter(CustomerOrder.id == order_id).first()
        if not order:
            return None, "Pedido no encontrado"

        contact = order.contact

        try:
            # Formata items para Mercado Pago
            items = []
            for item in order.items:
                items.append({
                    "title": item['product_name'],
                    "quantity": item['quantity'],
                    "unit_price": float(item['price'])
                })

            # Cria preferência de pagamento
            preference_data = {
                "items": items,
                "payer": {
                    "name": contact.name,
                    "phone": {
                        "number": contact.phone.replace("+54", "")  # remove código país
                    }
                },
                "back_urls": {
                    "success": "https://seu-dominio.com/pago/sucesso",
                    "failure": "https://seu-dominio.com/pago/falha",
                    "pending": "https://seu-dominio.com/pago/pendente"
                },
                "auto_return": "approved",
                "external_reference": f"order_{order_id}",
                "expires": True,
                "expiration_date_to": "2024-12-31T23:59:59Z"
            }

            # Cria a preferência
            preference_response = self.sdk.preference().create(preference_data)

            if preference_response["status"] == 201:
                checkout_url = preference_response["response"]["init_point"]

                # Salva o link no banco
                payment = Payment(
                    order_id=order_id,
                    mp_link=checkout_url,
                    status='pending'
                )
                db.add(payment)
                db.commit()

                logger.info(f"Link de pagamento gerado para pedido #{order_id}")
                return checkout_url, ""
            else:
                error = preference_response.get("message", "Error desconocido")
                logger.error(f"Erro ao gerar link: {error}")
                return None, f"Error al generar link de pago: {error}"

        except Exception as e:
            logger.exception(f"Exception ao gerar link para pedido #{order_id}")
            return None, f"Error técnico: {str(e)}"

    def send_payment_link_to_customer(self, phone: str, checkout_url: str) -> bool:
        """
        Envia o link de pagamento para o cliente via WhatsApp.

        Args:
            phone: número do cliente
            checkout_url: URL do Checkout Pro

        Returns:
            True se enviado com sucesso
        """
        message = (
            f"Dale! Acá te mando el link para que cierres el pago: {checkout_url} ⚡\n"
            f"Válido por 24hs."
        )

        try:
            send_text_message(phone=phone, text=message)
            logger.info(f"Link de pagamento enviado para {phone}")
            return True
        except Exception as e:
            logger.exception(f"Erro ao enviar link de pagamento para {phone}")
            return False

    def handle_payment_approved(
        self,
        order_id: int,
        db: Session,
        owner_phone: Optional[str] = None
    ) -> bool:
        """
        Processa um pagamento aprovado.

        1. Atualiza order.status para 'paid'
        2. Envia confirmação ao cliente
        3. Notifica o dono (opcional)

        Args:
            order_id: ID do pedido
            db: sessão SQLAlchemy
            owner_phone: telefone do dono para notificação

        Returns:
            True se processado com sucesso
        """
        order = db.query(CustomerOrder).filter(CustomerOrder.id == order_id).first()
        if not order:
            logger.warning(f"Pedido #{order_id} não encontrado para confirmação de pagamento")
            return False

        contact = order.contact

        try:
            # Atualiza status
            payment = db.query(Payment).filter(Payment.order_id == order_id).first()
            if payment:
                payment.status = 'approved'
                db.add(payment)

            order.status = 'paid'
            db.add(order)
            db.commit()

            # Notifica cliente
            customer_message = (
                "¡Listo! Pago confirmado ✅\n"
                "Tu pedido está en preparación.\n"
                "Te avisamos cuando salga.\n\n"
                "Muchas gracias por elegirnos 🍻"
            )
            try:
                send_text_message(phone=contact.phone, text=customer_message)
            except Exception as e:
                logger.warning(f"Erro ao enviar confirmação para cliente: {e}")

            # Notifica dono
            if owner_phone:
                owner_message = (
                    f"📦 *PAGO CONFIRMADO - PEDIDO #{order_id}*\n"
                    f"Cliente: {contact.name} ({contact.phone})\n"
                    f"Total: ${order.total}\n"
                    f"Status: Listo para preparar"
                )
                try:
                    send_text_message(phone=owner_phone, text=owner_message)
                except Exception as e:
                    logger.warning(f"Erro ao notificar dono: {e}")

            logger.info(f"Pagamento do pedido #{order_id} confirmado e cliente notificado")
            return True

        except Exception as e:
            logger.exception(f"Erro ao processar pagamento aprovado do pedido #{order_id}")
            return False

    def handle_payment_rejected(
        self,
        order_id: int,
        db: Session,
        reason: str = "desconocido"
    ) -> bool:
        """
        Processa um pagamento rejeitado.

        Notifica cliente em espanhol argentino.
        """
        order = db.query(CustomerOrder).filter(CustomerOrder.id == order_id).first()
        if not order:
            return False

        contact = order.contact

        try:
            payment = db.query(Payment).filter(Payment.order_id == order_id).first()
            if payment:
                payment.status = 'rejected'
                db.add(payment)
                db.commit()

            message = (
                f"Che, el pago fue rechazado 😞\n"
                f"Razón: {reason}\n\n"
                f"Probá con otra tarjeta o contactáme si tenés problemas.\n"
                f"El pedido sigue en espera."
            )
            try:
                send_text_message(phone=contact.phone, text=message)
            except Exception:
                logger.exception(f"Erro ao notificar rejeição ao cliente {contact.phone}")

            logger.info(f"Pagamento do pedido #{order_id} rejeitado")
            return True

        except Exception as e:
            logger.exception(f"Erro ao processar rejeição de pagamento")
            return False

    def handle_payment_expired(
        self,
        order_id: int,
        db: Session
    ) -> bool:
        """
        Processa um pagamento expirado (não foi realizado em 24hs).

        Notifica cliente e cancela o pedido.
        """
        order = db.query(CustomerOrder).filter(CustomerOrder.id == order_id).first()
        if not order:
            return False

        contact = order.contact

        try:
            payment = db.query(Payment).filter(Payment.order_id == order_id).first()
            if payment:
                payment.status = 'expired'
                db.add(payment)

            order.status = 'cancelled'
            db.add(order)
            db.commit()

            message = (
                "El link de pago expiró 😞\n"
                "Si todavía querés hacer el pedido, te mando uno nuevo.\n"
                "¿Dale?"
            )
            try:
                send_text_message(phone=contact.phone, text=message)
            except Exception:
                logger.exception(f"Erro ao notificar expiração ao cliente")

            logger.info(f"Pagamento do pedido #{order_id} expirado e pedido cancelado")
            return True

        except Exception as e:
            logger.exception(f"Erro ao processar pagamento expirado")
            return False

    @staticmethod
    def verify_webhook_signature(
        request_id: str,
        timestamp: str,
        signature: str,
        webhook_secret: str
    ) -> bool:
        """
        Verifica a assinatura do webhook do Mercado Pago.

        Mercado Pago envia:
            X-Request-ID: id único
            X-Request-Timestamp: timestamp
            X-Signature: hmac-sha256(secret + id + timestamp, secret)

        Args:
            request_id: header X-Request-ID
            timestamp: header X-Request-Timestamp
            signature: header X-Signature
            webhook_secret: chave secreta do webhook (do Mercado Pago)

        Returns:
            True se assinatura é válida
        """
        try:
            msg = f"id={request_id};ts={timestamp}"
            expected_signature = hmac.new(
                webhook_secret.encode(),
                msg.encode(),
                hashlib.sha256
            ).hexdigest()

            return hmac.compare_digest(signature, expected_signature)

        except Exception as e:
            logger.exception(f"Erro ao verificar assinatura webhook: {e}")
            return False
