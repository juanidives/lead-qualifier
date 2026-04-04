# File Manifest - JB Bebidas Implementation

**Total Files:** 16 created/modified
**Last Updated:** 2026-04-04

---

## Client Configuration

| File Path | Lines | Status | Description |
|-----------|-------|--------|-------------|
| `clients/jb_bebidas/config.yaml` | 118 | ✅ NEW | JB Bebidas configuration (11 products, 5 combos) |
| `clients/jb_bebidas/knowledge_base.md` | 304 | ✅ NEW | Knowledge base (FAQs, catalog, process, examples) |

---

## Backend Core

| File Path | Lines | Status | Description |
|-----------|-------|--------|-------------|
| `backend/app/agent.py` | 222 | ✅ MODIFIED | Dynamic system prompt builder + agent instance |
| `backend/app/main.py` | 154 | ✅ MODIFIED | FastAPI app + Mercado Pago webhook endpoint |
| `backend/app/config.py` | 27 | ✅ MODIFIED | Environment variables (added MercadoPago) |
| `backend/app/company_config.py` | - | ✅ EXISTING | Client config loader (unchanged) |

---

## Database Layer

| File Path | Lines | Status | Description |
|-----------|-------|--------|-------------|
| `backend/app/database.py` | 75 | ✅ NEW | SQLAlchemy engine + table creation |
| `backend/app/models.py` | 184 | ✅ NEW | 9 SQLAlchemy models (contact, product, order, etc) |

---

## Services

| File Path | Lines | Status | Description |
|-----------|-------|--------|-------------|
| `backend/app/services/contact_import_service.py` | 289 | ✅ NEW | Excel/Google Sheets import + phone normalization |
| `backend/app/services/order_service.py` | 267 | ✅ NEW | Order management (create, validate, confirm) |
| `backend/app/services/payment_service.py` | 324 | ✅ NEW | Mercado Pago integration (checkout + webhooks) |
| `backend/app/services/evolution_service.py` | - | ✅ EXISTING | WhatsApp message sending (unchanged) |
| `backend/app/services/cache_service.py` | - | ✅ EXISTING | Redis cache layer (unchanged) |

---

## Routers

| File Path | Lines | Status | Description |
|-----------|-------|--------|-------------|
| `backend/app/routers/whatsapp_router.py` | 245 | ✅ MODIFIED | Audio handling + contact capture |
| `backend/app/routers/__init__.py` | - | ✅ EXISTING | Router init (unchanged) |

---

## Workers (Celery)

| File Path | Lines | Status | Description |
|-----------|-------|--------|-------------|
| `backend/app/workers/celery_app.py` | - | ✅ EXISTING | Celery configuration (unchanged) |
| `backend/app/workers/tasks.py` | 104 | ✅ MODIFIED | Added send_audio_autoresponse task |
| `backend/app/workers/scheduled_tasks.py` | 307 | ✅ MODIFIED | Added send_promotion_broadcast task |
| `backend/app/workers/__init__.py` | - | ✅ EXISTING | Workers init (unchanged) |

---

## Configuration Files

| File Path | Lines | Status | Description |
|-----------|-------|--------|-------------|
| `backend/requirements.txt` | 14 | ✅ MODIFIED | Added: openpyxl, mercadopago, gspread |
| `backend/.env` | 22 | ✅ MODIFIED | Added: MERCADOPAGO_ACCESS_TOKEN, MERCADOPAGO_WEBHOOK_SECRET |
| `docker-compose.yml` | - | ✅ EXISTING | No changes needed (already complete) |
| `backend/Dockerfile` | - | ✅ EXISTING | No changes needed |
| `docker/init.sql` | - | ✅ EXISTING | Database initialization (already sets up leadqualifier DB) |

---

## Documentation

| File Path | Lines | Status | Description |
|-----------|-------|--------|-------------|
| `IMPLEMENTATION_SUMMARY.md` | 428 | ✅ NEW | Complete implementation guide + architecture |
| `QUICK_START.md` | ~250 | ✅ NEW | 5-step quick start + common tasks |
| `FILE_MANIFEST.md` | - | ✅ NEW | This file - complete file listing |

---

## Summary by Type

### New Files Created (11)
- Client configuration: 2
- Services: 3
- Database: 2
- Documentation: 3
- (plus this manifest)

### Modified Files (5)
- `backend/app/agent.py`
- `backend/app/main.py`
- `backend/app/config.py`
- `backend/app/routers/whatsapp_router.py`
- `backend/app/workers/tasks.py`
- `backend/app/workers/scheduled_tasks.py`
- `backend/requirements.txt`
- `backend/.env`

