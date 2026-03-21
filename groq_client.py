import os
import json
import logging
from typing import Dict, Any, Iterator, List
from groq import Groq
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

logger = logging.getLogger("ArgosGroq")

def get_groq_client() -> Groq:
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        logger.error("GROQ_API_KEY no encontrada en las variables de entorno.")
        raise ValueError("GROQ_API_KEY no configurada.")
    return Groq(api_key=api_key)

SYSTEM_PROMPT = """Eres Jules, un asistente de captura de conocimiento técnico (Segundo Cerebro).
Tu objetivo es transformar un fragmento de código con un comentario `@argos` en una nota estructurada para Obsidian.

La salida debe ser ÚNICAMENTE el contenido de la nota en formato Markdown, sin texto adicional antes o después.
El formato DEBE seguir estrictamente esta estructura:

---
date: {fecha_actual}
source_file: {ruta_del_archivo}
project: {nombre_del_proyecto}
language: {lenguaje_detectado}
tags:
  - {etiqueta1-en-kebab-case}
  - {etiqueta2-en-kebab-case}
  - {etiqueta3-en-kebab-case}
---

# {Un título descriptivo y conciso (no solo el nombre del archivo)}

> {Un breve resumen ejecutivo en una oración explicando la idea principal}

## 💡 Concepto / Problema
{Explicación técnica de lo que se resolvió o el concepto principal documentado}

## 🛠️ Implementación / Fragmento
```{lenguaje_detectado_en_minúsculas}
{El bloque de código relevante extraído del contexto}
```
{Comentarios sobre por qué esta solución es buena, mejores prácticas o puntos clave}

---
*Generado por Jules · {fecha_actual}*

REGLAS ESTRICTAS:
1. El frontmatter YAML usa `tags:` en formato de lista YAML (con guión e indentación), NO como array inline.
2. Los tags deben ser kebab-case sin espacios (ej: api-rest, node-js, aws-lambda, postgresql).
3. NO incluyas sección de conexiones ni wikilinks [[]] en el cuerpo. Los tags del frontmatter son suficientes para clasificar.
4. No incluyas los delimitadores ```markdown al principio ni al final del documento completo.
5. Analiza el source_file para extraer el project (directorio raíz del repositorio) y el language.
6. La fecha debe estar en formato YYYY-MM-DD.
7. El título debe ser semántico, no un simple nombre de archivo.
8. El bloque de código debe especificar el lenguaje en minúsculas (javascript, python, sql, etc).
"""

def generate_note(context: str, filepath: str, comment_text: str) -> str:
    try:
        client = get_groq_client()

        from datetime import datetime
        fecha_actual = datetime.now().strftime("%Y-%m-%d")

        user_prompt = f"""
Por favor, genera la nota de Obsidian basada en el siguiente contexto.

Fecha actual: {fecha_actual}
Archivo de origen: {filepath}
Comentario desencadenante: {comment_text}

CONTEXTO DEL CÓDIGO:
```
{context}
```
"""
        logger.info("Enviando solicitud a Groq API (Llama 3.3)...")

        chat_completion = client.chat.completions.create(
            messages=[
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": user_prompt,
                }
            ],
            model="llama-3.3-70b-versatile",
            temperature=0.2, # Baja temperatura para mayor consistencia en el formato
            max_tokens=2048,
        )

        result = chat_completion.choices[0].message.content.strip()

        # Limpiar backticks si el modelo los incluyó por error al inicio y final
        if result.startswith("```markdown"):
            result = result[11:].strip()
        elif result.startswith("```"):
            result = result[3:].strip()

        if result.endswith("```"):
            result = result[:-3].strip()

        return result

    except Exception as e:
        logger.error(f"Error al generar nota con Groq: {e}")
        raise


def stream_chat(
    messages: List[dict],
    model: str = "llama-3.3-70b-versatile",
    temperature: float = 0.7,
) -> Iterator[str]:
    """
    Yields text tokens from the Groq API as they arrive (streaming).
    Propagates all exceptions to the caller.
    """
    client = get_groq_client()
    completion = client.chat.completions.create(
        messages=messages,
        model=model,
        temperature=temperature,
        stream=True,
    )
    for chunk in completion:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content
