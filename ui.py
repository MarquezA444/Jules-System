"""
ui.py — Argos Rich terminal UI
Provides RichUI (layout, activity log, response panel, spinner, splash screen)
and supporting dataclasses.
"""
from __future__ import annotations

import os
import sys
import time
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterator, List, Optional

from rich.console import Console
from rich.live import Live
from rich.panel import Panel
from rich.rule import Rule
from rich.spinner import Spinner
from rich.table import Table
from rich.text import Text
from rich import box

# ── Version ──────────────────────────────────────────────────────────────────
VERSION = "1.0.0"

# ── Data models ──────────────────────────────────────────────────────────────

@dataclass
class UIEvent:
    timestamp: str   # HH:MM:SS
    message: str
    level: str       # scanning | trigger | action | success | error | idle | warn
    icon: str


@dataclass
class ChatMessage:
    role: str        # user | assistant | system
    content: str


@dataclass
class ScanSummary:
    files_scanned: int = 0
    triggers_found: int = 0
    notes_created: int = 0
    triggers_skipped: int = 0
    errors: int = 0


# ── Level → badge config ──────────────────────────────────────────────────────

_LEVEL_CONFIG = {
    "scanning": ("●", "cyan",         "SCANNING"),
    "trigger":  ("✓", "bright_cyan",  "TRIGGER"),
    "action":   ("⟳", "magenta",      "ACTION"),
    "success":  ("✓", "green",        "SUCCESS"),
    "error":    ("✗", "red",          "ERROR"),
    "idle":     ("◌", "dim white",    "IDLE"),
    "warn":     ("⚠", "yellow",       "WARN"),
    # aliases used internally
    "info":     ("●", "cyan",         "INFO"),
    "processing": ("⟳", "magenta",   "ACTION"),
}

_MAX_BUFFER = 200

# ── Splash screen ─────────────────────────────────────────────────────────────

_ARGOS_LOGO_PREMIUM = r"""
 █████╗ ██████╗  ██████╗  ██████╗ ███████╗
██╔══██╗██╔══██╗██╔════╝ ██╔═══██╗██╔════╝
███████║██████╔╝██║  ███╗██║   ██║███████╗
██╔══██║██╔══██╗██║   ██║██║   ██║╚════██║
██║  ██║██║  ██║╚██████╔╝╚██████╔╝███████║
╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝  ╚═════╝ ╚══════╝
""".strip("\n")

def show_splash(console: Optional[Console] = None) -> str:
    """
    Render a premium interactive splash screen.
    Returns: The selected mode ('watcher', 'scan', 'chat', or 'exit').
    """
    from rich.align import Align
    from rich.prompt import Prompt
    from rich.layout import Layout

    if console is None:
        console = Console()

    os.system('cls' if os.name == 'nt' else 'clear')

    logo_text = Text(_ARGOS_LOGO_PREMIUM, style="bold cyan")
    
    # Dashboard Info
    info_table = Table(box=None, show_header=False, padding=(0, 1))
    info_table.add_row("[dim white]System:[/dim white]", f"[bold cyan]Argos v{VERSION}[/bold cyan]")
    info_table.add_row("[dim white]Engine:[/dim white]", "[bold white]Llama 3.3 / Groq[/bold white]")
    info_table.add_row("[dim white]Status:[/dim white]", "[green] Ready[/green]")

    menu_table = Table(box=None, show_header=False, padding=(0, 2))
    menu_table.add_row("[bold cyan]1.[/bold cyan] Watcher Mode", "[dim]Monitor files for @argos tags[/dim]")
    menu_table.add_row("[bold cyan]2.[/bold cyan] Scan Mode", "[dim]Bulk scan a directory[/dim]")
    menu_table.add_row("[bold cyan]3.[/bold cyan] Chat Mode", "[dim]Interactive synthesis & QA[/dim]")
    menu_table.add_row("[bold cyan]Q.[/bold cyan] Exit", "[dim]Close Argos[/dim]")

    # Create the splash panel content using a Group of renderables
    from rich.console import Group
    
    content = Group(
        Text("\n"),
        Align.center(logo_text),
        Text("\n\n"),
        Align.center(info_table),
        Text("\n"),
        Align.center(Text("─" * 45, style="bright_black")),
        Text("\n"),
        Align.center(Text("S E L E C T   M O D E", style="bold white")),
        Text("\n"),
        Align.center(menu_table),
        Text("\n")
    )

    # Render a single rounded panel
    panel = Panel(
        content,
        box=box.ROUNDED,
        border_style="bright_black",
        padding=(1, 4),
        subtitle=f"[dim]Knowledge Capture System — {datetime.now().year}[/dim]",
        subtitle_align="right"
    )

    console.print("\n")
    console.print(Align.center(panel))
    console.print()

    choices = ["1", "2", "3", "q"]
    ans = Prompt.ask(
        "[bold white]Select Option[/bold white]",
        choices=choices,
        default="1",
        show_choices=False,
        console=console
    ).lower()

    os.system('cls' if os.name == 'nt' else 'clear')

    mapping = {
        "1": "watcher",
        "2": "scan",
        "3": "chat",
        "q": "exit"
    }
    return mapping.get(ans, "exit")


# ── RichUI ────────────────────────────────────────────────────────────────────

