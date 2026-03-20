import argparse
import os
import sys
import time
import hashlib
import json
import logging
from dataclasses import dataclass
from typing import List, Tuple, Optional
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from dotenv import load_dotenv

from groq_client import generate_note
from obsidian_client import send_to_obsidian, extract_title_from_note

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("JulesWatcher")

# Cargar variables de entorno
load_dotenv()

@dataclass
class ScanResult:
    filepath: str
    triggers_found: int
    notes_created: int
    triggers_skipped: int
    errors: int


@dataclass
class ScanSummary:
    files_scanned: int
    triggers_found: int
    notes_created: int
    triggers_skipped: int
    errors: int


class FileScanner:
    IGNORED_DIRS  = {'.git', '__pycache__', 'node_modules', 'venv'}
    IGNORED_FILES = {'.env'}

    def discover_files(self, root: str) -> List[str]:
        eligible = []
        for dirpath, dirs, files in os.walk(root):
            # Filtrar directorios ignorados in-place para no descender en ellos
            dirs[:] = [d for d in dirs if d not in self.IGNORED_DIRS]

            for filename in files:
                # Descartar archivos ignorados por nombre
                if filename in self.IGNORED_FILES:
                    continue
                # Descartar swap files y backups
                if filename.endswith('.swp') or filename.endswith('~'):
                    continue

                filepath = os.path.join(dirpath, filename)

                # Descartar archivos binarios (no decodificables como UTF-8)
                try:
                    with open(filepath, 'rb') as f:
                        chunk = f.read(8192)
                    chunk.decode('utf-8')
                except (UnicodeDecodeError, OSError):
                    continue

                eligible.append(filepath)

        return eligible

    def scan_file(self, filepath: str, cache: dict) -> ScanResult:
        result = ScanResult(
            filepath=filepath,
            triggers_found=0,
            notes_created=0,
            triggers_skipped=0,
            errors=0,
        )

        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
        except (UnicodeDecodeError, OSError) as e:
            logger.error(f"No se pudo leer {filepath}: {e}")
            result.errors += 1
            return result

        for idx, line in enumerate(lines):
            if "@jules" not in line:
                continue

            result.triggers_found += 1
            comment_text = line.strip()
            current_hash = generate_hash(comment_text, filepath)

            if current_hash in cache:
                logger.debug(f"[SKIP] Trigger ya procesado (hash {current_hash[:8]}): {comment_text}")
                result.triggers_skipped += 1
                continue

            # Trigger nuevo — procesar
            context = extract_context(filepath, idx, lines)

            try:
                note_content = generate_note(context, filepath, comment_text)
            except Exception as e:
                logger.error(f"[ERROR] generate_note falló en {filepath}:{idx + 1} — {e}")
                result.errors += 1
                continue

            success = send_to_obsidian(note_content)
            if not success:
                logger.error(f"[ERROR] send_to_obsidian falló para trigger en {filepath}:{idx + 1}")
                result.errors += 1
                continue

            # Éxito: actualizar caché y contadores
            cache[current_hash] = {
                "timestamp": time.time(),
                "filepath": filepath,
                "comment": comment_text,
            }
            save_cache(cache)

            note_title = extract_title_from_note(note_content)
            logger.info(f"[OK] Nota creada — {filepath} → '{note_title}'")
            result.notes_created += 1

        return result

    def run(self, root: str) -> ScanSummary:
        files = self.discover_files(root)

        if not files:
            print("No se encontraron archivos elegibles para escanear.")
            return ScanSummary(
                files_scanned=0,
                triggers_found=0,
                notes_created=0,
                triggers_skipped=0,
                errors=0,
            )

        cache = load_cache()
        summary = ScanSummary(
            files_scanned=0,
            triggers_found=0,
            notes_created=0,
            triggers_skipped=0,
            errors=0,
        )

        for filepath in files:
            print(f"Procesando: {filepath}")
            result = self.scan_file(filepath, cache)
            summary.files_scanned += 1
            summary.triggers_found += result.triggers_found
            summary.notes_created += result.notes_created
            summary.triggers_skipped += result.triggers_skipped
            summary.errors += result.errors

        return summary


CACHE_FILE = os.path.expanduser("~/.jules_cache.json")
MAX_FILE_SIZE_BYTES = 10 * 1024  # 10KB
LINES_AROUND = 50

