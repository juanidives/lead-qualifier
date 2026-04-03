"""
evolution_service.py
--------------------
Cliente HTTP para a Evolution API v2.
Responsável por enviar mensagens de volta ao WhatsApp.
"""

import re
import httpx
from app.config import EVOLUTION_API_URL, EVOLUTION_API_KEY, EVOLUTION_INSTANCE


def send_text_message(phone: str, text: str) -> dict:
    """
    Envia uma mensagem de texto via Evolution API.

    Args:
        phone: número no formato internacional, ex: "5511999990000"
               (sem @s.whatsapp.net — a Evolution API formata sozinha)
        text:  conteúdo da mensagem

    Returns:
        JSON de resposta da API.

    Raises:
        httpx.HTTPStatusError: se a API retornar erro HTTP.
    """
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"

    headers = {
        "apikey": EVOLUTION_API_KEY,
        "Content-Type": "application/json",
    }

    payload = {
        "number": phone,
        "text": text,
    }

    with httpx.Client(timeout=30) as client:
        response = client.post(url, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()


def strip_markdown(text: str) -> str:
    """
    Converte formatação Markdown para o formato nativo do WhatsApp.
    WhatsApp usa *negrito*, _itálico_ e ~tachado~ nativamente.
    """
    # Remove headers markdown (## Título → linha simples)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # Converte **negrito** → *negrito* (formato WhatsApp)
    text = re.sub(r"\*\*(.+?)\*\*", r"*\1*", text)
    # Converte bullets markdown → bullet unicode
    text = re.sub(r"^[-*]\s+", "• ", text, flags=re.MULTILINE)
    # Remove linhas em branco duplas
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()
