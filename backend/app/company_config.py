import os
from pathlib import Path
import yaml


def load_client_config() -> dict:
    """
    Carrega a configuração do cliente ativo.
    O cliente é definido pela variável de ambiente CLIENT no .env.
    Exemplo: CLIENT=clinica-estetica
    """
    client = os.getenv("CLIENT", "clinica-estetica")
    config_path = Path(__file__).parent.parent.parent / "clients" / client / "config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuração do cliente '{client}' não encontrada em {config_path}.\n"
            f"Crie o arquivo clients/{client}/config.yaml baseado no exemplo em clients/.env.example"
        )

    with open(config_path, encoding="utf-8") as f:
        return yaml.safe_load(f)


# Carregado uma vez na inicialização do servidor
config = load_client_config()
