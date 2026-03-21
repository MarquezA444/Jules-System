import os
import re
from typing import List, Dict

def search_local_files(query: str, root_dirs: List[str], max_results: int = 3) -> List[Dict]:
    """
    Busca palabras clave en los archivos locales y devuelve fragmentos relevantes.
    """
    results = []
    # Stop words comunes en español/inglés para consultas conversacionales
    STOP_WORDS = {
        "puedes", "hablarme", "hablame", "acerca", "del", "los", "las", "una", "unos", 
        "unas", "como", "cuando", "donde", "quien", "cual", "que", "para", "con", "por", 
        "sobre", "explicar", "explica", "dime", "info", "informacion", "buscar", "esto", 
        "este", "esta", "esos", "esas", "aquel", "cuentame", "sirve", "hace", "dentro",
        "tiene", "tienen", "estoy", "esta", "estan", "eres", "soy", "ayuda", "ayudame",
        "dame", "detalle", "detalles", "alguna", "algun", "alguno", "hola", "algo", "dice"
    }

    # Extract alphanumeric words only, strictly >= 3 chars, and NOT in stop words
    keywords = [k.lower() for k in re.findall(r'\b\w+\b', query) if len(k) >= 3 and k.lower() not in STOP_WORDS]
    
    if not keywords:
        return []

    processed_count = 0
    for root in root_dirs:
        if not os.path.exists(root):
            continue
            
        for dirpath, dirs, filenames in os.walk(root):
            # Ignorar carpetas comunes de dependencias
            if any(x in dirpath for x in ["venv", ".git", "__pycache__", "node_modules", ".obsidian"]):
                dirs[:] = [] # Evitar entrar en estas carpetas
                continue
                
            for f in filenames:
                if f.endswith((".py", ".md", ".txt", ".js", ".ts", ".json")):
                    fullpath = os.path.join(dirpath, f)
                    try:
                        with open(fullpath, "r", encoding="utf-8") as file:
                            content = file.read()
                            content_lower = content.lower()
                            
                            # Score is weighted by the length of the matching keyword to favor technical terms
                            score = 0
                            found_kws = []
                            for kw in keywords:
                                if kw in content_lower:
                                    score += len(kw)
                                    found_kws.append(kw)
                                    
                            if score > 0:
                                # Buscar el hit de la palabra más larga encontrada para centrar el snippet
                                longest_kw = max(found_kws, key=len)
                                first_hit_pos = content_lower.find(longest_kw)
                                
                                start = max(0, first_hit_pos - 200)
                                end = min(len(content), first_hit_pos + 600)
                                snippet = content[start:end]
                                if start > 0: snippet = "..." + snippet
                                if end < len(content): snippet = snippet + "..."

                                results.append({
                                    "path": fullpath,
                                    "hits": score, # using hits key for sorting
                                    "content": snippet
                                })
                                processed_count += 1
                                
                    except (UnicodeDecodeError, PermissionError):
                        continue
                        
                if processed_count >= max_results * 2: # Buscar un poco más para luego filtrar por 'hits'
                    break
            if processed_count >= max_results * 2:
                break

    # Sort by hits and return top results
    results.sort(key=lambda x: x["hits"], reverse=True)
    return results[:max_results]