def load_cache() -> dict:
    if os.path.exists(CACHE_FILE):
        try:
            with open(CACHE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except json.JSONDecodeError:
            logger.warning("Archivo de caché corrupto. Creando uno nuevo.")
            return {}
    return {}

def save_cache(cache: dict) -> None:
    with open(CACHE_FILE, 'w', encoding='utf-8') as f:
        json.dump(cache, f, indent=2)

def generate_hash(content: str, filepath: str) -> str:
    hasher = hashlib.sha256()
    hasher.update(filepath.encode('utf-8'))
    hasher.update(content.encode('utf-8'))
    return hasher.hexdigest()

def extract_context(filepath: str, jules_line_idx: int, lines: List[str]) -> str:
    file_size = os.path.getsize(filepath)

    if file_size <= MAX_FILE_SIZE_BYTES:
        return "".join(lines)

    start_idx = max(0, jules_line_idx - LINES_AROUND)
    end_idx = min(len(lines), jules_line_idx + LINES_AROUND + 1)

    return "".join(lines[start_idx:end_idx])

def process_file(filepath: str) -> None:
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()

        for idx, line in enumerate(lines):
            if "@jules" in line:
                comment_text = line.strip()

                # Generar hash del comentario + archivo
                current_hash = generate_hash(comment_text, filepath)

                cache = load_cache()

                if current_hash in cache:
                    logger.debug(f"Comentario ya procesado (Hash: {current_hash[:8]}): {comment_text}")
                    continue

                logger.info(f"¡Nuevo @jules detectado en {filepath}!")
                context = extract_context(filepath, idx, lines)

                logger.info(f"Contexto extraído ({len(context)} caracteres).")

                # Fase 3: Integración Groq
                try:
                    nota_markdown = generate_note(context, filepath, comment_text)
                    logger.info("Nota generada exitosamente por Groq.")

                    # Fase 4: Enviar a Obsidian
                    if send_to_obsidian(nota_markdown):
                        logger.info("Proceso completado.")

                        cache[current_hash] = {
                            "timestamp": time.time(),
                            "filepath": filepath,
                            "comment": comment_text
                        }
                        save_cache(cache)
                    else:
                        logger.error("No se pudo guardar la nota en Obsidian. Se intentará nuevamente más tarde.")
                        continue

                except Exception as e:
                    logger.error(f"Error procesando el comentario: {e}")
                    continue

    except UnicodeDecodeError:
        # Ignorar archivos binarios
        pass
    except Exception as e:
        logger.error(f"Error procesando el archivo {filepath}: {e}")

class JulesEventHandler(FileSystemEventHandler):
    def __init__(self, watch_dirs: List[str]):
        self.watch_dirs = [os.path.abspath(d) for d in watch_dirs]
        self.ignored_paths = ['.git', '__pycache__', 'node_modules', 'venv', '.env']

    def is_ignored(self, filepath: str) -> bool:
        # Ignore backup files
        if filepath.endswith('~') or filepath.endswith('.swp'):
            return True

        # Ignore specific directories
        for ignored in self.ignored_paths:
            if f"/{ignored}/" in filepath or filepath.endswith(f"/{ignored}"):
                return True

        return False

    def on_modified(self, event):
        if not event.is_directory and not self.is_ignored(event.src_path):
            process_file(event.src_path)

def run_watcher() -> None:
    watch_dirs_env = os.environ.get("WATCH_DIRS")
    if not watch_dirs_env:
        logger.error("La variable de entorno WATCH_DIRS no está definida.")
        sys.exit(1)

    watch_dirs = [d.strip() for d in watch_dirs_env.split(",")]

    observer = Observer()
    handler = JulesEventHandler(watch_dirs)

    for directory in watch_dirs:
        if os.path.exists(directory) and os.path.isdir(directory):
            observer.schedule(handler, directory, recursive=True)
            logger.info(f"Observando directorio: {directory}")
        else:
            logger.warning(f"Directorio no encontrado o inválido: {directory}")

    if not observer.emitters:
        logger.error("No hay directorios válidos para observar. Saliendo.")
        sys.exit(1)

    observer.start()
    logger.info("Jules Watcher iniciado. Esperando eventos...")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        logger.info("Jules Watcher detenido por el usuario.")
    observer.join()


def run_scan(path: str) -> None:
    # Validar que path existe y es un directorio
    if not os.path.exists(path) or not os.path.isdir(path):
        print(f"Error: '{path}' no existe o no es un directorio.", file=sys.stderr)
        sys.exit(1)

    # Validar variables de entorno requeridas
    missing = [v for v in ("GROQ_API_KEY", "OBSIDIAN_INBOX_URL") if not os.environ.get(v)]
    if missing:
        print(f"Error: las siguientes variables de entorno son requeridas y no están definidas: {', '.join(missing)}", file=sys.stderr)
        sys.exit(1)

    scanner = FileScanner()
    summary = scanner.run(path)

    print(
        f"\nResumen del scan:\n"
        f"  Archivos escaneados : {summary.files_scanned}\n"
        f"  Triggers encontrados: {summary.triggers_found}\n"
        f"  Notas creadas       : {summary.notes_created}\n"
        f"  Triggers omitidos   : {summary.triggers_skipped}\n"
        f"  Errores             : {summary.errors}"
    )

    sys.exit(1 if summary.errors > 0 else 0)


def main():
    parser = argparse.ArgumentParser(prog="jules", description="Jules - Knowledge capture tool")
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Scan a directory for @jules triggers")
    scan_parser.add_argument("path", help="Root directory to scan")

    args = parser.parse_args()

    if args.command == "scan":
        run_scan(args.path)
    else:
        run_watcher()


if __name__ == "__main__":
    main()
