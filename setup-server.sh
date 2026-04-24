#!/bin/bash
# ============================================================
# setup-server.sh
# Configuração inicial do servidor Hetzner (Ubuntu 24.04)
# Rodar UMA VEZ depois de criar o servidor
#
# Uso:
#   chmod +x setup-server.sh
#   ./setup-server.sh
# ============================================================

set -e  # para se qualquer comando falhar

echo "============================================"
echo "  Setup do servidor — JB Bebidas / Juani"
echo "============================================"

# ── 1. Atualiza o sistema ─────────────────────
echo ""
echo "[1/6] Atualizando sistema..."
apt-get update -qq && apt-get upgrade -y -qq

# ── 2. Instala dependências básicas ──────────
echo ""
echo "[2/6] Instalando dependências..."
apt-get install -y -qq \
    curl \
    git \
    ufw \
    htop \
    nano

# ── 3. Instala Docker ─────────────────────────
echo ""
echo "[3/6] Instalando Docker..."
curl -fsSL https://get.docker.com | sh
systemctl enable docker
systemctl start docker

# Adiciona usuário atual ao grupo docker (evita sudo)
usermod -aG docker "$USER" || true

echo "Docker instalado: $(docker --version)"

# ── 4. Configura firewall ─────────────────────
echo ""
echo "[4/6] Configurando firewall..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow ssh          # SSH (porta 22)
ufw allow 8080/tcp     # Evolution API dashboard
ufw allow 8000/tcp     # FastAPI (opcional — para testes)
ufw --force enable

echo "Firewall configurado."

# ── 5. Clona o repositório ────────────────────
echo ""
echo "[5/6] Clonando repositório..."
if [ ! -d "/opt/lead-qualifier" ]; then
    git clone https://github.com/SEU_USUARIO/lead-qualifier.git /opt/lead-qualifier
    echo "Repositório clonado em /opt/lead-qualifier"
else
    echo "Repositório já existe em /opt/lead-qualifier"
fi

# ── 6. Instrução final ────────────────────────
echo ""
echo "[6/6] Setup concluído!"
echo ""
echo "============================================"
echo "  PRÓXIMOS PASSOS:"
echo "============================================"
echo ""
echo "1. Entre na pasta do projeto:"
echo "   cd /opt/lead-qualifier"
echo ""
echo "2. Crie o arquivo de ambiente:"
echo "   cp backend/.env.production.example backend/.env.production"
echo "   nano backend/.env.production"
echo "   (preencha OPENAI_API_KEY, EVOLUTION_API_KEY, etc.)"
echo ""
echo "3. Crie o arquivo .env na raiz (para docker-compose.prod.yml):"
echo "   echo 'SERVER_IP=<IP_DO_SEU_SERVIDOR>' > .env"
echo "   echo 'EVOLUTION_API_KEY=<SUA_CHAVE>' >> .env"
echo "   echo 'POSTGRES_PASSWORD=<SENHA_SEGURA>' >> .env"
echo ""
echo "4. Suba os serviços:"
echo "   docker compose -f docker-compose.prod.yml up -d --build"
echo ""
echo "5. Verifique se está tudo rodando:"
echo "   docker compose -f docker-compose.prod.yml ps"
echo ""
echo "6. Veja os logs:"
echo "   docker compose -f docker-compose.prod.yml logs -f"
echo "============================================"