class RichUI:
    """
    Central presentation layer for Argos.
    Wraps watcher, scan, and chat modes with a structured Rich terminal UI.
    """

    def __init__(self, mode: str, watch_dirs: Optional[List[str]] = None):
        self.mode = mode.lower()
        self.watch_dirs = watch_dirs or []
        self._console = Console(highlight=False)
        self._events: List[UIEvent] = []
        self._response_panel: Optional[Panel] = None
        self._live: Optional[Live] = None
        self._lock = threading.Lock()
        self._running = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        self._running = True
        self._console.clear()
        self._render_header()
        self._console.print(Rule(style="bright_black"))

    def stop(self) -> None:
        self._running = False
        if self._live:
            self._live.stop()
        self._console.print(Rule(style="bright_black"))

    def __enter__(self) -> "RichUI":
        self.start()
        return self

    def __exit__(self, *args) -> None:
        self.stop()

    # ── Header / Footer ───────────────────────────────────────────────────────

    def _render_header(self) -> None:
        mode_indicators = {
            "watcher": ("●", "WATCHER", "cyan"),
            "scan":    ("⟳", "SCAN",    "yellow"),
            "chat":    ("◆", "CHAT",    "magenta"),
        }
        icon, label, color = mode_indicators.get(self.mode, ("●", self.mode.upper(), "cyan"))

        header = Text()
        header.append("  Argos", style="bold cyan")
        header.append(f" v{VERSION}", style="dim white")
        header.append(f"  {icon} ", style=color)
        header.append(label, style=f"bold {color}")

        for d in self.watch_dirs:
            header.append(f"  {d}", style="dim cyan")

        self._console.print(Rule(style="bright_black"))
        self._console.print(header)

    def _render_footer(self) -> None:
        footer = Text()
        footer.append("  ^", style="dim white")
        footer.append("C", style="white")
        footer.append(" Exit", style="dim white")
        footer.append("  •  ", style="bright_black")
        footer.append("^", style="dim white")
        footer.append("L", style="white")
        footer.append(" Clear", style="dim white")
        footer.append("  •  ", style="bright_black")
        footer.append("^", style="dim white")
        footer.append("K", style="white")
        footer.append(" Config", style="dim white")

        if self.mode == "chat":
            footer.append("  •  ", style="bright_black")
            footer.append("◆ ", style="cyan")
            footer.append("Prompt activo", style="dim white")

        self._console.print(Rule(style="bright_black"))
        self._console.print(footer)
        self._console.print(Rule(style="bright_black"))

    # ── Activity log ──────────────────────────────────────────────────────────

    def log_event(self, message: str, level: str = "info") -> None:
        """Append a timestamped, color-coded event to the activity log."""
        # Security: never render API key values
        _redact_keys(message)

        key = level.lower()
        icon, color, badge = _LEVEL_CONFIG.get(key, ("●", "cyan", level.upper()[:8]))

        ts = datetime.now().strftime("%H:%M:%S")
        event = UIEvent(timestamp=ts, message=message, level=key, icon=icon)

        with self._lock:
            self._events.append(event)
            if len(self._events) > _MAX_BUFFER:
                self._events = self._events[-_MAX_BUFFER:]

        line = Text()
        line.append(f"[{ts}]", style="dim white")
        line.append("  ")
        badge_str = f"{icon}  {badge}"
        line.append(f"{badge_str:<12}", style=f"bold {color}")
        line.append("  ")
        line.append(message, style="white")

        self._console.print(line)

    # ── Spinner ───────────────────────────────────────────────────────────────

    @contextmanager
    def show_spinner(self, message: str):
        """Context manager that shows an animated spinner while active."""
        with self._console.status(f"[magenta]{message}[/magenta]", spinner="dots"):
            yield

    # ── Response panel ────────────────────────────────────────────────────────

    def stream_response(self, token_iterator: Iterator[str], title: str = "Argos RESPONSE") -> None:
        """
        Render tokens from the iterator into a ROUNDED panel in real time.
        Uses Markdown for rich formatting and syntax highlighting.
        """
        from rich.markdown import Markdown
        full_text = ""
        panel_title = f"◆  {title}"

        with Live(console=self._console, refresh_per_second=10, transient=False) as live:
            for token in token_iterator:
                if token:
                    full_text += token
                    panel = Panel(
                        Markdown(full_text),
                        title=f"[bold cyan]{panel_title}[/bold cyan]",
                        border_style="cyan",
                        box=box.ROUNDED,
                        padding=(1, 2),
                    )
                    live.update(panel)

        # Final static render after streaming ends
        if full_text:
            self._console.print(
                Panel(
                    Markdown(full_text),
                    title=f"[bold cyan]{panel_title}[/bold cyan]",
                    border_style="cyan",
                    box=box.ROUNDED,
                    padding=(1, 2),
                )
            )

    # ── Scan summary ──────────────────────────────────────────────────────────

    def show_scan_summary(self, summary: ScanSummary) -> None:
        """Render a Rich table summarizing scan results."""
        table = Table(
            title="[bold cyan]Resumen del Scan[/bold cyan]",
            box=box.ROUNDED,
            border_style="cyan",
            show_header=True,
            header_style="bold white",
        )
        table.add_column("Métrica", style="dim white")
        table.add_column("Valor", justify="right", style="white")

        table.add_row("Archivos escaneados",  str(summary.files_scanned))
        table.add_row("Triggers encontrados", str(summary.triggers_found))
        table.add_row("Notas creadas",        f"[green]{summary.notes_created}[/green]")
        table.add_row("Triggers omitidos",    str(summary.triggers_skipped))
        table.add_row(
            "Errores",
            f"[red]{summary.errors}[/red]" if summary.errors else "[green]0[/green]",
        )

        self._console.print()
        self._console.print(table)
        self._console.print()
        self._render_footer()


# ── Security helper ───────────────────────────────────────────────────────────

def _redact_keys(text: str) -> None:
    """Raise ValueError if any API key value appears in the text."""
    for env_var in ("GROQ_API_KEY", "OBSIDIAN_API_KEY"):
        val = os.environ.get(env_var, "")
        if val and val in text:
            raise ValueError(f"Security: {env_var} value detected in UI output — redacted.")
