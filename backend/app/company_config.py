import os
from pathlib import Path
import yaml


def load_client_config() -> dict:
    """
    Carrega a configuração do cliente ativo.
    O cliente é definido pela variável de ambiente CLIENT no .env.
    Exemplo: CLIENT=clinica-estetica

    Também carrega o knowledge_base.md se existir, e o injeta
    no campo 'knowledge_base' do dicionário retornado.
    """
    client = os.getenv("CLIENT", "clinica-estetica")
    client_dir = Path(__file__).parent.parent.parent / "clients" / client
    config_path = client_dir / "config.yaml"

    if not config_path.exists():
        raise FileNotFoundError(
            f"Configuração do cliente '{client}' não encontrada em {config_path}.\n"
            f"Crie o arquivo clients/{client}/config.yaml baseado no exemplo em clients/.env.example"
        )

    with open(config_path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Carrega knowledge_base.md se existir para o cliente
    kb_path = client_dir / "knowledge_base.md"
    if kb_path.exists():
        with open(kb_path, encoding="utf-8") as f:
            cfg["knowledge_base"] = f.read()
    else:
        cfg["knowledge_base"] = ""

    return cfg


# Carregado uma vez na inicialização do servidor
config = load_client_config()
