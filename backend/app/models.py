"""
models.py
---------
Definição de todas as tabelas do banco de dados.
"""

from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Text, Boolean, Numeric, DateTime,
    ForeignKey, JSON, UniqueConstraint
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship

Base = declarative_base()


class Contact(Base):
    """
    Tabela de contatos/clientes.
    """
    __tablename__ = 'contact'

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)
    phone = Column(String(20), nullable=False, unique=True, index=True)
    push_name = Column(String(255), nullable=True, comment='Nome do WhatsApp — apenas para logs internos, nunca usado como nome do cliente')
    city = Column(String(100), nullable=True)
    source = Column(
        String(50),
        nullable=False,
        default='inbound_whatsapp',
        comment='planilha_importada, inbound_whatsapp, trafego_pago'
    )
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relacionamentos
    orders = relationship('CustomerOrder', back_populates='contact', cascade='all, delete-orphan')
    conversations = relationship('Conversation', back_populates='contact', cascade='all, delete-orphan')
    broadcast_logs = relationship('BroadcastLog', back_populates='contact', cascade='all, delete-orphan')


class Product(Base):
    """
    Tabela de produtos do catálogo.
    """
    __tablename__ = 'product'

    id = Column(Integer, primary_key=True)
    product_name = Column(String(255), nullable=False, unique=True)
    category = Column(
        String(50),
        nullable=False,
        comment='beer, aperitive, wine, spirit, non_alcoholic, other'
    )
    price = Column(Numeric(10, 2), nullable=False)
    cost_price = Column(Numeric(10, 2), nullable=False)
    alcohol = Column(Boolean, nullable=False, default=True)
    stock_quantity = Column(Integer, nullable=False, default=0)
    is_available = Column(Boolean, nullable=False, default=True)
    description = Column(Text, nullable=True)
    upselling = Column(JSON, nullable=True, comment='Array de nomes de produtos sugeridos')
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)


class CustomerOrder(Base):
    """
    Tabela de pedidos de clientes.
    """
    __tablename__ = 'customer_order'

    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey('contact.id'), nullable=False)
    items = Column(
        JSON,
        nullable=False,
        comment='[{"product_name": str, "quantity": int, "price": float, "subtotal": float}]'
    )
    address = Column(Text, nullable=False)
    total = Column(Numeric(10, 2), nullable=False)
    status = Column(
        String(30),
        nullable=False,
        default='pending',
        comment='pending, waiting_payment_confirm, payment_confirmed, ready, shipped, cancelled'
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relacionamentos
    contact = relationship('Contact', back_populates='orders')
    payment = relationship('Payment', back_populates='order', uselist=False, cascade='all, delete-orphan')


class Payment(Base):
    """
    Tabela de pagamentos via Mercado Pago.
    """
    __tablename__ = 'payment'

    id = Column(Integer, primary_key=True)
    order_id = Column(Integer, ForeignKey('customer_order.id'), nullable=False)
    mp_link = Column(String(500), nullable=True, comment='URL do Checkout Pro do Mercado Pago')
    status = Column(
        String(20),
        nullable=False,
        default='pending',
        comment='pending, approved, rejected, expired'
    )
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relacionamentos
    order = relationship('CustomerOrder', back_populates='payment')


class Conversation(Base):
    """
    Tabela de histórico de conversas por contato.
    """
    __tablename__ = 'conversation'

    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey('contact.id'), nullable=False)
    role = Column(String(20), nullable=False, comment='user, agent')
    content = Column(Text, nullable=False)
    type = Column(String(20), nullable=False, default='text', comment='text, audio, image')
    created_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relacionamentos
    contact = relationship('Contact', back_populates='conversations')


class BroadcastLog(Base):
    """
    Tabela de log de broadcasts/promoções enviadas.
    """
    __tablename__ = 'broadcast_log'

    id = Column(Integer, primary_key=True)
    contact_id = Column(Integer, ForeignKey('contact.id'), nullable=False)
    promotion_id = Column(Integer, ForeignKey('promotion.id'), nullable=True)
    message = Column(Text, nullable=False)
    status = Column(String(20), nullable=False, default='sent', comment='sent, error')
    replied = Column(Boolean, nullable=False, default=False)
    sent_at = Column(DateTime, nullable=False, default=datetime.utcnow)

    # Relacionamentos
    contact = relationship('Contact', back_populates='broadcast_logs')
    promotion = relationship('Promotion', back_populates='broadcast_logs')


class Promotion(Base):
    """
    Tabela de promoções/campanhas.
    """
    __tablename__ = 'promotion'

    id = Column(Integer, primary_key=True)
    title = Column(String(255), nullable=False)
    message_text = Column(Text, nullable=False)
    image_path = Column(String(500), nullable=True)
    total_sent = Column(Integer, nullable=False, default=0)
    total_replied = Column(Integer, nullable=False, default=0)
    scheduled_at = Column(DateTime, nullable=True, comment='Quando agendar o envio')
    sent_at = Column(DateTime, nullable=True, comment='Quando foi efetivamente enviado')

    # Relacionamentos
    broadcast_logs = relationship('BroadcastLog', back_populates='promotion', cascade='all, delete-orphan')


class AgentConfig(Base):
    """
    Tabela de configuração do agente por cliente.
    Permite múltiplos agentes em um único servidor.
    """
    __tablename__ = 'agent_config'

    id = Column(Integer, primary_key=True)
    client_slug = Column(String(50), nullable=False, unique=True, comment='clinica-estetica, jb_bebidas')
    agent_name = Column(String(100), nullable=False)
    system_prompt = Column(Text, nullable=False)
    working_hours = Column(String(255), nullable=True)
    owner_phone = Column(String(20), nullable=True)
    is_active = Column(Boolean, nullable=False, default=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
