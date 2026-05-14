# Manual de Operação — lead-qualifier

> Manual interno de operação do agente. Cobre desenvolvimento local, deploy, configuração de cliente e troubleshooting.

**Última atualização:** maio de 2026

---

## Sumário

1. [Pipeline de deploy (regra fundamental)](#pipeline-de-deploy-regra-fundamental)
2. [O que sobe automaticamente quando você liga o PC](#o-que-sobe-automaticamente-quando-você-liga-o-pc)
3. [Verificar se tudo está rodando](#verificar-se-tudo-está-rodando)
4. [Subir manualmente (se o automático falhar)](#subir-manualmente-se-o-automático-falhar)
5. [Trocar de cliente ativo](#trocar-de-cliente-ativo)
6. [Conectar WhatsApp (uma vez por número)](#conectar-whatsapp-uma-vez-por-número)
7. [Testar sem WhatsApp (simulação)](#testar-sem-whatsapp-simulação)
8. [Adicionar um novo cliente](#adicionar-um-novo-cliente)
9. [Adicionar uma nova vertical](#adicionar-uma-nova-vertical)
10. [Estrutura de pastas resumida](#estrutura-de-pastas-resumida)
11. [Variáveis de ambiente importantes](#variáveis-de-ambiente-importantes)
12. [Portas utilizadas](#portas-utilizadas)
13. [Problemas comuns](#problemas-comuns)

---

## Pipeline de deploy (regra fundamental)

```
Windows (local)  →  GitHub  →  Hetzner (servidor)
```

**Nunca** modificar arquivos diretamente no servidor, mesmo em emergência. A correção certa leva poucos minutos a mais e evita dessincronização entre o repositório e o que está rodando em produção.

### Passo a passo

```powershell
# 1. Edite localmente
cd C:\Workspace\ia\lead-qualifier
# ... edita os arquivos ...

# 2. Commit + push
git add .
git commit -m "tipo: descrição clara"
git push origin main
```

```bash
# 3. Pull no servidor
ssh root@kailor-server
cd /opt/lead-qualifier
git pull origin main

# 4. Rebuild + restart se mudou código ou imagem Docker
docker compose --profile production up -d --build

# 5. Verificar
docker ps
git log --oneline -3
```

### Verificar sincronização entre GitHub e servidor

```powershell
# Local — último commit no GitHub
git log origin/main --oneline -3
```

```bash
# Servidor — último commit
cd /opt/lead-qualifier && git log --oneline -3
```

Os hashes precisam bater. Se o servidor estiver atrás, `git pull origin main`. Se aparecer mudança local no servidor que não veio do GitHub, alguém editou direto — descartar com `git checkout -- .` (depois de salvar o que for valioso) e reaplicar pelo pipeline.

### Em caso de conflito no pull

```bash
# Servidor tem mudanças locais que já estão no GitHub
git checkout -- arquivo-conflitante
git pull origin main
```

### Repositório

- **GitHub:** [`juanidives/lead-qualifier`](https://github.com/juanidives/lead-qualifier)
- **Servidor:** `/opt/lead-qualifier` (Hetzner `kailor-server`, IP `5.75.170.67`)
- **Local:** `C:\Workspace\ia\lead-qualifier`

---

## O que sobe automaticamente quando você liga o PC

| Serviço | Como sobe | O que faz |
|---|---|---|
| Docker Desktop | Configurado no Windows (Start at login) | Gerencia os containers |
| PostgreSQL | `restart: unless-stopped` no docker-compose | Banco de dados |
| Redis | `restart: unless-stopped` no docker-compose | Cache + fila Celery |
| Evolution API | `restart: unless-stopped` no docker-compose | Gateway WhatsApp |
| FastAPI (uvicorn) | Task Scheduler (`start.ps1`) | API do agente |
| Celery Worker | Task Scheduler (`start.ps1`) | Processa mensagens |

> Se o Task Scheduler não funcionar, suba uvicorn e Celery manualmente (próxima seção).

---

## Verificar se tudo está rodando

Abra o PowerShell e rode:

```powershell
docker ps
```

Deve mostrar 3 containers com status `Up`:

- `evolution-api`
- `postgres`
- `redis`

Para verificar o backend, abra o navegador em:

```
http://localhost:8000/docs
```

---

## Subir manualmente (se o automático falhar)

### 1 — Containers Docker

```powershell
cd C:\Workspace\ia\lead-qualifier
docker compose up -d
```

### 2 — Backend (FastAPI)

```powershell
cd C:\Workspace\ia\lead-qualifier\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

Deixe esse terminal aberto.

### 3 — Celery Worker

```powershell
cd C:\Workspace\ia\lead-qualifier\backend
.\.venv\Scripts\Activate.ps1
celery -A app.workers.celery_app worker --loglevel=info --pool=solo
```

> No Windows use `--pool=solo`. Em Linux pode usar o pool padrão.

### 4 — Frontend (opcional, só pra testar via browser)

```powershell
cd C:\Workspace\ia\lead-qualifier\frontend
npm run dev
```

Acesse: `http://localhost:3000`

---

## Trocar de cliente ativo

Edite `C:\Workspace\ia\lead-qualifier\backend\.env`:

```env
# Para a clínica estética:
CLIENT=clinica-estetica

# Para a JB Bebidas:
CLIENT=jb_bebidas
```

Reinicie o uvicorn (`Ctrl+C` e rode de novo).

---

## Conectar WhatsApp (uma vez por número)

### Passo 1 — Acessar o manager

```
http://localhost:8080/manager
```

API Key: a que estiver em `EVOLUTION_API_KEY` no `backend/.env`.

### Passo 2 — Criar a instância

- Clique em **Create Instance**
- Nome: `clinica-estetica` (ou `jb-bebidas`) — deve bater com `EVOLUTION_INSTANCE` no `.env`
- Integration: `WHATSAPP-BAILEYS`
- Salvar

### Passo 3 — Escanear o QR code

- Clique na instância → **Connect**
- No celular: WhatsApp → 3 pontinhos → **Aparelhos conectados** → **Conectar aparelho**
- Escaneie o QR
- Status muda para `open` ou `connected`

### Passo 4 — Configurar o webhook

Em **Settings → Webhook**:

- URL: `http://host.docker.internal:8000/webhook/whatsapp`
  - Em produção (servidor): `http://fastapi:8000/webhook/whatsapp`
- Evento: `MESSAGES_UPSERT`
- Headers: `x-api-key: <valor de WEBHOOK_API_KEY no .env>`
- Salvar

Pronto — o agente responde a partir desse momento.

---

## Testar sem WhatsApp (simulação)

### Para a Clínica Estética (Sofia)

```powershell
$key = (Get-Content C:\Workspace\ia\lead-qualifier\backend\.env | Select-String "WEBHOOK_API_KEY=").ToString().Split("=")[1]

Invoke-WebRequest -Uri "http://localhost:8000/webhook/whatsapp" `
  -Method POST `
  -ContentType "application/json" `
  -Headers @{ "x-api-key" = $key } `
  -Body '{"event":"MESSAGES_UPSERT","instance":"clinica-estetica","data":{"key":{"remoteJid":"5511999990000@s.whatsapp.net","fromMe":false,"id":"TEST001"},"pushName":"Maria","message":{"conversation":"Ola, quero saber sobre botox"}}}' `
  -UseBasicParsing
```

### Para a JB Bebidas (Juani)

```powershell
$key = (Get-Content C:\Workspace\ia\lead-qualifier\backend\.env | Select-String "WEBHOOK_API_KEY=").ToString().Split("=")[1]

Invoke-WebRequest -Uri "http://localhost:8000/webhook/whatsapp" `
  -Method POST `
  -ContentType "application/json" `
  -Headers @{ "x-api-key" = $key } `
  -Body '{"event":"MESSAGES_UPSERT","instance":"jb-bebidas","data":{"key":{"remoteJid":"5491199990000@s.whatsapp.net","fromMe":false,"id":"TEST001"},"pushName":"Juan","message":{"conversation":"Hola! Que cervezas tienen?"}}}' `
  -UseBasicParsing
```

Resposta esperada: `{"status":"queued","phone":"..."}` — a resposta do agente aparece no terminal do Celery worker.

---

## Testar via browser (chat visual)

Com o frontend rodando (`npm run dev`):

```
http://localhost:3000
```

O cliente ativo é o que está em `backend/.env` → `CLIENT=`.

---

## Adicionar um novo cliente

### 1 — Criar a pasta e o config

```
clients/
└── novo-cliente/
    └── config.yaml
```

### 2 — Preencher o `config.yaml`

**Vertical `lead_qualifier` (clínicas / serviços / qualificação):**

```yaml
company_name: "Nome da Empresa"
agent_name: "Nome do Agente"
client_type: "lead_qualifier"
niche: "tipo de negócio"
working_hours: "horário de funcionamento"
tone: "tom de voz"
services:
  - name: "Serviço 1"
    description: "Descrição do serviço"
next_step: "agendar uma consulta"
```

**Vertical `beverages` (distribuidoras / vendas com catálogo):**

```yaml
company_name: "Nome da Empresa"
agent_name: "Nome do Agente"
client_type: "beverages"
niche: "distribuidora de bebidas"
language: "es_AR"            # opcional
working_hours: "horário de funcionamento"
tone: "tom de voz"
owner_phone: ["549..."]
payment_alias: "alias-da-transferencia"
payment_methods_pickup:   ["transferencia", "efectivo"]
payment_methods_delivery: ["transferencia"]
min_order: "$0 ARS"
delivery_policy: "política de entrega"
products:
  - product_name: "Produto 1"
    category: "Cerveja"
    price: 1000
    cost_price: 600
    alcohol: true
    stock_quantity: 100
    is_available: true
    description: "Descrição"
    upselling: ["Produto 2"]
combos:
  - "Descrição do combo"
```

### 3 — (Opcional) Criar `knowledge_base.md`

Se a pasta tiver um `knowledge_base.md`, ele é carregado automaticamente em `cfg["knowledge_base"]` e injetado no prompt.

### 4 — Ativar o cliente

```env
# backend/.env
CLIENT=novo-cliente
```

Reiniciar o uvicorn. Pronto.

---

## Adicionar uma nova vertical

1. Criar `backend/app/prompts/<vertical>.py` com a função `build_<vertical>_prompt(cfg)`:

   ```python
   def build_minha_vertical_prompt(cfg: dict) -> str:
       return f"""
       Você é {cfg['agent_name']}, ...
       """
   ```

2. Registrar em `backend/app/prompts/__init__.py`:

   ```python
   from app.prompts.minha_vertical import build_minha_vertical_prompt

   PROMPT_BUILDERS = {
       "lead_qualifier": build_lead_qualifier_prompt,
       "beverages": build_beverages_prompt,
       "minha_vertical": build_minha_vertical_prompt,  # ← adicionar aqui
   }
   ```

3. Nos novos clientes dessa vertical: `client_type: "minha_vertical"` no `config.yaml`.

---

## Estrutura de pastas resumida

```
lead-qualifier/
├── docker-compose.yml         sobe todos os serviços (dev + prod via profile)
├── docker-compose.prod.yml    compose alternativo só de produção
├── start.ps1                  inicialização automática Windows
├── README.md                  apresentação pública do projeto
├── MANUAL.md                  este arquivo
├── LICENSE                    MIT
├── .gitattributes             normalização de line endings (LF)
├── .gitignore
├── clients/                   um cliente = uma pasta
│   ├── clinica-estetica/
│   │   └── config.yaml
│   └── jb_bebidas/
│       ├── config.yaml
│       └── knowledge_base.md
├── docker/
│   └── init.sql               cria DB leadqualifier + habilita pgvector
├── scripts/
│   └── check_whatsapp_connection.py   monitor de conexão (cron 18h)
├── frontend/                  Next.js (chat visual de dev)
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    ├── .env                   (não commitado)
    ├── .env.production.example
    └── app/
        ├── main.py            AgentOS + endpoints
        ├── agent.py           instância do Agno
        ├── company_config.py  carrega config do cliente ativo
        ├── config.py          lê variáveis do .env
        ├── database.py        engine SQLAlchemy
        ├── models.py          tabelas (Contact, Product, CustomerOrder, ...)
        ├── prompts/
        │   ├── __init__.py    factory PROMPT_BUILDERS
        │   ├── lead_qualifier.py
        │   └── beverages.py
        ├── routers/
        │   └── whatsapp_router.py    webhook autenticado por x-api-key
        ├── services/
        │   ├── agent_tools.py        tool confirmar_pedido (Agno)
        │   ├── evolution_service.py
        │   ├── cache_service.py
        │   ├── order_service.py
        │   ├── order_commands_service.py    comandos do dono (CONFIRMAR PAGO etc.)
        │   └── contact_import_service.py    importa contatos de Excel
        └── workers/
            ├── celery_app.py
            ├── tasks.py                debounce + processamento de mensagem
            └── scheduled_tasks.py      Celery Beat (follow-up, broadcast, etc.)
```

---

## Variáveis de ambiente importantes

`backend/.env` (dev local):

```env
# Cliente ativo (deve existir uma pasta clients/<CLIENT>/)
CLIENT=jb_bebidas

# OpenAI
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4.1-mini

# Evolution API (gateway WhatsApp)
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=...
EVOLUTION_INSTANCE=jb-bebidas

# Webhook autenticação (header x-api-key)
# Gerar com: openssl rand -hex 32
WEBHOOK_API_KEY=...

# Redis (Celery broker + cache)
REDIS_URL=redis://localhost:6379/0

# PostgreSQL — em produção SEMPRE preenchido
# (vazio = SQLite em dev local)
POSTGRES_URL=postgresql://evolution:evolution@localhost:5432/leadqualifier

# Telefone do dono (formato internacional sem +)
OWNER_PHONE=549...
```

> **Em produção:** a URL muda para a rede Docker — `http://evolution-api:8080`, `redis://redis:6379/0`, `postgresql://evolution:...@postgres:5432/leadqualifier`. Veja `backend/.env.production.example`.

---

## Portas utilizadas

| Serviço | Porta | Bind |
|---|---|---|
| FastAPI (backend) | 8000 | `0.0.0.0` (público) |
| Next.js (frontend) | 3000 | `0.0.0.0` (dev local) |
| Evolution API | 8080 | `127.0.0.1` (loopback, atrás de Nginx em prod) |
| PostgreSQL | 5432 | `127.0.0.1` (interno) |
| Redis | 6379 | `127.0.0.1` (interno) |
| n8n (opcional) | 5678 | `127.0.0.1` (interno) |

> **Importante:** Postgres, Redis e n8n usam bind em `127.0.0.1` no compose porque **Docker bypassa o UFW**. Sem o bind, ficariam públicos mesmo com `ufw deny`. Já tivemos um incidente em produção por causa disso.

---

## Problemas comuns

**`uvicorn` não reconhecido:**
Use `python -m uvicorn app.main:app --reload` dentro de `backend/` com `.venv` ativo.

**`No module named 'app'`:**
Você está na pasta errada. Precisa estar dentro de `backend/`.

**Containers não sobem:**
Abra o Docker Desktop e aguarde o ícone estabilizar. Depois rode `docker compose up -d`.

**Evolution API reiniciando em loop:**
`docker logs evolution-api`. Geralmente é problema de conexão com o PostgreSQL — espere o Postgres ficar healthy.

**Agente respondendo errado (cliente errado):**
Verifique `CLIENT=` no `backend/.env` e reinicie o uvicorn.

**Webhook retorna 403:**
Header `x-api-key` ausente ou diferente do `WEBHOOK_API_KEY` configurado no `.env`. Atualize o webhook na Evolution (Settings → Webhook → Headers).

**Celery não processa mensagens:**

```powershell
# Checar fila Redis
docker exec -it redis redis-cli LLEN celery

# Reiniciar worker
# (no dev: Ctrl+C e roda de novo. Em prod: docker compose restart celery-worker)
```

**Servidor com mudanças locais não commitadas:**
Sinal de que alguém quebrou o pipeline e editou direto no servidor. Salve o que for valioso, descarte com `git checkout -- .` e reaplique a mudança via Local → GitHub → Servidor.

**Diff fantasma de line endings (CRLF↔LF):**
Não deve acontecer porque o `.gitattributes` força LF. Se voltar, rode `git add --renormalize .` e commit.
