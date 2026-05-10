#!/usr/bin/env python3
"""
Monitor de conexão WhatsApp — roda todo dia às 18h
Verifica se a instância está conectada e avisa os owners se não estiver.
"""
import os
import requests

EVOLUTION_API_URL = os.getenv("EVOLUTION_API_URL", "http://localhost:8080")
EVOLUTION_API_KEY = os.getenv("EVOLUTION_API_KEY", "minha-chave-secreta")
EVOLUTION_INSTANCE = os.getenv("EVOLUTION_INSTANCE", "jb-bebidas")
OWNER_PHONE = os.getenv("OWNER_PHONE", "5493625276313")

def check_connection() -> bool:
    """Retorna True se a instância está conectada."""
    url = f"{EVOLUTION_API_URL}/instance/connectionState/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY}
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        data = resp.json()
        state = data.get("instance", {}).get("state", "")
        return state == "open"
    except Exception as e:
        print(f"Erro ao checar conexão: {e}")
        return False

def send_alert(phone: str):
    """Manda mensagem de alerta para o owner."""
    url = f"{EVOLUTION_API_URL}/message/sendText/{EVOLUTION_INSTANCE}"
    headers = {"apikey": EVOLUTION_API_KEY, "Content-Type": "application/json"}
    payload = {
        "number": phone,
        "text": (
            "⚠️ *ALERTA — Bot desconectado*\n\n"
            "O WhatsApp do JB Bebidas está *desconectado*.\n"
            "O bot não está respondendo clientes.\n\n"
            "Para reconectar:\n"
            "1. Acesse http://5.75.170.67:8080/manager\n"
            "2. Entre na instância *jb-bebidas*\n"
            "3. Clique em *Get QR Code*\n"
            "4. Escaneie com o celular do JB Bebidas"
        )
    }
    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"Alerta enviado para {phone}: {resp.status_code}")
    except Exception as e:
        print(f"Erro ao enviar alerta para {phone}: {e}")

if __name__ == "__main__":
    print(f"Verificando conexão da instância '{EVOLUTION_INSTANCE}'...")
    connected = check_connection()
    if connected:
        print("✅ WhatsApp conectado — tudo ok.")
    else:
        print("❌ WhatsApp desconectado — enviando alertas...")
        for phone in OWNER_PHONE.split(","):
            send_alert(phone.strip())