### Unchanged Files (Existing)
- Company config loader
- Evolution API service
- Cache service
- Celery configuration
- Docker setup

---

## Database Tables (9 total)

Created in `backend/app/models.py`:

1. **contact** - Customer/client records
2. **product** - Beverage catalog
3. **customer_order** - Purchase orders
4. **payment** - Payment tracking (Mercado Pago)
5. **conversation** - Message history
6. **broadcast_log** - Promotion broadcast tracking
7. **promotion** - Campaign definitions
8. **agent_config** - Multi-tenant agent settings

---

## Key Functions by Module

### agent.py
- `build_system_prompt(cfg: dict) -> str` - Main function for dynamic prompts

### database.py
- `get_engine()` - SQLAlchemy engine factory
- `init_db()` - Auto-create tables
- `get_db()` - FastAPI dependency

### contact_import_service.py
- `import_from_excel(file_path, source_name)` - Excel import
- `import_from_google_sheets(sheet_url, source_name)` - Google Sheets import
- `normalize_phone(phone_str, country_code)` - International format (+54...)

### order_service.py
- `detect_purchase_intent(message)` - Purchase detection
- `check_availability(product_name, quantity)` - Stock validation
- `create_order_draft(contact_id, items, address)` - Order creation
- `confirm_order(order_id)` - Order finalization + stock decrement

### payment_service.py
- `generate_checkout_link(order_id, db)` - Mercado Pago link generation
- `send_payment_link_to_customer(phone, checkout_url)` - WhatsApp send
- `handle_payment_approved/rejected/expired()` - Webhook handlers
- `verify_webhook_signature()` - HMAC-SHA256 validation

### whatsapp_router.py
- `_detect_audio_message(data)` - Audio detection
- `_save_or_update_contact(phone, push_name)` - Contact persistence
- `whatsapp_webhook(request)` - Main webhook handler

### scheduled_tasks.py
- `send_promotion_broadcast()` - Mass broadcast task
- `update_broadcast_reply_count()` - Reply tracking
- `send_followup_inactive_leads()` - Follow-up task (existing)

### tasks.py
- `process_whatsapp_message()` - Message processing (existing)
- `send_audio_autoresponse()` - Audio auto-reply (new)

---

## Quick Reference

### Configuration Files to Update
```
backend/.env → CLIENT=jb_bebidas (change from clinica-estetica)
backend/.env → MERCADOPAGO_ACCESS_TOKEN (add token)
backend/.env → MERCADOPAGO_WEBHOOK_SECRET (add secret)
backend/.env → OWNER_PHONE (optional, for notifications)
```

### Required Environment Variables
```
OPENAI_API_KEY=sk-proj-...
OPENAI_MODEL=gpt-4.1-mini
CLIENT=jb_bebidas
EVOLUTION_API_URL=http://localhost:8080
EVOLUTION_API_KEY=...
EVOLUTION_INSTANCE=jb-bebidas
REDIS_URL=redis://localhost:6379/0
POSTGRES_URL=postgresql://evolution:evolution@localhost:5432/leadqualifier
MERCADOPAGO_ACCESS_TOKEN=APP_USR-...
MERCADOPAGO_WEBHOOK_SECRET=...
```

### Key Endpoints
```
POST /chat → Agent chat (OpenAI)
POST /webhook/whatsapp → Evolution API notifications
POST /webhooks/mercadopago → Mercado Pago payments
```

### Database Connection
```
PostgreSQL: localhost:5432/leadqualifier
(user: evolution, password: evolution)
Tables auto-created on first run via init_db()
```

### Celery Tasks
```
process_whatsapp_message() → Message processing
send_audio_autoresponse() → Audio auto-reply
send_promotion_broadcast() → Mass broadcasts
send_followup_inactive_leads() → Follow-ups
```

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0 | 2026-04-04 | Initial complete implementation |

---

## Compatibility

- **Python:** 3.10+
- **PostgreSQL:** 14+
- **Redis:** 7+
- **Docker:** Compose 2.0+
- **OpenAI:** API v2
- **Evolution API:** v2.x
- **Mercado Pago:** SDK 2.2.0+

---

## Related Documentation

- `IMPLEMENTATION_SUMMARY.md` - Full architecture & implementation details
- `QUICK_START.md` - 5-step setup guide + common tasks
- `clients/jb_bebidas/knowledge_base.md` - Agent knowledge base
- `clients/jb_bebidas/config.yaml` - Client configuration

---

**Generated:** 2026-04-04
**Status:** ✅ Complete
