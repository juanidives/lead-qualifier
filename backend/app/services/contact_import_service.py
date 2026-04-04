"""
contact_import_service.py
------------------------
Serviço para importar contatos de planilhas (Excel/Google Sheets).
Normaliza números telefônicos, evita duplicatas e salva no banco de dados.
"""

import logging
import re
from datetime import datetime
from typing import Optional, Tuple
import httpx
import openpyxl

logger = logging.getLogger(__name__)


def normalize_phone(phone_str: str, country_code: str = "54") -> Optional[str]:
    """
    Normaliza número telefônico para formato internacional.

    Exemplos:
      - "1100000000" → "+541100000000"
      - "11 99999-0000" → "+5511999990000"
      - "5491199990000" → "+5491199990000"
      - "+5491199990000" → "+5491199990000"

    Args:
        phone_str: número em qualquer formato
        country_code: código do país (padrão: 54 para Argentina)

    Returns:
        Número normalizado com + ou None se inválido
    """
    if not phone_str:
        return None

    # Remove caracteres não-numéricos, menos o + no início
    phone = re.sub(r'[^\d\+]', '', str(phone_str).strip())

    # Se começar com +, mantém como está (já internacional)
    if phone.startswith('+'):
        return phone

    # Se começar com código do país, adiciona +
    if phone.startswith(country_code):
        return f"+{phone}"

    # Caso contrário, assume que é número local e adiciona código
    if len(phone) >= 10:
        return f"+{country_code}{phone}"

    logger.warning(f"Número inválido: {phone_str}")
    return None


def import_from_excel(file_path: str, source_name: str = "excel_import") -> dict:
    """
    Importa contatos de arquivo .xlsx (Excel).

    Espera colunas: nombre, telefono, ciudad (obrigatórias)
    Opcional: upselling (produtos recomendados, separados por vírgula)

    Args:
        file_path: caminho absoluto ao arquivo .xlsx
        source_name: origem para rastreamento (ex: "excel_import", "planilha_01")

    Returns:
        {
            'total_imported': int,
            'duplicates_ignored': int,
            'errors': list,
            'contacts': list[dict]
        }
    """
    result = {
        'total_imported': 0,
        'duplicates_ignored': 0,
        'errors': [],
        'contacts': []
    }

    try:
        workbook = openpyxl.load_workbook(file_path, data_only=True)
        worksheet = workbook.active

        # Mapeia as colunas esperadas
        headers = {}
        for col_idx, cell in enumerate(worksheet[1], start=1):
            if cell.value:
                headers[cell.value.lower().strip()] = col_idx - 1

        # Valida colunas obrigatórias
        required_cols = ['nombre', 'telefono', 'ciudad']
        for req_col in required_cols:
            if req_col not in headers:
                result['errors'].append(f"Coluna obrigatória ausente: {req_col}")
                return result

        # Processa linhas de dados
        seen_phones = set()
        for row_idx, row in enumerate(worksheet.iter_rows(min_row=2, values_only=False), start=2):
            try:
                # Extrai valores de cada coluna
                nombre = row[headers['nombre']].value
                telefono_raw = row[headers['telefono']].value
                ciudad = row[headers['ciudad']].value

                # Valida campos obrigatórios
                if not nombre or not telefono_raw or not ciudad:
                    result['errors'].append(f"Linha {row_idx}: campos obrigatórios vazios")
                    continue

                # Normaliza telefone
                telefono = normalize_phone(str(telefono_raw))
                if not telefono:
                    result['errors'].append(f"Linha {row_idx}: telefone inválido ({telefono_raw})")
                    continue

                # Verifica duplicata nesta importação
                if telefono in seen_phones:
                    result['duplicates_ignored'] += 1
                    continue
                seen_phones.add(telefono)

                # Extrai upselling se presente
                upselling = None
                if 'upselling' in headers:
                    upselling_raw = row[headers['upselling']].value
                    if upselling_raw:
                        upselling = [p.strip() for p in str(upselling_raw).split(',')]

                contact = {
                    'name': str(nombre).strip(),
                    'phone': telefono,
                    'city': str(ciudad).strip(),
                    'source': source_name,
                    'created_at': datetime.utcnow(),
                    'is_active': True,
                    'upselling': upselling
                }

                result['contacts'].append(contact)
                result['total_imported'] += 1

            except Exception as e:
                result['errors'].append(f"Linha {row_idx}: {str(e)}")
                continue

        workbook.close()

    except Exception as e:
        result['errors'].append(f"Erro ao abrir arquivo: {str(e)}")

    return result


