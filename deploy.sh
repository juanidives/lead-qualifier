#!/bin/bash
# ============================================================
# deploy.sh
# Atualiza o servidor com a versão mais recente do GitHub
#
# Uso (no servidor):
#   ./deploy.sh
# ============================================================

set -e

echo "============================================"
echo "  Deploy — JB Bebidas / Juani"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"
echo "============================================"

cd /opt/lead-qualifier

# ── 1. Puxa última versão do git ──────────────
echo ""
echo "[1/4] Atualizando código..."
git pull origin main

# ── 2. Rebuild das imagens ────────────────────
echo ""
echo "[2/4] Rebuilding imagens Docker..."
docker compose -f docker-compose.prod.yml build --no-cache fastapi celery-worker

# ── 3. Reinicia os serviços ───────────────────
echo ""
echo "[3/4] Reiniciando serviços..."
docker compose -f docker-compose.prod.yml up -d

# ── 4. Verifica status ────────────────────────
echo ""
echo "[4/4] Status dos serviços:"
docker compose -f docker-compose.prod.yml ps

echo ""
echo "✅ Deploy concluído!"
echo ""
echo "Para ver os logs:"
echo "  docker compose -f docker-compose.prod.yml logs -f fastapi"
echo "  docker compose -f docker-compose.prod.yml logs -f celery-worker"
