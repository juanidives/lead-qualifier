# Deploy — JB Bebidas Agent

## Servidor
- **Provider:** Hetzner Cloud
- **IP:** 5.75.170.67
- **Tipo:** CPX22 (3 vCPU, 4GB RAM)
- **OS:** Ubuntu 24.04

## Acesso
```bash
ssh root@5.75.170.67
```

## Estrutura no servidor
```
/opt/lead-qualifier/          ← repositório git
/opt/lead-qualifier/backend/.env      ← NÃO está no git, criado manualmente
/opt/lead-qualifier/clients/          ← NÃO está no git, copiado via scp
/opt/lead-qualifier/docker-compose.prod.yml  ← NÃO está no git, criado manualmente
```

## Containers rodando
| Container      | Porta | Descrição                  |
|----------------|-------|----------------------------|
| fastapi        | 8000  | API + webhook WhatsApp     |
| celery-worker  | —     | Processamento em background|
| evolution-api  | 8080  | Gateway WhatsApp           |
| postgres       | —     | Banco de dados (interno)   |
| redis          | —     | Cache + broker (interno)   |

## Deploy de atualização de código
Quando fizer mudanças no código local e der push no git:

```bash
ssh root@5.75.170.67
cd /opt/lead-qualifier
git pull
docker compose -f docker-compose.prod.yml up -d --build fastapi celery-worker
```

## Se mudar o clients/ localmente
Precisa copiar manualmente via scp (não está no git):
```bash
scp -r C:\Workspace\ia\lead-qualifier\clients root@5.75.170.67:/opt/lead-qualifier/clients
```
Depois reiniciar:
```bash
ssh root@5.75.170.67
cd /opt/lead-qualifier
docker compose -f docker-compose.prod.yml restart fastapi celery-worker
```

## Se mudar o .env localmente
Editar diretamente no servidor:
```bash
ssh root@5.75.170.67
nano /opt/lead-qualifier/backend/.env
docker compose -f docker-compose.prod.yml restart fastapi celery-worker
```

## Evolution API Manager
- URL: http://5.75.170.67:8080/manager
- Instância: jb-bebidas
- API Key: minha-chave-secreta
- Webhook: http://5.75.170.67:8000/webhook/whatsapp

## Ver logs em tempo real
```bash
# FastAPI
docker logs -f fastapi

# Celery
docker logs -f celery-worker

# Todos juntos
docker compose -f docker-compose.prod.yml logs -f
```

## Reiniciar tudo
```bash
docker compose -f docker-compose.prod.yml restart
```

## Status dos containers
```bash
docker compose -f docker-compose.prod.yml ps
```
