# Manual de Operação — Lead Qualifier Agent
**Projeto:** Multi-tenant WhatsApp AI Agent
**Última atualização:** Abril 2026

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

> Se o Task Scheduler não funcionar, suba uvicorn e Celery manualmente (ver seção abaixo).

---

## Verificar se tudo está rodando

Abra o PowerShell e rode:

```
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
```
cd C:\Workspace\ia\lead-qualifier
docker compose up -d
```

### 2 — Backend (FastAPI)
Abra um PowerShell e rode:
```
cd C:\Workspace\ia\lead-qualifier\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```
Deixe esse terminal aberto.

### 3 — Celery Worker
Abra um segundo PowerShell e rode:
```
cd C:\Workspace\ia\lead-qualifier\backend
.\.venv\Scripts\Activate.ps1
celery -A app.workers.celery_app worker --loglevel=info
```
Deixe esse terminal aberto.

### 4 — Frontend (opcional — só para testar via browser)
Abra um terceiro PowerShell e rode:
```
cd C:\Workspace\ia\lead-qualifier\frontend
npm run dev
```
Acesse: `http://localhost:3000`

---

## Trocar de cliente ativo

Abra `C:\Workspace\ia\lead-qualifier\backend\.env` e mude:

```
# Para a clínica estética:
CLIENT=clinica-estetica

# Para a JB Bebidas:
CLIENT=jb_bebidas
```

Depois reinicie o uvicorn (`Ctrl+C` e rode novamente).

---

## Conectar WhatsApp (fazer uma vez por número)

### Passo 1 — Acessar o manager
Abra o navegador em:
```
http://localhost:8080/manager
```
API Key: `minha-chave-secreta`

### Passo 2 — Criar a instância
- Clique em **Create Instance**
- Nome: `clinica-estetica` (ou `jb-bebidas`)
- Integration: `WHATSAPP-BAILEYS`
- Salvar

### Passo 3 — Escanear o QR code
- Clique na instância criada → **Connect**
- Aparece o QR code
- No celular: WhatsApp → 3 pontinhos → **Aparelhos conectados** → **Conectar aparelho**
- Escaneie o QR
- Status deve mudar para `open` ou `connected`

### Passo 4 — Configurar o webhook
Na instância, vá em **Settings → Webhook** e configure:
- URL: `http://host.docker.internal:8000/webhook/whatsapp`
- Evento: `MESSAGES_UPSERT`
- Salvar

Pronto — o agente responde automaticamente a partir desse momento.

---

## Testar sem WhatsApp (simulação)

Abra o PowerShell (qualquer pasta) e rode:

**Para a clínica (Sofia):**
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/webhook/whatsapp" -Method POST -ContentType "application/json" -Body '{"event":"MESSAGES_UPSERT","instance":"clinica-estetica","data":{"key":{"remoteJid":"5511999990000@s.whatsapp.net","fromMe":false,"id":"TEST001"},"pushName":"Maria","message":{"conversation":"Ola, quero saber sobre botox"}}}' -UseBasicParsing
```

**Para a JB Bebidas (Juani):**
```powershell
Invoke-WebRequest -Uri "http://localhost:8000/webhook/whatsapp" -Method POST -ContentType "application/json" -Body '{"event":"MESSAGES_UPSERT","instance":"jb-bebidas","data":{"key":{"remoteJid":"5491199990000@s.whatsapp.net","fromMe":false,"id":"TEST001"},"pushName":"Juan","message":{"conversation":"Hola! Que cervezas tienen?"}}}' -UseBasicParsing
```

Resposta esperada: `{"status":"queued","phone":"..."}`

Veja a resposta do agente no terminal do uvicorn.

---

## Testar via browser (chat visual)

Com o frontend rodando (`npm run dev`), acesse:
```
http://localhost:3000
```

O cliente ativo é o que está definido em `backend/.env` → `CLIENT=`.

---

## Adicionar um novo cliente

### 1 — Criar a pasta e o config
```
clients/
└── novo-cliente/
    └── config.yaml
