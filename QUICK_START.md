# Quick Start - JB Bebidas WhatsApp Sales Agent

## Início Rápido em 5 Passos

### 1️⃣ Configurar Cliente
```bash
# backend/.env
CLIENT=jb_bebidas
OPENAI_API_KEY=sk-proj-...
EVOLUTION_API_KEY=sua-chave-evolution
EVOLUTION_INSTANCE=jb-bebidas
```

### 2️⃣ Instalar Dependências
```bash
cd backend
pip install -r requirements.txt
```

### 3️⃣ Iniciar Banco de Dados
```bash
# Criar tabelas automaticamente
docker compose up postgres redis -d
```

### 4️⃣ Rodar o Backend
```bash
# Terminal 1: FastAPI (webhook + chat)
uvicorn app.main:app --reload

# Terminal 2: Celery Worker (processamento assíncrono)
celery -A app.workers.celery_app worker --loglevel=info

# Terminal 3 (opcional): Celery Beat (tarefas agendadas)
celery -A app.workers.celery_app beat --loglevel=info
```

### 5️⃣ Testar
```bash
# Endpoint de chat
curl -X POST http://localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Hola, quiero una Quilmes"}'

# Webhook WhatsApp (simulado)
curl -X POST http://localhost:8000/webhook/whatsapp \
  -H "Content-Type: application/json" \
  -d '{
    "event": "MESSAGES_UPSERT",
    "data": {
      "key": {"remoteJid": "5491199990000@s.whatsapp.net", "fromMe": false},
      "message": {"conversation": "Hola Juani!"},
      "pushName": "Juan"
    }
  }'
```

---

## 📋 Funcionalidades Principais

| Feature | Status | Arquivo |
|---------|--------|---------|
| Agent Juani (IA) | ✅ | `app/agent.py` |
| WhatsApp Webhook | ✅ | `app/routers/whatsapp_router.py` |
| Importar Contatos | ✅ | `app/services/contact_import_service.py` |
| Gerenciar Pedidos | ✅ | `app/services/order_service.py` |
| Pagamento Mercado Pago | ✅ | `app/services/payment_service.py` |
| Broadcasts | ✅ | `app/workers/scheduled_tasks.py` |
| Banco de Dados | ✅ | `app/models.py` |
| Knowledge Base | ✅ | `clients/jb_bebidas/knowledge_base.md` |

---

## 🛠️ Tarefas Comuns

### Importar Contatos
```python
from app.services.contact_import_service import import_from_excel
from app.database import SessionLocal
from app.models import Contact

# Excel
result = import_from_excel("./contacts.xlsx")
print(f"✅ Importados: {result['total_imported']}")

# Salvar no banco
db = SessionLocal()
for contact_data in result['contacts']:
    contact = Contact(**contact_data)
    db.add(contact)
db.commit()
db.close()
```

### Enviar Promoção em Massa
```bash
# Via Celery
celery -A app.workers.celery_app call tasks.send_promotion_broadcast \
  --args='["🍻 Sexta com 2x1 em cervezas!", "all_active"]'

# Via Python
from app.workers.scheduled_tasks import send_promotion_broadcast
send_promotion_broadcast.delay(
    message_text="Promoção especial para você!",
    contact_ids="all_active"
)
```

### Consultiar Estoque
```python
from app.database import SessionLocal
from app.models import Product

db = SessionLocal()
produtos = db.query(Product).filter(Product.is_available == True).all()
for p in produtos:
    print(f"{p.product_name}: {p.stock_quantity} unid. (${p.price})")
db.close()
```

### Atualizar Estoque Manual
```python
from app.database import SessionLocal
from app.models import Product

db = SessionLocal()
quilmes = db.query(Product).filter(
    Product.product_name == "Quilmes Clásica 1L"
).first()

quilmes.stock_quantity = 150
db.add(quilmes)
db.commit()
```

---

## 🎯 Fluxo de Venda (Visão Geral)

