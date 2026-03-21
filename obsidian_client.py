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

def search_notes(query: str) -> list:
    """
    Busca notas en Obsidian usando el endpoint /search/.
    Retorna una lista de objetos con 'filename', 'score', etc.
    """
    base_url = os.environ.get("OBSIDIAN_INBOX_URL")
    if not base_url: return []
    
    # Extraer el host y puerto de la URL de Inbox
    match = re.search(r'(https?://[^/]+)', base_url)
    if not match: return []
    api_root = match.group(1)
    
    url = f"{api_root}/search/"
    api_key = os.environ.get("OBSIDIAN_API_KEY")
    headers = {
        "Authorization": f"Bearer {api_key}" if api_key else "",
        "Content-Type": "application/vnd.olrapi.jsonlogic+json"
    }
    
    # Stop words comunes en español/inglés
    STOP_WORDS = {
        "puedes", "hablarme", "hablame", "acerca", "del", "los", "las", "una", "unos", 
        "unas", "como", "cuando", "donde", "quien", "cual", "que", "para", "con", "por", 
        "sobre", "explicar", "explica", "dime", "info", "informacion", "buscar", "esto", 
        "este", "esta", "esos", "esas", "aquel", "cuentame", "sirve", "hace", "dentro",
        "tiene", "tienen", "estoy", "esta", "estan", "eres", "soy", "ayuda", "ayudame",
        "dame", "detalle", "detalles", "alguna", "algun", "alguno", "hola", "algo", "dice"
    }

    # Extraer palabras clave válidas (sin puntuación ni stop words)
    keywords = [k for k in re.findall(r'\b\w+\b', query) if len(k) >= 3 and k.lower() not in STOP_WORDS]
    # Usar la palabra más larga como término de búsqueda principal para Obsidian (suele ser el término técnico)
    search_term = max(keywords, key=len) if keywords else query
    
    try:
        # El plugin Local REST API requiere POST y JsonLogic
        payload = {"in": [search_term, {"var": "content"}]}
        response = requests.post(url, headers=headers, json=payload, timeout=5)
        
        if response.status_code == 200:
            all_results = response.json()
            # JsonLogic devuelve [{"filename": "...", "result": True/False}]
            return [res for res in all_results if res.get("result") is True]
        return []
    except Exception as e:
        logger.error(f"Error en search_notes: {e}")
        return []

def format_obsidian_content(text: str) -> str:
    """
    Limpia y formatea el contenido bruto de Obsidian para que el LLM lo entienda mejor.
    Elimina metadatos innecesarios y ruido visual.
    """
    if not text:
        return text
        
    # 1. Eliminar Frontmatter YAML (bloque inicial --- ... ---)
    text = re.sub(r'^---\n.*?\n---\n', '', text, flags=re.DOTALL)
    
    # 2. Eliminar consultas Dataview (bloques ```dataview ... ```)
    text = re.sub(r'```dataview\n.*?\n```', '', text, flags=re.DOTALL)
    
    # 3. Simplificar enlaces Obsidian [[Enlace]] o [[Enlace|Alias]] -> Alias o Enlace
    text = re.sub(r'\[\[(?:[^\]|]+\|)?([^\]]+)\]\]', r'\1', text)
    
    # 4. Eliminar lineas en blanco excesivas
    text = re.sub(r'\n{3,}', '\n\n', text)
    
    return text.strip()

def get_note_content(filepath: str) -> str:
    """
    Obtiene el contenido de una nota específica por su ruta, pre-formateado.
    """
    base_url = os.environ.get("OBSIDIAN_INBOX_URL")
    if not base_url: return ""
    
    match = re.search(r'(https?://[^/]+)', base_url)
    if not match: return ""
    api_root = match.group(1)
    
    # El filepath debe estar URL-encoded
    url = f"{api_root}/vault/{quote(filepath)}"
    api_key = os.environ.get("OBSIDIAN_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 200:
            return format_obsidian_content(response.text)
        return ""
    except Exception:
        return ""
