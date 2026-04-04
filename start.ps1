# Aguarda o Docker estar pronto
Start-Sleep -Seconds 10

# Inicia o FastAPI
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd C:\Workspace\ia\lead-qualifier\backend; .\.venv\Scripts\Activate.ps1; uvicorn app.main:app --host 0.0.0.0 --port 8000"
)

# Inicia o Celery Worker
Start-Process powershell -ArgumentList @(
    "-NoExit", "-Command",
    "cd C:\Workspace\ia\lead-qualifier\backend; .\.venv\Scripts\Activate.ps1; celery -A app.workers.celery_app worker --loglevel=info"
)