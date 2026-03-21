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
from ui import RichUI, ScanSummary, show_splash

# Configurar logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ArgosWatcher")

# Cargar variables de entorno
load_dotenv()

@dataclass
class ScanResult:
    filepath: str
    triggers_found: int
    notes_created: int
    triggers_skipped: int
    errors: int


class FileScanner:
    IGNORED_DIRS  = {'.git', '__pycache__', 'node_modules', 'venv'}
    IGNORED_FILES = {'.env'}

    def __init__(self, ui: Optional[RichUI] = None):
        self.ui = ui

    def _log(self, message: str, level: str = "info") -> None:
        if self.ui:
            self.ui.log_event(message, level)
        else:
            print(message)

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
            self._log(f"No se pudo leer {filepath}: {e}", "error")
            result.errors += 1
            return result

        for idx, line in enumerate(lines):
            if "@argos" not in line:
                continue

            result.triggers_found += 1
            comment_text = line.strip()
            current_hash = generate_hash(comment_text, filepath)

            if current_hash in cache:
                logger.debug(f"[SKIP] Trigger ya procesado (hash {current_hash[:8]}): {comment_text}")
                result.triggers_skipped += 1
                continue

            context = extract_context(filepath, idx, lines)
            self._log(f"Procesando trigger en {os.path.basename(filepath)}:{idx + 1}", "trigger")

            try:
                spinner_msg = "Generando nota vía Groq..."
                if self.ui:
                    with self.ui.show_spinner(spinner_msg):
                        note_content = generate_note(context, filepath, comment_text)
                else:
                    note_content = generate_note(context, filepath, comment_text)
            except Exception as e:
                self._log(f"generate_note falló en {filepath}:{idx + 1} — {e}", "error")
                result.errors += 1
                continue

            success = send_to_obsidian(note_content)
            if not success:
                self._log(f"send_to_obsidian falló para trigger en {filepath}:{idx + 1}", "error")
                result.errors += 1
                continue

            cache[current_hash] = {
                "timestamp": time.time(),
                "filepath": filepath,
                "comment": comment_text,
            }
            save_cache(cache)

            note_title = extract_title_from_note(note_content)
            self._log(f'Nota creada: "{note_title}"', "success")
            result.notes_created += 1

        return result

    def run(self, root: str) -> ScanSummary:
        files = self.discover_files(root)

        if not files:
            self._log("No se encontraron archivos elegibles para escanear.", "warn")
            return ScanSummary()

        cache = load_cache()
        summary = ScanSummary()

        for filepath in files:
            self._log(f"Procesando: {filepath}", "scanning")
            result = self.scan_file(filepath, cache)
            summary.files_scanned += 1
            summary.triggers_found += result.triggers_found
            summary.notes_created += result.notes_created
            summary.triggers_skipped += result.triggers_skipped
            summary.errors += result.errors

        return summary


CACHE_FILE = os.path.expanduser("~/.argos_cache.json")
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
            if "@argos" in line:
                comment_text = line.strip()

                # Generar hash del comentario + archivo
                current_hash = generate_hash(comment_text, filepath)

                cache = load_cache()

                if current_hash in cache:
                    logger.debug(f"Comentario ya procesado (Hash: {current_hash[:8]}): {comment_text}")
                    continue

                logger.info(f"¡Nuevo @argos detectado en {filepath}!")
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

