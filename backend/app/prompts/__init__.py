"""
prompts/__init__.py
--------------------
Factory de builders de system prompt por vertical.

Como funciona:
  1. Cada cliente declara client_type no seu config.yaml
  2. get_prompt_builder(client_type) retorna a função construtora correta
  3. agent.py chama builder(config) e obtém o prompt pronto

Para adicionar uma nova vertical (ex: imobiliária):
  1. Crie backend/app/prompts/real_estate.py com build_real_estate_prompt()
  2. Adicione ao dicionário PROMPT_BUILDERS abaixo
  3. Nos novos clientes, use client_type: "real_estate" no config.yaml
"""

from app.prompts.lead_qualifier import build_lead_qualifier_prompt
from app.prompts.beverages import build_beverages_prompt

# Registro de todos os builders disponíveis
# chave: valor do campo client_type no config.yaml
# valor: função que recebe cfg (dict) e retorna o prompt (str)
PROMPT_BUILDERS = {
    "lead_qualifier": build_lead_qualifier_prompt,
    "beverages": build_beverages_prompt,
}


def get_prompt_builder(client_type: str):
    """
    Retorna o builder de prompt correto para o tipo de cliente.

    Args:
        client_type: valor do campo client_type no config.yaml

    Returns:
        Função build_*_prompt correspondente

    Raises:
        ValueError: se o client_type não estiver registrado
    """
    builder = PROMPT_BUILDERS.get(client_type)

    if not builder:
        available = list(PROMPT_BUILDERS.keys())
        raise ValueError(
            f"client_type '{client_type}' não reconhecido. "
            f"Tipos disponíveis: {available}. "
            f"Verifique o campo client_type no config.yaml do cliente."
        )

    return builder
