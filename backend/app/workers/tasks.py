"""
tasks.py
--------
Tarefas assíncronas do Celery.

Fluxo com debounce:
  1. WhatsApp manda mensagem → Evolution API → webhook FastAPI
  2. FastAPI responde 200 IMEDIATAMENTE
  3. FastAPI acumula texto no Redis e agenda debounce_whatsapp_message (4s de delay)
  4. Se o cliente manda outra mensagem antes dos 4s → reinicia o contador, acumula
  5. Após 4s sem novas mensagens → Celery combina todas e chama process_whatsapp_message
  6. process_whatsapp_message chama o agente Agno (OpenAI)
  7. Aguarda 1-3s (typing delay orgânico) e envia resposta

Resultado: mensagens múltiplas do cliente viram UMA só entrada para o agente.
"""

import logging
import random
import time
import uuid

import redis as redis_lib

from app.config import REDIS_URL
from app.workers.celery_app import celery_app
from app.agent import agent
from app.services.evolution_service import send_text_message, strip_markdown
from app.services.cache_service import get_cached_response, set_cached_response

logger = logging.getLogger(__name__)

# Tempo de espera antes de processar (segundos).
# Se chegarem mensagens dentro deste intervalo, são combinadas em uma só.
DEBOUNCE_SECONDS = 5

# Delay aleatório antes de enviar resposta — simula digitação humana
TYPING_DELAY_MIN = 1.0
TYPING_DELAY_MAX = 3.5


# ─────────────────────────────────────────────────────────────
# Função síncrona chamada pelo webhook — acumula + agenda
# ─────────────────────────────────────────────────────────────

def enqueue_debounced(phone: str, text: str, push_name: str) -> None:
    """
    Chamada diretamente pelo webhook (síncronas, sem Celery).

    1. Adiciona o texto ao buffer Redis do telefone
    2. Gera um novo token (invalida tasks anteriores do mesmo telefone)
    3. Agenda debounce_whatsapp_message com countdown=DEBOUNCE_SECONDS
    """
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)

    list_key  = f"debounce_msgs:{phone}"
    token_key = f"debounce_token:{phone}"

    r.rpush(list_key, text)
    r.expire(list_key, 120)

    token = str(uuid.uuid4())
    r.set(token_key, token, ex=120)

    debounce_whatsapp_message.apply_async(
        kwargs={"phone": phone, "push_name": push_name, "token": token},
        countdown=DEBOUNCE_SECONDS,
    )
    logger.info(f"[Debounce] Mensagem de {phone} acumulada, aguardando {DEBOUNCE_SECONDS}s")


# ─────────────────────────────────────────────────────────────
# Task 1 — Debounce: verifica se é o último token e combina
# ─────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    name="tasks.debounce_whatsapp_message",
)
def debounce_whatsapp_message(self, phone: str, push_name: str, token: str):
    """
    Executada após DEBOUNCE_SECONDS.

    Se um token mais recente existe no Redis (outra mensagem chegou),
    esta task é descartada silenciosamente.
    Caso contrário, combina todas as mensagens acumuladas e processa.
    """
    r = redis_lib.from_url(REDIS_URL, decode_responses=True)

    token_key = f"debounce_token:{phone}"
    list_key  = f"debounce_msgs:{phone}"

    current_token = r.get(token_key)
    if current_token != token:
        logger.info(f"[Debounce] Task superada para {phone}, descartando")
        return {"status": "debounced"}

    # Busca e limpa mensagens acumuladas
    msgs = r.lrange(list_key, 0, -1)
    r.delete(list_key)
    r.delete(token_key)

    if not msgs:
        return {"status": "no_messages"}

    combined_text = "\n".join(msgs)
    n = len(msgs)
    logger.info(
        f"[Debounce] {n} mensagem(ns) combinadas de {phone}: {combined_text[:80]}"
    )

    # Encaminha para o processador real (sem delay adicional)
    process_whatsapp_message.apply_async(
        kwargs={"phone": phone, "text": combined_text, "push_name": push_name},
    )

    return {"status": "forwarded", "messages_batched": n}


# ─────────────────────────────────────────────────────────────
# Task 2 — Processa mensagem(ns) combinadas com o agente
# ─────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=5,
    name="tasks.process_whatsapp_message",
)
def process_whatsapp_message(self, phone: str, text: str, push_name: str = ""):
    """
    Chama o agente Agno (OpenAI) e envia a resposta ao cliente.

    Args:
        phone:     número do remetente
        text:      mensagem (pode ser várias combinadas pelo debounce)
        push_name: nome de exibição do contato
    """
    logger.info(f"[Celery] Processando mensagem de {push_name} ({phone}): {text[:80]}")

    # ─── Verifica cache antes de chamar a OpenAI ──────────
    cached = get_cached_response(phone, text)
    if cached:
        logger.info(f"[Celery] Cache HIT — resposta sem chamar OpenAI")
        try:
            _send_with_typing_delay(phone, cached)
        except Exception as exc:
            raise self.retry(exc=exc, countdown=2 ** self.request.retries)
        return {"phone": phone, "status": "sent_from_cache"}

    # ─── Chama o agente Agno (OpenAI) ─────────────────────
    try:
        response = agent.run(text, session_id=phone)
        reply_text = strip_markdown(response.content)
    except Exception as exc:
        logger.exception(f"[Celery] Erro ao processar mensagem de {phone}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    # Só cacheia respostas válidas (sem erros de schema/tool)
    _error_markers = ("invalid schema", "error code", "bad request", "invalid_request")
    if not any(marker in reply_text.lower() for marker in _error_markers):
        set_cached_response(phone, text, reply_text)

    # ─── Envia com delay orgânico ──────────────────────────
    try:
        _send_with_typing_delay(phone, reply_text)
        logger.info(f"[Celery] Resposta enviada para {phone}")
    except Exception as exc:
        logger.exception(f"[Celery] Erro ao enviar resposta para {phone}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)

    return {"phone": phone, "status": "sent"}


def _send_with_typing_delay(phone: str, text: str) -> None:
    """
    Aguarda um tempo aleatório (simula digitação) antes de enviar.
    Quanto maior o texto, maior o delay máximo — mais natural.
    """
    # Delay base + extra proporcional ao tamanho da resposta
    base_delay  = random.uniform(TYPING_DELAY_MIN, TYPING_DELAY_MAX)
    length_factor = min(len(text) / 500, 1.5)   # até +1.5s para respostas longas
    delay = round(base_delay + length_factor, 1)

    logger.info(f"[TypingDelay] Aguardando {delay}s antes de responder para {phone}")
    time.sleep(delay)
    send_text_message(phone=phone, text=text)


# ─────────────────────────────────────────────────────────────
# Task 3 — Auto-resposta para áudio
# ─────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=2,
    name="tasks.send_audio_autoresponse",
)
def send_audio_autoresponse(self, phone: str):
    """
    Envia auto-resposta quando o usuário manda áudio.
    """
    message = (
        "Che, estoy con la señal cortada y no me llega bien el audio 😅\n"
        "¿Por favor, me mandás por escrito lo que necesitás?"
    )

    logger.info(f"[Celery] Enviando auto-resposta de áudio para {phone}")

    try:
        send_text_message(phone=phone, text=message)
        logger.info(f"[Celery] Auto-resposta de áudio enviada para {phone}")
        return {"phone": phone, "status": "audio_response_sent"}
    except Exception as exc:
        logger.exception(f"[Celery] Erro ao enviar auto-resposta de áudio para {phone}")
        raise self.retry(exc=exc, countdown=2 ** self.request.retries)