class ArgosEventHandler(FileSystemEventHandler):
    def __init__(self, watch_dirs: List[str], ui: Optional[RichUI] = None):
        self.watch_dirs = [os.path.abspath(d) for d in watch_dirs]
        self.ignored_paths = ['.git', '__pycache__', 'node_modules', 'venv', '.env']
        self.ui = ui

    def is_ignored(self, filepath: str) -> bool:
        if filepath.endswith('~') or filepath.endswith('.swp'):
            return True
        for ignored in self.ignored_paths:
            if f"/{ignored}/" in filepath or filepath.endswith(f"/{ignored}"):
                return True
        return False

    def _log(self, message: str, level: str = "info") -> None:
        if self.ui:
            self.ui.log_event(message, level)
        else:
            logger.info(message)

    def on_modified(self, event):
        if not event.is_directory and not self.is_ignored(event.src_path):
            self._process_file(event.src_path)

    def _process_file(self, filepath: str) -> None:
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()

            for idx, line in enumerate(lines):
                if "@argos" not in line:
                    continue

                comment_text = line.strip()
                current_hash = generate_hash(comment_text, filepath)
                cache = load_cache()

                if current_hash in cache:
                    logger.debug(f"Comentario ya procesado: {comment_text}")
                    continue

                rel = os.path.basename(filepath)
                self._log(f"@argos detectado en {rel}:{idx + 1}", "trigger")

                context = extract_context(filepath, idx, lines)

                try:
                    spinner_msg = "Generando nota vía Groq (Llama 3.3)..."
                    self._log(spinner_msg, "action")
                    if self.ui:
                        with self.ui.show_spinner(spinner_msg):
                            nota_markdown = generate_note(context, filepath, comment_text)
                    else:
                        nota_markdown = generate_note(context, filepath, comment_text)

                    if send_to_obsidian(nota_markdown):
                        title = extract_title_from_note(nota_markdown)
                        self._log(f'Nota guardada: "{title}"', "success")
                        cache[current_hash] = {
                            "timestamp": time.time(),
                            "filepath": filepath,
                            "comment": comment_text,
                        }
                        save_cache(cache)
                    else:
                        self._log("No se pudo guardar la nota en Obsidian.", "error")

                except Exception as e:
                    self._log(f"Error procesando trigger: {e}", "error")

        except UnicodeDecodeError:
            pass
        except Exception as e:
            self._log(f"Error procesando archivo {filepath}: {e}", "error")

def run_watcher() -> None:
    watch_dirs_env = os.environ.get("WATCH_DIRS")
    if not watch_dirs_env:
        # If not in env, we might want to ask or default to current dir
        watch_dirs = ["."]
    else:
        watch_dirs = [d.strip() for d in watch_dirs_env.split(",")]

    ui = RichUI(mode="watcher", watch_dirs=watch_dirs)
    ui.start()

    observer = Observer()
    handler = ArgosEventHandler(watch_dirs, ui=ui)

    valid_dirs = []
    for directory in watch_dirs:
        if os.path.exists(directory) and os.path.isdir(directory):
            observer.schedule(handler, directory, recursive=True)
            valid_dirs.append(directory)
        else:
            ui.log_event(f"Directorio no encontrado o inválido: {directory}", "warn")

    if not observer.emitters:
        ui.log_event("No hay directorios válidos para observar. Saliendo.", "error")
        ui.stop()
        sys.exit(1)

    observer.start()
    ui.log_event(f"Observando {len(valid_dirs)} directorio(s) activo(s)...", "scanning")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        ui.log_event("Argos Watcher detenido por el usuario.", "idle")
    observer.join()
    ui.stop()


def run_scan(path: str) -> None:
    if not os.path.exists(path) or not os.path.isdir(path):
        print(f"Error: '{path}' no existe o no es un directorio.", file=sys.stderr)
        sys.exit(1)

    missing = [v for v in ("GROQ_API_KEY", "OBSIDIAN_INBOX_URL") if not os.environ.get(v)]
    if missing:
        print(
            f"Error: variables de entorno requeridas no definidas: {', '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

    ui = RichUI(mode="scan")
    ui.start()

    scanner = FileScanner(ui=ui)
    summary = scanner.run(path)
    ui.show_scan_summary(summary)

    sys.exit(1 if summary.errors > 0 else 0)


def run_chat() -> None:
    from chat_session import ChatSession
    ui = RichUI(mode="chat")
    ui.start()
    session = ChatSession(ui)
    session.run()


def main():
    parser = argparse.ArgumentParser(prog="argos", description="Argos - Knowledge capture tool")
    subparsers = parser.add_subparsers(dest="command")

    scan_parser = subparsers.add_parser("scan", help="Scan a directory for @argos triggers")
    scan_parser.add_argument("path", help="Root directory to scan")

    subparsers.add_parser("chat", help="Interactive chat with Groq/Llama 3.3")
    subparsers.add_parser("watch", help="Start the file watcher (default)")

    args = parser.parse_args()

    # Determine command: CLI argument or Interactive Splash
    cmd = args.command
    if not cmd:
        cmd = show_splash()
    
    if cmd == "exit":
        sys.exit(0)

    if cmd == "scan":
        path = getattr(args, "path", None)
        if not path:
            from rich.prompt import Prompt
            path = Prompt.ask("[bold white]Directory to scan[/bold white]", default=".")
        run_scan(path)
    elif cmd == "chat":
        run_chat()
    else:
        # Default to watcher
        run_watcher()


if __name__ == "__main__":
    main()
