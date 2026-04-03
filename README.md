# lead-qualifier

Agente de qualificação de leads customizável por empresa, com memória de conversa e interface de chat.

## Estrutura

```
lead-qualifier/
├── backend/        FastAPI + Agno (Python)
├── frontend/       Interface de chat (Next.js)
├── clients/        Configurações por empresa
└── .gitignore
```

## Adicionar um novo cliente

1. Crie uma pasta em `clients/nome-do-cliente/`
2. Copie e preencha `config.yaml` baseado no exemplo de `clinica-estetica`
3. No `.env` do backend, defina `CLIENT=nome-do-cliente`
4. Reinicie o servidor

## Rodar localmente

**Backend:**
```bash
cd backend
python -m venv .venv
.venv\Scripts\activate        # Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

**Frontend:**
```bash
cd frontend
npm install
npm run dev
```
