"""
cache_service.py
----------------
Cache semântico usando Redis.

Objetivo: evitar chamar a OpenAI quando a mesma pergunta
(ou uma semanticamente muito similar) já foi respondida recentemente.

Nível 1 — Cache exato (implementado aqui):
  Usa hash MD5 da mensagem normalizada como chave Redis.
  TTL de 1 hora. Gratuito, zero dependências extras.

Nível 2 — Cache semântico (comentado, requer Redis Stack):
  Usa embeddings + busca vetorial para achar respostas similares.
  Requer: pip install redisvl sentence-transformers
  Requer: imagem redis/redis-stack no docker-compose

Como usar no tasks.py:
  from app.services.cache_service import get_cached_response, set_cached_response

  cached = get_cached_response(phone, message)
  if cached:
      send_text_message(phone, cached)
      return

  response = sofia.run(message, session_id=phone)
  set_cached_response(phone, message, response.content)
"""

import hashlib
import logging
import redis as redis_lib

from app.config import REDIS_URL

logger = logging.getLogger(__name__)

# TTL padrão do cache: 1 hora
CACHE_TTL_SECONDS = 3600

# Prefixo das chaves no Redis
CACHE_PREFIX = "chat_cache"


def _get_redis_client() -> redis_lib.Redis:
    return redis_lib.from_url(REDIS_URL, decode_responses=True)


def _build_cache_key(phone: str, message: str) -> str:
    """
    Gera uma chave única baseada no número + mensagem normalizada.
    Normaliza: lowercase, sem espaços extras.
    """
    normalized = message.lower().strip()
    message_hash = hashlib.md5(normalized.encode()).hexdigest()
    return f"{CACHE_PREFIX}:{phone}:{message_hash}"


def get_cached_response(phone: str, message: str) -> str | None:
    """
    Busca resposta em cache para a mensagem deste contato.
    Retorna None se não encontrar ou se Redis estiver indisponível.
    """
    try:
        client = _get_redis_client()
        key = _build_cache_key(phone, message)
        cached = client.get(key)
        if cached:
            logger.info(f"[Cache] HIT para {phone}: {message[:40]}")
        return cached
    except Exception:
        logger.warning("[Cache] Redis indisponível — continuando sem cache")
        return None


def set_cached_response(phone: str, message: str, response: str) -> None:
    """
    Armazena resposta no cache com TTL de 1 hora.
    Falha silenciosamente se Redis estiver indisponível.
    """
    try:
        client = _get_redis_client()
        key = _build_cache_key(phone, message)
        client.setex(key, CACHE_TTL_SECONDS, response)
        logger.info(f"[Cache] SET para {phone}: {message[:40]}")
    except Exception:
        logger.warning("[Cache] Redis indisponível — resposta não cacheada")


# ─────────────────────────────────────────────────────────────────
# NÍVEL 2 — Cache semântico com embeddings (requer Redis Stack)
# Descomente e instale: pip install redisvl sentence-transformers
# Troque a imagem Redis no docker-compose por: redis/redis-stack:latest
# ─────────────────────────────────────────────────────────────────

# from redisvl.extensions.llmcache import SemanticCache
#
# _semantic_cache: SemanticCache | None = None
#
# def get_semantic_cache() -> SemanticCache:
#     global _semantic_cache
#     if _semantic_cache is None:
#         _semantic_cache = SemanticCache(
#             name="lead_qualifier_cache",
#             redis_url=REDIS_URL,
#             distance_threshold=0.15,  # similaridade mínima (0=idêntico, 1=oposto)
#         )
#     return _semantic_cache
#
# def get_semantic_cached_response(message: str) -> str | None:
#     try:
#         cache = get_semantic_cache()
#         results = cache.check(prompt=message)
#         if results:
#             logger.info(f"[Cache Semântico] HIT: {message[:40]}")
#             return results[0]["response"]
#     except Exception:
#         logger.warning("[Cache Semântico] Erro ao consultar cache")
#     return None
#
# def set_semantic_cached_response(message: str, response: str) -> None:
#     try:
#         cache = get_semantic_cache()
#         cache.store(prompt=message, response=response)
#     except Exception:
#         logger.warning("[Cache Semântico] Erro ao armazenar no cache")