```
Cliente mensageia Juani
    ↓
[whatsapp_router.py] Recebe via Evolution API
    ↓
[agent.py] Sofia/Juani responde (OpenAI)
    ↓
[evolution_service.py] Envia resposta via WhatsApp
    ↓
Cliente: "Quiero 2 Quilmes"
    ↓
[order_service.py] Valida estoque + cria pedido
    ↓
[payment_service.py] Gera link Mercado Pago
    ↓
Cliente paga
    ↓
[main.py] Webhook Mercado Pago confirma
    ↓
[models.py] Atualiza status + estoque
    ↓
Cliente e dono notificados ✅
```

---

## 🔑 Variáveis Ambiente Obrigatórias

```env
# OpenAI
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4.1-mini

# Cliente ativo
CLIENT=jb_bebidas

# Evolution API (WhatsApp gateway)
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=sua-chave-aqui
EVOLUTION_INSTANCE=jb-bebidas

# Redis (Celery broker)
REDIS_URL=redis://localhost:6379/0

# PostgreSQL (Fase 3)
POSTGRES_URL=postgresql://evolution:evolution@localhost:5432/leadqualifier

# Mercado Pago
MERCADOPAGO_ACCESS_TOKEN=APP_USR-...
MERCADOPAGO_WEBHOOK_SECRET=seu-webhook-secret

# Info do negócio
OWNER_PHONE=5491100000000
```

---

## 📊 Estrutura de Dados

### Tabelas Principais

**contact** - Clientes
```sql
id | name | phone (+549...) | city | source | is_active | created_at
```

**product** - Catálogo
```sql
id | product_name | category | price | stock_quantity | is_available | ...
```

**customer_order** - Pedidos
```sql
id | contact_id | items (JSON) | address | total | status | created_at
status: pending → paid → cancelled
```

**payment** - Pagamentos
```sql
id | order_id | mp_link | status | created_at
status: pending → approved → rejected → expired
```

**conversation** - Histórico
```sql
id | contact_id | role (user|agent) | content | type (text|audio|image) | created_at
```

**broadcast_log** - Promoções enviadas
```sql
id | contact_id | promotion_id | message | status | replied | sent_at
```

---

## 🚀 Deploy Docker

```bash
# Desenvolvimento (só backend)
docker compose up postgres redis -d
uvicorn app.main:app --reload

# Produção (completo)
docker compose --profile production up -d

# Verificar logs
docker compose logs -f celery-worker
docker compose logs -f backend
```

---

## 🐛 Debug & Troubleshooting

### Celery não processa mensagens?
```bash
# Checar fila Redis
redis-cli
> LLEN celery
> SMEMBERS celery:active_queue

# Reiniciar worker
docker compose restart celery-worker
```

### Banco não conecta?
```bash
# Testar PostgreSQL
psql postgresql://evolution:evolution@localhost:5432/leadqualifier

# Criar tabelas manualmente
python -c "from app.database import init_db; init_db()"
```

### OpenAI timeout?
```bash
# Aumentar timeout em app/agent.py
TIMEOUT = 60  # segundos
```

### Webhook não recebe?
```bash
# Verificar Evolution API
curl http://localhost:8080/health

# Logs FastAPI
tail -f uvicorn.log
```

---

## 📞 Contatos e Suporte

- **Documentação completa:** `IMPLEMENTATION_SUMMARY.md`
- **Knowledge base:** `clients/jb_bebidas/knowledge_base.md`
- **Config:** `clients/jb_bebidas/config.yaml`
- **GitHub:** (adicione seu repo)

---

## 🎓 Próximos Passos

1. ✅ Conectar Evolution API real
2. ✅ Registrar webhook Mercado Pago
3. ✅ Importar catálogo de produtos
4. ✅ Configurar horários de atendimento
5. ✅ Treinar com exemplos de conversas
6. ✅ Deploy em produção
7. 🔄 Monitorar e otimizar respostas

---

**Última atualização:** 2026-04-04
**Versão:** 1.0 - Completa
