# Jules System

Jules es una herramienta de documentación automática de código para desarrolladores que usan Obsidian como segundo cerebro.

Observa tus proyectos en busca de comentarios `@jules` en el código fuente, genera notas Markdown estructuradas usando IA (Groq / Llama 3.3) y las deposita automáticamente en la carpeta `00_Inbox/` de tu vault de Obsidian. También incluye un modo CLI para escanear proyectos completos de una sola vez.

---

## Cómo funciona

1. Escribís un comentario `@jules` en cualquier archivo de código
2. Jules detecta el comentario (en tiempo real o via scan)
3. Groq/Llama 3.3 genera una nota Markdown estructurada con contexto, fragmento de código y tags
4. La nota se guarda automáticamente en tu vault de Obsidian

---

## Requisitos previos

- Python 3.10+
- [Obsidian](https://obsidian.md/) con el plugin [Local REST API](https://github.com/coddingtonbear/obsidian-local-rest-api) instalado y activo
- Una cuenta en [Groq](https://console.groq.com/) para obtener un API key gratuito

---

## Instalación

**1. Clonar el repositorio**

```bash
git clone https://github.com/tu-usuario/jules-system.git
cd jules-system
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

# Directorios de proyectos a observar, separados por coma
WATCH_DIRS=C:\Projects\my-app,C:\Projects\other-app

# URL del endpoint REST Local de Obsidian
# El formato correcto es: http://localhost:27123/vault/<nombre-de-tu-vault>/00_Inbox
OBSIDIAN_INBOX_URL=http://localhost:27123/vault/MiVault/00_Inbox

# API key del plugin Local REST API de Obsidian
# Encontrala en: Obsidian → Settings → Community Plugins → Local REST API
OBSIDIAN_API_KEY=tu_api_key_de_obsidian
```

**5. Verificar que Obsidian está corriendo** con el plugin Local REST API activo antes de usar Jules.

---

## Uso

### Modo Watcher — documentación en tiempo real

Iniciá el watcher y dejalo corriendo en una terminal:

```bash
python jules.py
```

Jules observará los directorios configurados en `WATCH_DIRS`. Cada vez que guardés un archivo con un comentario `@jules`, generará y enviará la nota automáticamente.

```
2026-03-19 18:02:41 - JulesWatcher - INFO - ¡Nuevo @jules detectado en index.js!
2026-03-19 18:02:43 - JulesWatcher - INFO - Nota generada exitosamente por Groq.
2026-03-19 18:02:45 - JulesWatcher - INFO - [OK] Nota creada — index.js → 'Agregar Nota a Contrato Seguido'
```

### Modo Scan — documentar un proyecto existente

Para procesar un directorio completo de una sola vez sin necesidad de modificar archivos:

```bash
python jules.py scan /ruta/a/tu/proyecto
```

Al finalizar verás un resumen:

```
Resumen del scan:
  Archivos escaneados : 142
  Triggers encontrados: 8
  Notas creadas       : 6
  Triggers omitidos   : 2
  Errores             : 0
```

### Insertar un trigger en tu código

Añadí un comentario `@jules` seguido de una descripción en cualquier archivo de código:

```javascript
// @jules Explicar cómo funciona el sistema de autenticación JWT en este módulo
exports.handler = async (event) => {
  // ...
};
```

```python
# @jules Documentar el algoritmo de caché con Redis y sus casos de invalidación
def get_cached_data(key: str):
    ...
```

```sql
-- @jules Explicar la lógica de esta query y sus índices relevantes
SELECT * FROM contratos WHERE ...
```

Jules funciona con cualquier lenguaje de programación.

---

## Estructura del proyecto

```
jules-system/
├── jules.py            # Punto de entrada — watcher y CLI scan
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

Jules mantiene un caché en `~/.jules_cache.json`. Los triggers ya procesados se omiten automáticamente tanto en modo watcher como en modo scan, evitando notas duplicadas al reiniciar o re-escanear.

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
- Jules-System debe vivir **fuera** del vault de Obsidian para que el vault contenga únicamente notas `.md`
- El plugin Local REST API de Obsidian debe estar activo y Obsidian debe estar abierto para que las notas se depositen correctamente
