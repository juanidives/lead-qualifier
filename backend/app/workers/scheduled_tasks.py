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
  - Broadcast: envia promoção para lista de contatos

Para ativar o Beat, rode em um terminal separado:
  celery -A app.workers.celery_app beat --loglevel=info

Ou adicione --beat ao worker (só para desenvolvimento):
  celery -A app.workers.celery_app worker --beat --loglevel=info
"""

import logging
import time
from datetime import datetime, timedelta
from typing import List, Optional

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


# ─────────────────────────────────────────────────────────────────
# Tarefa de broadcast (promoções em massa)
# ─────────────────────────────────────────────────────────────────

@celery_app.task(
    bind=True,
    max_retries=3,
    default_retry_delay=300,
    name="tasks.send_promotion_broadcast",
)
def send_promotion_broadcast(
    self,
    message_text: str,
    contact_ids: List[int] | str = 'all_active',
    image_path: Optional[str] = None,
    promotion_id: Optional[int] = None,
    min_delay_seconds: int = 6
):
    """
    Envia uma promoção/mensagem em massa para uma lista de contatos.

    Respeita intervalo mínimo entre envios para evitar spam.

    Args:
        message_text: conteúdo da mensagem
        contact_ids: lista de IDs de contatos ou 'all_active' para todos ativos
        image_path: caminho a uma imagem (opcional)
        promotion_id: ID da promoção (para rastreamento)
        min_delay_seconds: intervalo mínimo entre envios (padrão 6s)

    Returns:
        {
            'total_sent': int,
            'total_errors': int,
            'errors': list[str]
        }
    """
    from app.database import SessionLocal
    from app.models import Contact, BroadcastLog, Promotion

    logger.info(
        f"[Broadcast] Iniciando envio de promoção "
        f"(contact_ids={contact_ids}, promotion_id={promotion_id})"
    )

    db = SessionLocal()
    result = {
        'total_sent': 0,
        'total_errors': 0,
        'errors': []
    }

    try:
        # Determina lista de contatos
        if contact_ids == 'all_active':
            contacts = db.query(Contact).filter(Contact.is_active == True).all()
            logger.info(f"[Broadcast] Enviando para {len(contacts)} contatos ativos")
        else:
            contacts = db.query(Contact).filter(Contact.id.in_(contact_ids)).all()
            logger.info(f"[Broadcast] Enviando para {len(contacts)} contatos selecionados")

        # Processa cada contato com intervalo
        for idx, contact in enumerate(contacts):
            try:
                logger.debug(f"[Broadcast] Enviando para {contact.phone} ({idx + 1}/{len(contacts)})")

                # Envia mensagem
                send_text_message(phone=contact.phone, text=message_text)

                # TODO: implementar envio de imagem quando disponível
                # if image_path:
                #     send_image_message(phone=contact.phone, image_path=image_path, caption=message_text)

                # Registra no broadcast_log
                log_entry = BroadcastLog(
                    contact_id=contact.id,
                    promotion_id=promotion_id,
                    message=message_text,
                    status='sent'
                )
                db.add(log_entry)
                db.commit()

                result['total_sent'] += 1

                # Aguarda intervalo antes do próximo envio
                if idx < len(contacts) - 1:  # não aguarda após o último
                    time.sleep(min_delay_seconds)

            except Exception as e:
                error_msg = f"Contato {contact.phone}: {str(e)}"
                result['total_errors'] += 1
                result['errors'].append(error_msg)
                logger.error(f"[Broadcast] {error_msg}")

                # Registra erro no broadcast_log
                try:
                    log_entry = BroadcastLog(
                        contact_id=contact.id,
                        promotion_id=promotion_id,
                        message=message_text,
                        status='error'
                    )
                    db.add(log_entry)
                    db.commit()
                except Exception as log_e:
                    logger.warning(f"[Broadcast] Erro ao registrar falha: {log_e}")

        # Atualiza estatísticas da promoção
        if promotion_id:
            try:
                promotion = db.query(Promotion).filter(Promotion.id == promotion_id).first()
                if promotion:
                    promotion.total_sent += result['total_sent']
                    promotion.sent_at = datetime.utcnow()
                    db.add(promotion)
                    db.commit()
                    logger.info(f"[Broadcast] Promoção #{promotion_id} atualizada")
            except Exception as e:
                logger.warning(f"[Broadcast] Erro ao atualizar promoção: {e}")

        logger.info(
            f"[Broadcast] Concluído: {result['total_sent']} enviados, "
            f"{result['total_errors']} erros"
        )
        return result

    except Exception as e:
        logger.exception(f"[Broadcast] Erro geral na tarefa de broadcast")
        result['errors'].append(f"Erro crítico: {str(e)}")

        # Retry automático
        if self.request.retries < self.max_retries:
            logger.info(f"[Broadcast] Retentando... (tentativa {self.request.retries + 1})")
            raise self.retry(exc=e, countdown=300)  # tenta em 5 minutos
        else:
            logger.error("[Broadcast] Máximo de tentativas excedido")

        return result

    finally:
        db.close()


@celery_app.task(
    bind=True,
    name="tasks.update_broadcast_reply_count",
)
def update_broadcast_reply_count(self, contact_id: int, promotion_id: int):
    """
    Atualiza o contador de replies de uma promoção quando o contato responde.

    Chamada quando um contato que recebeu broadcast responde a uma mensagem.

    Args:
        contact_id: ID do contato que respondeu
        promotion_id: ID da promoção
    """
    from app.database import SessionLocal
    from app.models import BroadcastLog, Promotion

    db = SessionLocal()

    try:
        # Marca o log como "replied"
        log = db.query(BroadcastLog).filter(
            BroadcastLog.contact_id == contact_id,
            BroadcastLog.promotion_id == promotion_id
        ).first()

        if log and not log.replied:
            log.replied = True
            db.add(log)

            # Incrementa contador da promoção
            promotion = db.query(Promotion).filter(Promotion.id == promotion_id).first()
            if promotion:
                promotion.total_replied += 1
                db.add(promotion)

            db.commit()
            logger.info(
                f"[Broadcast] Contato {contact_id} respondeu à promoção #{promotion_id}"
            )

    except Exception as e:
        logger.exception(f"[Broadcast] Erro ao atualizar reply count: {e}")
        db.rollback()

    finally:
        db.close()
