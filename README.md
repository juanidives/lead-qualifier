# lead-qualifier

> Agente de IA multi-tenant para WhatsApp. Atende clientes, qualifica leads e fecha vendas com memória persistente e fluxo customizável por vertical.

[![Python](https://img.shields.io/badge/python-3.12-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.135-009688.svg)](https://fastapi.tiangolo.com/)
[![Agno](https://img.shields.io/badge/Agno-2.5-orange.svg)](https://github.com/agno-agi/agno)
[![Docker](https://img.shields.io/badge/Docker-compose-2496ED.svg)](https://docs.docker.com/compose/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

---

## O que é

Plataforma backend que conecta um modelo de linguagem (OpenAI) ao WhatsApp via [Evolution API](https://github.com/EvolutionAPI/evolution-api), permitindo que negócios diferentes usem o mesmo código com configuração própria — catálogo, prompts, fluxo de pedido, política de pagamento.

Cada cliente é uma pasta em `clients/<slug>/` com um `config.yaml` declarando a vertical (`client_type`). O builder de prompt correto é selecionado em runtime via factory pattern. Para adicionar um cliente novo da mesma vertical, basta criar a pasta e preencher o YAML — sem tocar no código.

## Cases em produção

- **JB Bebidas** ([Resistencia, Argentina](https://www.google.com/maps/place/Resistencia,+Chaco)) — agente de vendas para distribuidora de bebidas. Atende em espanhol argentino, processa pedidos, valida estoque, gerencia pagamento por transferência ou efectivo, e notifica os donos via WhatsApp com comandos determinísticos (`CONFIRMAR PAGO`, `LISTO`, `ENVIADO`).
- **Clínica Estética Belá** — agente de qualificação de leads para clínica de estética. Apresenta serviços, qualifica BANT (Budget, Authority, Need, Timeline) e agenda consultas.

## Stack

| Camada | Tecnologia |
|---|---|
| Modelo | OpenAI (GPT-4.1-mini por padrão, configurável) |
| Framework de agente | [Agno](https://github.com/agno-agi/agno) |
| API | FastAPI + Uvicorn |
| Gateway WhatsApp | Evolution API v2 (Baileys) |
| Tasks assíncronas | Celery + Redis |
| Banco de dados | PostgreSQL (com pgvector) |
| Frontend dev | Next.js 16 + React 19 |
| Infra | Docker Compose |

## Arquitetura

```
WhatsApp do cliente
        │
        ▼
┌────────────────────┐
│   Evolution API    │  gateway WhatsApp (Baileys)
└─────────┬──────────┘
          │ webhook
          ▼
┌────────────────────┐
│  FastAPI / router  │  autentica (x-api-key), roteia por tipo de mensagem
└────┬───────┬───────┘
     │       │
     │       └─► comandos do dono ─► determinístico (sem LLM)
     │
     ▼
┌────────────────────┐
│  Redis (debounce)  │  acumula mensagens 4-5s
└─────────┬──────────┘
          ▼
┌────────────────────┐
│   Celery worker    │  processa, chama o agente, responde com typing delay
└─────────┬──────────┘
          ▼
┌────────────────────┐
│   Agente (Agno)    │  prompt da vertical + catálogo + knowledge base
│   ├─ tool: confirmar_pedido
│   └─ memória: PostgreSQL
└─────────┬──────────┘
          ▼
   resposta via Evolution API
```

## Multi-tenancy

A pasta `clients/<slug>/` é a única coisa que muda por cliente. O resto é código compartilhado.

```
clients/
├── clinica-estetica/
│   └── config.yaml             # client_type: lead_qualifier
└── jb_bebidas/
    ├── config.yaml             # client_type: beverages
    └── knowledge_base.md       # injetado no prompt automaticamente
```

Trocar o cliente ativo: setar `CLIENT=<slug>` no `backend/.env` e reiniciar o servidor.

## Verticais suportadas

| `client_type` | Builder de prompt | Caso de uso |
|---|---|---|
| `lead_qualifier` | `app/prompts/lead_qualifier.py` | Atendimento + qualificação BANT (clínicas, serviços) |
| `beverages` | `app/prompts/beverages.py` | Vendas com catálogo, combos, upselling, fluxo de pagamento |

Adicionar uma nova vertical é uma função pura `build_<vertical>_prompt(cfg) -> str` registrada no factory de `app/prompts/__init__.py`.

## Estrutura do projeto

```
lead-qualifier/
├── backend/                    FastAPI + Agno + Celery
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py             AgentOS + endpoints
│       ├── agent.py            instância do Agno
│       ├── company_config.py   carrega config do cliente ativo
│       ├── prompts/            builders por vertical
│       ├── routers/            webhook WhatsApp
│       ├── services/           lógica de negócio (orders, payments, evolution)
│       └── workers/            Celery tasks + Beat schedule
├── frontend/                   Next.js (chat visual para dev)
├── clients/                    configs por tenant
├── docker/                     init.sql do Postgres (cria DB + pgvector)
├── scripts/                    utilitários (monitor de conexão)
├── docker-compose.yml          dev local + produção via profile
├── docker-compose.prod.yml     compose alternativo só de produção
├── start.ps1                   inicialização Windows (Task Scheduler)
└── MANUAL.md                   manual de operação completo
```

## Quick start (dev local)

Pré-requisitos: Docker Desktop, Python 3.12, Node 20+.

```bash
# 1. Clone
git clone https://github.com/juanidives/lead-qualifier.git
cd lead-qualifier

# 2. Configure o backend
cp backend/.env.production.example backend/.env
# Edite backend/.env com suas chaves

# 3. Suba a infra (Postgres, Redis, Evolution API)
docker compose up -d

# 4. Backend (FastAPI)
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1                 # Windows
# source .venv/bin/activate                # Linux/Mac
pip install -r requirements.txt
python -m uvicorn app.main:app --reload

# 5. Em outro terminal: Celery worker
celery -A app.workers.celery_app worker --loglevel=info

# 6. (opcional) Frontend de dev
cd ../frontend
npm install && npm run dev
```

Operação detalhada (conectar WhatsApp, trocar cliente, deploy, troubleshooting): ver [MANUAL.md](MANUAL.md).

## Endpoints

| Método | Path | Descrição |
|---|---|---|
| `POST` | `/webhook/whatsapp` | Webhook da Evolution API. Requer header `x-api-key`. |
| `GET`  | `/agent-info` | Nome e descrição do agente ativo (usado pelo frontend). |
| `POST` | `/chat` | Chat direto via Agent UI (mantém `session_id`). |
| `GET`  | `/docs` | Swagger UI gerado pelo FastAPI. |

Mais endpoints expostos pelo `AgentOS` do Agno em `/agui/*`.

## Segurança

- Webhook autenticado por API key (`WEBHOOK_API_KEY`, header `x-api-key`).
- Postgres e Redis com bind em `127.0.0.1` (não exposto à internet) — Docker bypassa o UFW, esse cuidado é obrigatório.
- `.env` e `*.db` no `.gitignore`. Template em `backend/.env.production.example` com placeholders.
- Mensagens do dono são processadas deterministicamente, nunca passam pelo LLM.

## Licença

[MIT](LICENSE) — use, modifique, distribua livremente, mantendo o aviso de copyright.

## Sobre

Desenvolvido por [Juan Morales](https://github.com/juanidives) como infraestrutura da [Kailor](https://kailor.com.br) — agentes de IA para pequenas e médias empresas.
