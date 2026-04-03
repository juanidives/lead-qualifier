"""
celery_app.py
-------------
Configuração central do Celery.

O Celery é o gerenciador de tarefas assíncronas.
Ele recebe tarefas (ex: processar mensagem WhatsApp) e as executa
em background, sem bloquear o FastAPI.

Arquitetura:
  FastAPI (webhook) → enfileira tarefa no Redis → Celery Worker processa
"""

from celery import Celery
from app.config import REDIS_URL

# Cria a instância do Celery
# - broker: onde as tarefas ficam na fila (Redis)
# - backend: onde os resultados são armazenados (Redis também)
celery_app = Celery(
    "lead_qualifier",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "app.workers.tasks",             # processamento de mensagens
        "app.workers.scheduled_tasks",   # follow-ups e proactive messaging
    ],
)

# Configurações gerais
celery_app.conf.update(
    # Serialização em JSON (mais seguro e legível que pickle)
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    # Fuso horário
    timezone="America/Sao_Paulo",
    enable_utc=True,
    # Retry automático em caso de falha de conexão com o broker
    broker_connection_retry_on_startup=True,
    # Resultado expira em 1 hora (não precisamos guardar para sempre)
    result_expires=3600,
)