```

### 2 — Preencher o config.yaml

**Para clínicas/qualificação de leads:**
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

**Para distribuidoras/vendas:**
```yaml
company_name: "Nome da Empresa"
agent_name: "Nome do Agente"
client_type: "beverages"
niche: "distribuidora de bebidas"
working_hours: "horário de funcionamento"
tone: "tom de voz"
owner_phone: "5491100000000"
min_order: "$3000 ARS"
delivery_policy: "política de entrega"
products:
  - product_name: "Produto 1"
    category: "beer"
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

### 3 — Ativar o cliente
No `backend/.env`:
```
CLIENT=novo-cliente
```

Reiniciar o uvicorn. Pronto.

---

## Adicionar uma nova vertical (novo tipo de negócio)

1. Criar `backend/app/prompts/nova_vertical.py` com a função `build_nova_vertical_prompt(cfg)`
2. Registrar em `backend/app/prompts/__init__.py`:
```python
from app.prompts.nova_vertical import build_nova_vertical_prompt

PROMPT_BUILDERS = {
    "lead_qualifier": build_lead_qualifier_prompt,
    "beverages": build_beverages_prompt,
    "nova_vertical": build_nova_vertical_prompt,  # ← adicionar aqui
}
```
3. Nos novos clientes: `client_type: "nova_vertical"`

---

## Estrutura de pastas resumida

```
lead-qualifier/
├── docker-compose.yml     ← sobe todos os serviços
├── start.ps1              ← script de inicialização automática
├── clients/               ← um cliente = uma pasta
│   ├── clinica-estetica/
│   │   └── config.yaml
│   └── jb_bebidas/
│       ├── config.yaml
│       └── knowledge_base.md
└── backend/
    ├── .env               ← CLIENT= define o cliente ativo
    └── app/
        ├── agent.py       ← instancia o agente
        ├── prompts/       ← builders por vertical
        │   ├── lead_qualifier.py
        │   └── beverages.py
        ├── routers/
        │   └── whatsapp_router.py
        ├── services/
        │   ├── evolution_service.py
        │   ├── cache_service.py
        │   ├── order_service.py
        │   └── payment_service.py
        └── workers/
            ├── celery_app.py
            ├── tasks.py
            └── scheduled_tasks.py
```

---

## Variáveis de ambiente importantes (`backend/.env`)

```bash
# Cliente ativo
CLIENT=clinica-estetica

# OpenAI
OPENAI_API_KEY=sk-...
OPENAI_MODEL=gpt-4.1-mini

# Evolution API
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=minha-chave-secreta
EVOLUTION_INSTANCE=clinica-estetica

# Redis
REDIS_URL=redis://localhost:6379/0

# PostgreSQL (descomentado = usa Postgres, comentado = usa SQLite)
# POSTGRES_URL=postgresql://evolution:evolution@localhost:5432/leadqualifier

# Mercado Pago (quando tiver as credenciais)
# MERCADOPAGO_ACCESS_TOKEN=APP_USR-...
# MERCADOPAGO_WEBHOOK_SECRET=...
```

---

## Portas utilizadas

| Serviço | Porta |
|---|---|
| FastAPI (backend) | 8000 |
| Next.js (frontend) | 3000 |
| Evolution API | 8080 |
| PostgreSQL | 5432 |
| Redis | 6379 |

---

## Problemas comuns

**`uvicorn` não reconhecido:**
Use `python -m uvicorn app.main:app --reload` dentro de `backend/` com `.venv` ativo.

**`No module named 'app'`:**
Você está na pasta errada. Precisa estar dentro de `backend/`.

**Containers não sobem:**
Abra o Docker Desktop e aguarde o ícone estabilizar. Depois rode `docker compose up -d`.

**Evolution API reiniciando em loop:**
Verifique os logs: `docker logs evolution-api`. Geralmente é problema de conexão com o PostgreSQL.

**Agente respondendo errado (cliente errado):**
Verifique `CLIENT=` no `backend/.env` e reinicie o uvicorn.
