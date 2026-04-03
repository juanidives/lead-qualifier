-- init.sql
-- Executado automaticamente pelo PostgreSQL na primeira inicialização.
-- Cria o banco do backend separado do banco da Evolution API.

-- Banco para a Evolution API já é criado pelo POSTGRES_DB=evolution
-- Aqui criamos o banco para o backend (agente + memória)
CREATE DATABASE leadqualifier;

-- Habilita pgvector no banco da Evolution API (para uso futuro)
\c evolution
CREATE EXTENSION IF NOT EXISTS vector;

-- Habilita pgvector no banco do backend
\c leadqualifier
CREATE EXTENSION IF NOT EXISTS vector;