def import_from_google_sheets(sheet_url: str, source_name: str = "google_sheets") -> dict:
    """
    Importa contatos de Google Sheets via URL de exportação CSV.

    Uso:
      1. Abra a planilha no Google Sheets
      2. Copie a URL
      3. Modifique para: https://docs.google.com/spreadsheets/d/{ID}/export?format=csv

    Args:
        sheet_url: URL pública ou URL de exportação CSV
        source_name: origem para rastreamento

    Returns:
        Mesmo formato que import_from_excel()
    """
    result = {
        'total_imported': 0,
        'duplicates_ignored': 0,
        'errors': [],
        'contacts': []
    }

    try:
        # Se for URL normal, converte para exportação CSV
        if 'docs.google.com/spreadsheets' in sheet_url and 'export' not in sheet_url:
            sheet_id = sheet_url.split('/d/')[1].split('/')[0]
            sheet_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv"

        # Faz download do CSV
        with httpx.Client(timeout=30) as client:
            response = client.get(sheet_url)
            response.raise_for_status()
            csv_content = response.text

        # Processa CSV
        lines = csv_content.strip().split('\n')
        if not lines:
            result['errors'].append("Arquivo CSV vazio")
            return result

        # Parse do header
        headers = {}
        header_cells = lines[0].split(',')
        for col_idx, cell in enumerate(header_cells):
            headers[cell.lower().strip()] = col_idx

        # Valida colunas obrigatórias
        required_cols = ['nombre', 'telefono', 'ciudad']
        for req_col in required_cols:
            if req_col not in headers:
                result['errors'].append(f"Coluna obrigatória ausente: {req_col}")
                return result

        # Processa linhas de dados
        seen_phones = set()
        for line_idx, line in enumerate(lines[1:], start=2):
            try:
                cells = line.split(',')

                nombre = cells[headers['nombre']].strip() if headers['nombre'] < len(cells) else ''
                telefono_raw = cells[headers['telefono']].strip() if headers['telefono'] < len(cells) else ''
                ciudad = cells[headers['ciudad']].strip() if headers['ciudad'] < len(cells) else ''

                if not nombre or not telefono_raw or not ciudad:
                    result['errors'].append(f"Linha {line_idx}: campos obrigatórios vazios")
                    continue

                telefono = normalize_phone(telefono_raw)
                if not telefono:
                    result['errors'].append(f"Linha {line_idx}: telefone inválido ({telefono_raw})")
                    continue

                if telefono in seen_phones:
                    result['duplicates_ignored'] += 1
                    continue
                seen_phones.add(telefono)

                upselling = None
                if 'upselling' in headers:
                    upselling_raw = cells[headers['upselling']].strip() if headers['upselling'] < len(cells) else ''
                    if upselling_raw:
                        upselling = [p.strip() for p in upselling_raw.split(',')]

                contact = {
                    'name': nombre,
                    'phone': telefono,
                    'city': ciudad,
                    'source': source_name,
                    'created_at': datetime.utcnow(),
                    'is_active': True,
                    'upselling': upselling
                }

                result['contacts'].append(contact)
                result['total_imported'] += 1

            except Exception as e:
                result['errors'].append(f"Linha {line_idx}: {str(e)}")
                continue

    except Exception as e:
        result['errors'].append(f"Erro ao baixar/processar Google Sheet: {str(e)}")

    return result


def import_products_from_sheet(sheet_url: str) -> dict:
    """
    Importa produtos de aba 'productos' em Google Sheets.

    Espera colunas: product_name, category, price, cost_price, alcohol,
    stock_quantity, is_available, description, upselling (JSON array)

    Returns:
        {
            'total_imported': int,
            'errors': list,
            'products': list[dict]
        }
    """
    result = {
        'total_imported': 0,
        'errors': [],
        'products': []
    }

    # TODO: implementar quando necessário
    # Por enquanto, retorna vazio
    result['errors'].append("Importação de produtos ainda não implementada")

    return result
