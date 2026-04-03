"""
scheduled_tasks.py
------------------
Tarefas agendadas com Celery Beat.

Celery Beat é um scheduler — pensa nele como um "cron" gerenciado pelo Celery.
Define quais tarefas rodam automaticamente e com qual frequência.

Casos de uso:
  - Follow-up: lead não respondeu em 24h → manda mensagem de acompanhamento
  - Lembrete de consulta: 1 dia antes do agendamento
  - Reativação: lead sumiu há 7 dias → tenta reengajar

Para ativar o Beat, rode em um terminal separado:
  celery -A app.workers.celery_app beat --loglevel=info

Ou adicione --beat ao worker (só para desenvolvimento):
  celery -A app.workers.celery_app worker --beat --loglevel=info
"""

import logging
from datetime import datetime, timedelta

from app.workers.celery_app import celery_app
from app.services.evolution_service import send_text_message

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────
# Configuração do agendamento (Celery Beat Schedule)
# ─────────────────────────────────────────────────────────────────

celery_app.conf.beat_schedule = {
    # Verifica leads sem resposta todo dia às 10h
    "followup-sem-resposta": {
        "task": "tasks.send_followup_inactive_leads",
        "schedule": 86400,  # a cada 24 horas (em segundos)
        # Para horário fixo, use crontab:
        # "schedule": crontab(hour=10, minute=0),
    },
}


# ─────────────────────────────────────────────────────────────────
# Tarefa de follow-up
# ─────────────────────────────────────────────────────────────────

@celery_app.task(name="tasks.send_followup_inactive_leads")
def send_followup_inactive_leads():
    """
    Envia mensagem de follow-up para leads que não responderam em 24h.

    Em produção, esta tarefa buscaria no banco de dados (PostgreSQL)
    os contatos com última interação > 24h atrás e sem agendamento fechado.

    Por enquanto, serve como estrutura para você implementar a consulta
    ao banco conforme sua lógica de negócio.
    """
    logger.info("[Beat] Iniciando verificação de leads inativos...")

    # TODO: substituir por consulta real ao banco PostgreSQL
    # Exemplo de como ficaria:
    #
    # from sqlalchemy import create_engine, text
    # from app.config import POSTGRES_URL
    #
    # engine = create_engine(POSTGRES_URL)
    # with engine.connect() as conn:
    #     leads = conn.execute(text("""
    #         SELECT DISTINCT session_id
    #         FROM agent_sessions
    #         WHERE updated_at < NOW() - INTERVAL '24 hours'
    #           AND session_id NOT LIKE '%@g.us'  -- ignora grupos
    #     """)).fetchall()
    #
    # for lead in leads:
    #     phone = lead.session_id
    #     send_followup.delay(phone)

    logger.info("[Beat] Verificação concluída.")
    return {"status": "ok"}


@celery_app.task(
    bind=True,
    max_retries=2,
    name="tasks.send_followup",
)
def send_followup(self, phone: str, custom_message: str | None = None):
    """
    Envia uma mensagem de follow-up para um contato específico.

    Args:
        phone:          número do contato (ex: "5511999990000")
        custom_message: mensagem personalizada (usa padrão se None)
    """
    message = custom_message or (
        "Oi! 😊 Passando para ver se você ficou com alguma dúvida "
        "sobre nossos serviços. Posso te ajudar com alguma coisa?"
    )

    logger.info(f"[Beat] Enviando follow-up para {phone}")

    try:
        send_text_message(phone=phone, text=message)
        logger.info(f"[Beat] Follow-up enviado para {phone}")
        return {"phone": phone, "status": "sent"}
    except Exception as exc:
        logger.exception(f"[Beat] Erro ao enviar follow-up para {phone}")
        raise self.retry(exc=exc, countdown=60)
