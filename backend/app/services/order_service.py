"""
order_service.py
----------------
Serviço para gerenciar pedidos de clientes.
Detecta intenção de compra, valida estoque, salva pedido e gerencia alteração de estoque.
"""

import logging
import json
from datetime import datetime
from typing import Optional, List, Dict
from decimal import Decimal
from sqlalchemy.orm import Session
from app.models import CustomerOrder, Product, Contact

logger = logging.getLogger(__name__)


class OrderService:
    """
    Gerencia todo o fluxo de vendas: detecção de intenção, validação de estoque,
    confirmação e finalização.
    """

    def __init__(self, db: Session):
        self.db = db

    def detect_purchase_intent(self, message: str) -> bool:
        """
        Detecta se a mensagem contém intenção de compra.

        Palavras-chave:
        - "Quiero", "Necesito", "Dale", "Confirmá", "Me pones"
        - "Pedido", "Compro", "Llevo"
        """
        purchase_keywords = [
            'quiero', 'necesito', 'dale', 'confirma', 'me pones',
            'pedido', 'compro', 'llevo', 'dame', 'traeme',
            'cuanto vale', 'cuanto sale', 'precio'
        ]

        message_lower = message.lower().strip()
        return any(keyword in message_lower for keyword in purchase_keywords)

    def get_product_by_name(self, product_name: str) -> Optional[Product]:
        """
        Busca um produto pelo nome (case-insensitive).
        """
        return self.db.query(Product).filter(
            Product.product_name.ilike(f"%{product_name}%")
        ).first()

    def check_availability(self, product_name: str, quantity: int = 1) -> tuple[bool, str]:
        """
        Valida se um produto está disponível e tem estoque suficiente.

        Returns:
            (disponível, mensagem_descritiva)
        """
        product = self.get_product_by_name(product_name)

        if not product:
            return False, f"Che, ese producto no existe 😅 ¿Otra cosa?"

        if not product.is_available:
            # Sugere upselling
            upselling = product.upselling or []
            suggestion = ""
            if upselling:
                suggestion = f" ¿Te puedo ofrecer {upselling[0]}?"
            return False, f"Che, ese producto se nos terminó por ahora 😅{suggestion}"

        if product.stock_quantity < quantity:
            return False, (
                f"Tenemos solo {product.stock_quantity} en stock. "
                f"¿Te va esa cantidad o prefers otra cosa?"
            )

        return True, ""

    def create_order_draft(
        self,
        contact_id: int,
        items: List[Dict[str, any]],
        address: str
    ) -> CustomerOrder:
        """
        Cria um rascunho de pedido (status=pending).

        Args:
            contact_id: ID do contato/cliente
            items: lista de itens com {product_name, quantity}
            address: endereço de entrega

        Returns:
            CustomerOrder (salvo no banco)
        """
        # Calcula total e formata items com preços
        formatted_items = []
        total = Decimal('0')

        for item in items:
            product = self.get_product_by_name(item['product_name'])
            if not product:
                logger.warning(f"Produto não encontrado: {item['product_name']}")
                continue

            quantity = item.get('quantity', 1)
            subtotal = product.price * Decimal(quantity)
            total += subtotal

            formatted_items.append({
                'product_name': product.product_name,
                'quantity': quantity,
                'price': float(product.price),
                'subtotal': float(subtotal),
                'product_id': product.id
            })

        order = CustomerOrder(
            contact_id=contact_id,
            items=formatted_items,
            address=address,
            total=total,
            status='pending'
        )

        self.db.add(order)
        self.db.commit()
        self.db.refresh(order)

        logger.info(f"Pedido criado: #{order.id} para contato {contact_id} - Total: ${total}")
        return order

    def confirm_order(self, order_id: int) -> tuple[bool, str]:
        """
        Confirma um pedido e desconta do estoque.

        Regras:
        - Se stock_quantity cair para 0, is_available muda para False
        - Atualiza order.status para 'paid' (pronto para preparação)

        Returns:
            (sucesso, mensagem)
        """
        order = self.db.query(CustomerOrder).filter(CustomerOrder.id == order_id).first()
        if not order:
            return False, "Pedido no encontrado"

        try:
            # Processa cada item do pedido
            for item in order.items:
                product = self.db.query(Product).filter(
                    Product.id == item['product_id']
                ).first()

                if not product:
                    logger.warning(f"Produto #{item['product_id']} não encontrado ao confirmar")
                    continue

                # Desconta do estoque
                product.stock_quantity -= item['quantity']

                # Se zerou o estoque, marca como indisponível
                if product.stock_quantity <= 0:
                    product.is_available = False
                    product.stock_quantity = 0

                self.db.add(product)

            # Marca pedido como confirmado
            order.status = 'paid'
            self.db.add(order)
            self.db.commit()

            logger.info(f"Pedido #{order.id} confirmado e estoque atualizado")
            return True, ""

        except Exception as e:
            self.db.rollback()
            logger.exception(f"Erro ao confirmar pedido #{order_id}")
            return False, f"Erro ao confirmar: {str(e)}"

    def cancel_order(self, order_id: int) -> bool:
        """
        Cancela um pedido.
        """
        order = self.db.query(CustomerOrder).filter(CustomerOrder.id == order_id).first()
        if order:
            order.status = 'cancelled'
            self.db.add(order)
            self.db.commit()
            logger.info(f"Pedido #{order_id} cancelado")
            return True
        return False

    def get_order_summary(self, order_id: int) -> str:
        """
        Gera um resumo formatado do pedido para confirmação do cliente.

        Exemplo:
            Acá va tu pedido:
            - Quilmes Clásica 1L x2 = $1700
            - Fernet Branca 750ml x1 = $4500
            ─────────────────────
            Total: $6200

            Confirmás que queres seguir adelante? Dale o "Cancelar"
        """
        order = self.db.query(CustomerOrder).filter(CustomerOrder.id == order_id).first()
        if not order:
            return ""

        summary = "Acá va tu pedido:\n"
        for item in order.items:
            summary += (
                f"- {item['product_name']} x{item['quantity']} "
                f"= ${item['subtotal']:.0f}\n"
            )

        summary += f"─────────────────────\n"
        summary += f"Total: ${order.total}\n"
        summary += f"Dirección: {order.address}\n\n"
        summary += "¿Confirmás que queres este pedido? Dale o 'Cancelar'"

        return summary

    def get_order_confirmation_message(self, order_id: int) -> str:
        """
        Mensagem de confirmação enviada ao cliente após pagamento.
        """
        order = self.db.query(CustomerOrder).filter(CustomerOrder.id == order_id).first()
        if not order:
            return ""

        return (
            f"¡Listo! Pago confirmado ✅\n"
            f"Tu pedido está en preparación.\n"
            f"Te avisamos cuando salga.\n\n"
            f"Muchas gracias por elegirnos 🍻"
        )

    def get_order_notification_for_owner(self, order_id: int, owner_phone: str) -> str:
        """
        Mensagem para notificar o dono do negócio sobre novo pedido.
        """
        order = self.db.query(CustomerOrder).filter(CustomerOrder.id == order_id).first()
        if not order:
            return ""

        contact = order.contact

        items_text = "\n".join([
            f"- {item['product_name']} x{item['quantity']} = ${item['subtotal']:.0f}"
            for item in order.items
        ])

        return (
            f"📦 *NUEVO PEDIDO #{order.id}*\n"
            f"Cliente: {contact.name} ({contact.phone})\n"
            f"Dirección: {order.address}\n"
            f"Ciudad: {contact.city}\n\n"
            f"*Items:*\n{items_text}\n\n"
            f"*Total:* ${order.total}\n"
            f"*Estado:* {order.status}\n"
            f"*Creado:* {order.created_at.strftime('%d/%m/%Y %H:%M')}"
        )
