# Guia de Teste — Agente Juani (JB Bebidas)

**Para:** Cliente JB Bebidas
**Versão:** Abril 2026

---

## Antes de começar — checklist rápido

Antes de testar, confirme que tudo está rodando. Abra o PowerShell e rode:

```
docker ps
```

Deve mostrar 3 containers com status `Up`:
- `evolution-api`
- `postgres`
- `redis`

Depois abra o navegador em `http://localhost:8000/docs` — se abrir a documentação da API, o backend está OK.

Se algum dos dois falhar, veja a seção **"E se não funcionar?"** no final.

---

## Opção 1 — Testar pelo chat visual (mais fácil)

### Passo 1 — Abrir o PowerShell na pasta do frontend
```
cd C:\Workspace\ia\lead-qualifier\frontend
npm run dev
```

Deixe esse terminal aberto.

### Passo 2 — Abrir o chat no navegador
```
http://localhost:3000
```

O cabeçalho deve mostrar **Juani** e a descrição **distribuidora de bebidas**.

### Passo 3 — Conversar com o Juani

Experimente estas mensagens em ordem para testar o fluxo completo:

| Mensagem | O que você está testando |
|---|---|
| `Hola, qué cervezas tienen?` | Apresentação e catálogo |
| `Cuánto sale la Quilmes 1L?` | Consulta de preço |
| `Y el Fernet Branca?` | Produto específico |
| `Tienen algún combo?` | Promoções e combos |
| `Quiero pedir 2 Quilmes y 1 Coca` | Início do pedido |
| `Cómo pagan?` | Forma de pagamento |
| `Mi dirección es Av. Corrientes 1234, CABA` | Coleta de endereço |

O agente deve responder em espanhol argentino, com "vos", sugerir produtos complementares e fechar o pedido de forma natural.

---

## Opção 2 — Testar via WhatsApp (simulação por PowerShell)

Abra o PowerShell **em qualquer pasta** e rode:

```powershell
Invoke-WebRequest -Uri "http://localhost:8000/webhook/whatsapp" -Method POST -ContentType "application/json" -Body '{"event":"MESSAGES_UPSERT","instance":"jb-bebidas","data":{"key":{"remoteJid":"5491199990000@s.whatsapp.net","fromMe":false,"id":"TEST001"},"pushName":"Juan","message":{"conversation":"Hola! Que cervezas tienen?"}}}' -UseBasicParsing
```

Resposta esperada: `{"status":"queued","phone":"5491199990000"}`

A resposta do Juani aparece no terminal onde o uvicorn está rodando (procure a linha `[Celery] Resposta enviada para...`).

Para simular mensagens diferentes, mude o texto dentro de `"conversation":"..."`.

---

## Opção 3 — Testar via WhatsApp real

> Esta opção requer que o número de WhatsApp da JB Bebidas esteja conectado na Evolution API.

### Conectar o número (fazer uma vez)

1. Abra: `http://localhost:8080/manager`
   API Key: `minha-chave-secreta`

2. Clique em **Create Instance**
   - Nome: `jb-bebidas`
   - Integration: `WHATSAPP-BAILEYS`
   - Salvar

3. Clique na instância → **Connect**
   Aparece o QR code

4. No celular com o número da JB:
   WhatsApp → 3 pontinhos → **Aparelhos conectados** → **Conectar aparelho**
   Escaneie o QR

5. Status deve mudar para `open` ou `connected`

6. Configure o webhook:
   Settings → Webhook
   - URL: `http://host.docker.internal:8000/webhook/whatsapp`
   - Evento: `MESSAGES_UPSERT`
   - Salvar

A partir desse momento, qualquer mensagem enviada para o número da JB é respondida automaticamente pelo Juani.

---

## O que o Juani sabe fazer

- Apresentar o catálogo de bebidas (10 produtos disponíveis)
- Informar preços e disponibilidade em estoque
- Sugerir combos e promoções ativas
- Sugerir produtos complementares (ex: Fernet → Coca-Cola)
- Conduzir o pedido coletando nome, endereço e itens
- Encaminhar pedidos grandes (+$15.000 ARS) para o dono
- Responder sobre política de entrega e horários
- Responder em espanhol argentino casual ("vos", "che", "bro")

---

## Produtos disponíveis para testar

| Produto | Preço |
|---|---|
| Quilmes Clásica 1L | $850 |
| Corona Extra 355ml | $1.200 |
| Fernet Branca 750ml | $4.500 |
| Aperol 700ml | $5.200 |
| Chandon Extra Brut 750ml | $6.800 |
| Malbec Rutini 750ml | $8.500 |
| Vodka Smirnoff 750ml | $4.200 |
| Coca-Cola 1.5L | $650 |
| Soda Schweppes 1.5L | $550 |
| Six Pack Quilmes Lata 473ml | $3.800 |

**Combos ativos:**
- Pack Fernet-Coca: Fernet 750ml + 2 Coca 1.5L → $5.500 (economia de $450)
- Pack Aperol Spritz: Aperol + Chandon + Soda → $11.500 (economia de $1.000)
- Envio grátis acima de $5.000 em CABA e GBA
- 10% de desconto acima de $15.000

---

## E se não funcionar?

**O chat abre mas não aparece "Juani" no cabeçalho:**
O backend não está rodando. Suba o uvicorn:
```
cd C:\Workspace\ia\lead-qualifier\backend
.\.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

**O agente não responde:**
Verifique se o Celery está rodando em um segundo terminal:
```
cd C:\Workspace\ia\lead-qualifier\backend
.\.venv\Scripts\Activate.ps1
celery -A app.workers.celery_app worker --loglevel=info
```

**Os containers não estão `Up`:**
```
cd C:\Workspace\ia\lead-qualifier
docker compose up -d
```

**O agente responde como "Sofia":**
Confirme que `backend/.env` tem `CLIENT=jb_bebidas` e reinicie o uvicorn.
