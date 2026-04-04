"""
database.py
-----------
Configuração de conexão ao PostgreSQL via SQLAlchemy.
Cria automaticamente todas as tabelas na primeira execução.
"""

import logging
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import StaticPool
from app.config import POSTGRES_URL
from app.models import Base

logger = logging.getLogger(__name__)


def get_engine():
    """
    Retorna a engine SQLAlchemy configurada.

    Em development: usa SQLite em memória se POSTGRES_URL vazio
    Em produção: usa PostgreSQL
    """
    if POSTGRES_URL:
        logger.info("Usando PostgreSQL como banco de dados")
        engine = create_engine(
            POSTGRES_URL,
            echo=False,  # mude para True para ver SQL gerado
            pool_pre_ping=True,  # testa conexão antes de usar
        )
    else:
        logger.warning("POSTGRES_URL não configurado. Usando SQLite em memória para testes.")
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )

    return engine


def init_db():
    """
    Cria todas as tabelas definidas em models.py.
    Seguro chamar múltiplas vezes — cria apenas se não existirem.
    """
    engine = get_engine()
    logger.info("Criando tabelas no banco de dados...")
    Base.metadata.create_all(engine)
    logger.info("Tabelas criadas com sucesso")
    return engine


# Instancia global da engine
engine = init_db()

# SessionLocal factory para criar sessões do SQLAlchemy
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def get_db() -> Session:
    """
    Generator para uso em dependências FastAPI.

    Exemplo:
        @app.get("/items")
        def list_items(db: Session = Depends(get_db)):
            return db.query(Item).all()
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
