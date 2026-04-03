"""
tasks.py
--------
Tarefas assíncronas do Celery.

Fluxo completo com Celery:
  1. WhatsApp manda mensagem → Evolution API
  2. Evolution API faz POST no webhook FastAPI
  3. FastAPI responde 200 IMEDIATAMENTE (não bloqueia)
  4. FastAPI enfileira a tarefa: process_whatsapp_message.delay(...)
  5. Celery Worker pega a tarefa da fila Redis
  6. Worker chama a Sofia (OpenAI)
  7. Worker envia resposta via Evolution API

Vantagem: o webhook nunca trava, mesmo que a OpenAI demore 10s.
"""

import logging
from app.workers.celery_app import celery_app
from app.agent import sofia
from app.services.evolution_service import send_text_message, strip_markdown
from app.services.cache_service import get_cached_response, set_cached_response

logger = logging.getLogger(__name__)


@celery_app.task(
    bind=True,
    max_retries=3,           # tenta 3x antes de desistir
    default_retry_delay=5,   # aguarda 5s entre tentativas
    name="tasks.process_whatsapp_message",
)
def process_whatsapp_message(self, phone: str, text: str, push_name: str = ""):
    """
    Processa uma mensagem WhatsApp recebida de forma assíncrona.

    Args:
        phone:     número do remetente (ex: "5511999990000")
        text:      conteúdo da mensagem
        push_name: nome de exibição do contato no WhatsApp
    """
    logger.info(f"[Celery] Processando mensagem de {push_name} ({phone}): {text[:80]}")

    # ─── Fase 4: verifica cache antes de chamar a OpenAI ───
    cached = get_cached_response(phone, text)
    if cached:
        logger.info(f"[Celery] Cache HIT — resposta sem chamar OpenAI")
        try:
            send_text_message(phone=phone, text=cached)
        except Exception as exc:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        return {"phone": phone, "status": "sent_from_cache"}

    # ─── Chama a Sofia (OpenAI) ────────────────────────────
    try:
        response = sofia.run(text, session_id=phone)
        reply_text = strip_markdown(response.content)
    except Exception as exc:
        logger.exception(f"[Celery] Erro ao processar mensagem de {phone}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    # Armazena no cache para próximas mensagens idênticas
    set_cached_response(phone, text, reply_text)

    # ─── Envia resposta via Evolution API ─────────────────
    try:
        send_text_message(phone=phone, text=reply_text)
        logger.info(f"[Celery] Resposta enviada para {phone}")
    except Exception as exc:
        logger.exception(f"[Celery] Erro ao enviar resposta para {phone}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    return {"phone": phone, "status": "sent"}
