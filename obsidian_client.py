import os
import requests
import logging
from urllib.parse import quote
from dotenv import load_dotenv
import re

load_dotenv()

logger = logging.getLogger("ArgosObsidian")

def sanitize_filename(title: str) -> str:
    """Sanitiza el título para usarlo como nombre de archivo."""
    # Eliminar caracteres inválidos en nombres de archivos
    sanitized = re.sub(r'[<>:"/\\|?*]', '', title)
    # Limitar longitud
    return sanitized[:100].strip()

def extract_title_from_note(note_content: str) -> str:
    """Extrae el título H1 (# Título) de la nota."""
    for line in note_content.split('\n'):
        if line.startswith('# '):
            return line[2:].strip()
    return "Jules_Nota_Generada"

def send_to_obsidian(note_content: str) -> bool:
    """
    Envía la nota a la API REST Local de Obsidian.
    URL Base: ej. http://localhost:27123/00_Inbox/
    """
    base_url = os.environ.get("OBSIDIAN_INBOX_URL")
    if not base_url:
        logger.error("OBSIDIAN_INBOX_URL no configurada.")
        return False

    title = extract_title_from_note(note_content)
    filename = f"{sanitize_filename(title)}.md"

    # Asegurar que la URL termine en '/'
    if not base_url.endswith('/'):
        base_url += '/'

    url = f"{base_url}{quote(filename)}"
    logger.info(f"Enviando nota a Obsidian: {url}")

    api_key = os.environ.get("OBSIDIAN_API_KEY")
    headers = {
        "Content-Type": "text/markdown",
        **({"Authorization": f"Bearer {api_key}"} if api_key else {})
    }

    try:
        response = requests.post(url, headers=headers, data=note_content.encode('utf-8'))

        if response.status_code in [200, 201, 204]:
            logger.info(f"Nota '{filename}' guardada exitosamente en Obsidian.")
            return True
        else:
            logger.error(f"Fallo al guardar en Obsidian. Código: {response.status_code}. Respuesta: {response.text}")
            return False

    except requests.exceptions.ConnectionError:
        logger.error("No se pudo conectar a la API de Obsidian. ¿Está abierto Obsidian y el plugin Local REST API activado?")
        return False
    except Exception as e:
        logger.error(f"Error inesperado conectando con Obsidian: {e}")
        return False
