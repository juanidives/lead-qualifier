"""
payment_service.py
------------------
REMOVIDO: integração com Mercado Pago.

O cliente JB Bebidas usa transferência bancária com alias.
O fluxo de pagamento é gerenciado por:
  - whatsapp_router.py    — detecção de comprovante + notificação ao dono
  - order_commands_service.py — comandos do dono (CONFIRMAR PAGO, LISTO, ENVIADO)
"""
