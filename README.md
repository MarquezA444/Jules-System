# Argos System

Argos es una herramienta de documentación automática de código para desarrolladores que usan Obsidian como segundo cerebro.

Observa tus proyectos en busca de comentarios `@argos` en el código fuente, genera notas Markdown estructuradas usando IA y las deposita automáticamente en tu Bóveda de Obsidian. 
Además, incluye un **Modo Chat Interactivo** dotado de un sistema RAG (Retrieval-Augmented Generation) que utiliza tu Bóveda y los archivos locales de tus proyectos como su cerebro, permitiéndote hacer preguntas técnicas complejas sobre tu propio código.

---

## Características Principales

1. **Modo Watcher (Tiempo Real)**: Detecta comentarios `@argos` cuando guardas un archivo y genera documentación automática en Obsidian.
2. **Modo Chat (Tu IA Personal)**: Chat interactivo por terminal (Jules) con acceso total en tiempo real a tus notas de Obsidian y código fuente local.
3. **Buscador RAG de Precisión**: Utiliza heurística de *Stop Words* y *JsonLogic* nativo contra la API de Obsidian para encontrar exactamente el código o nota que necesitas, sin alucinaciones.
4. **Exportación de Conversaciones**: Guarda hilos enteros de chat usando el comando `/save` directo a tu Bóveda.
5. **Dashboard Interactivo**: UI premium en la terminal usando la librería `rich`.

---

## Requisitos previos

- Python 3.10+
- [Obsidian](https://obsidian.md/) con el plugin [Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) instalado y activo.
- Una cuenta en [Groq](https://console.groq.com/) para obtener un API key gratuito (modelo Llama 3.3).

---

## Instalación

**1. Clonar el repositorio**

```bash
git clone https://github.com/tu-usuario/Argos-System.git
cd Argos-System
```

**2. Crear y activar el entorno virtual**

```bash
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate
```

**3. Instalar dependencias**

```bash
pip install -r requirements.txt
```

**4. Configurar variables de entorno**

```bash
cp .env.example .env
```

Abrí `.env` y completá los valores:

```env
# API key de Groq — obtenela en https://console.groq.com/
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxx

# Directorios de proyectos a observar, separados por coma. Ejemplo: .,..
WATCH_DIRS=.,..

# URL del endpoint REST Local de Obsidian
# El formato correcto es: http://localhost:27123/vault/<nombre-de-tu-vault>/00_Inbox
OBSIDIAN_INBOX_URL=http://localhost:27123/vault/MiVault/00_Inbox

# API key del plugin Local REST API de Obsidian
# Encontrala en: Obsidian → Settings → Community Plugins → Local REST API
OBSIDIAN_API_KEY=tu_api_key_de_obsidian
```

**5. Verificar que Obsidian está corriendo** con el plugin Local REST API activo antes de usar Jules.

---

## Uso (Dashboard Start)

Para iniciar Argos y acceder al menú interactivo de la terminal:

```bash
python argos.py
```

Desde el Dashboard podrás moverte con las flechas direccionales y seleccionar el modo de operación:

### 1. Modo Chat (Asistente RAG)

Jules (la IA) actuará como un desarrollador experto que conoce todo tu código y notas.
- **RAG Dual Engine**: Cada pregunta tuya escanea tu Bóveda de Obsidian (vía JsonLogic) y todos los archivos listados en `WATCH_DIRS` (buscando coincidencias de texto exactas, ignorando *stop words*).
- **Consola Markdown**: Las respuestas se renderizan con resaltado de sintaxis, tablas y colores de Markdown.
- **Comandos**: Escribe `/save` en cualquier momento para exportar toda tu conversación técnica directamente como una nota en la carpeta Inbox de Obsidian. Escribe `/exit` para salir.

### 2. Modo Watcher (Documentación en vivo)

Al iniciarlo, Argos se queda escuchando cambios en los archivos.
Añadí un comentario `@argos` seguido de una descripción en cualquier archivo de código:

```javascript
// @argos Explicar cómo funciona el sistema de autenticación JWT en este módulo
exports.handler = async (event) => {
  // ...
};
```

Argos leerá el archivo, aislará la función o clase subyacente, la explicará y mandará la nota a Obsidian de forma silenciosa e independiente.

### 3. Modo Scan (Documentación masiva)

Para procesar un directorio completo de una sola vez sin necesidad de modificar archivos de forma activa. Escaneará **todos** los `@argos` que tengas pendientes y generará todas las notas juntas.


```python
# @argos Documentar el algoritmo de caché con Redis y sus casos de invalidación
def get_cached_data(key: str):
    ...
```

```sql
-- @argos Explicar la lógica de esta query y sus índices relevantes
SELECT * FROM contratos WHERE ...
```

Jules funciona con cualquier lenguaje de programación.

---

## Estructura del proyecto

```
Argos-System/
├── argos.py            # Punto de entrada — watcher y CLI scan
├── groq_client.py      # Cliente Groq/Llama — genera las notas Markdown
├── obsidian_client.py  # Cliente Obsidian REST API — deposita las notas
├── test_jules_scan.py  # Suite de tests (pytest + Hypothesis)
├── .env.example        # Plantilla de variables de entorno
├── requirements.txt    # Dependencias Python
└── README.md
```

---

## Formato de las notas generadas

Cada nota generada por Jules sigue esta estructura en Obsidian:

````markdown
---
date: 2026-03-19
source_file: C:\Projects\app\index.js
project: my-app
language: JavaScript
tags:
  - aws-lambda
  - node-js
  - postgresql
---

# Título descriptivo del concepto

> Resumen ejecutivo en una oración.

## 💡 Concepto / Problema

Explicación técnica del problema resuelto o concepto documentado.

## 🛠️ Implementación / Fragmento

```javascript
// fragmento de código relevante
```
````

Comentarios sobre mejores prácticas y puntos clave.

---

_Generado por Jules · 2026-03-19_

````

---

## Deduplicación

Jules mantiene un caché en `~/.argos_cache.json`. Los triggers ya procesados se omiten automáticamente tanto en modo watcher como en modo scan, evitando notas duplicadas al reiniciar o re-escanear.

---

## Tests

```bash
# Activar el venv primero
venv\Scripts\activate

# Correr la suite completa
python -m pytest test_jules_scan.py -v
````

---

## Notas importantes

- El archivo `.env` nunca debe subirse a control de versiones (está en `.gitignore`)
- Argos-System debe vivir **fuera** del vault de Obsidian para que el vault contenga únicamente notas `.md`
- El plugin Local REST API de Obsidian debe estar activo y Obsidian debe estar abierto para que las notas se depositen correctamente
