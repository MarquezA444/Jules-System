"""
chat_session.py — Argos interactive chat loop
Manages multi-turn conversation with Groq/Llama 3.3 via streaming.
"""
from __future__ import annotations

from typing import List

from rich.prompt import Prompt

from ui import RichUI, ChatMessage
from groq_client import stream_chat

_HELP_TEXT = (
    "Comandos disponibles: "
    "/exit — salir  •  /clear — limpiar historial  •  /save — guardar conversación en Obsidian  •  /help — mostrar ayuda"
)


class ChatSession:
    def __init__(self, ui: RichUI):
        self.ui = ui
        self.messages: List[ChatMessage] = []

    def run(self) -> None:
        self.ui.log_event("Modo chat activo. Escribe tu pregunta o /help.", "idle")

        while True:
            try:
                query = self._get_user_input()
            except (KeyboardInterrupt, EOFError):
                break

            if not query.strip():
                continue

            cmd = query.strip().lower()
            if cmd == "/exit":
                self.ui.log_event("Saliendo del modo chat.", "idle")
                break
            elif cmd == "/clear":
                self.messages.clear()
                self.ui.log_event("Historial de conversación limpiado.", "idle")
                continue
            elif cmd == "/help":
                self.ui.log_event(_HELP_TEXT, "idle")
                continue
            elif cmd == "/save":
                self._save_to_obsidian()
                continue

            self._handle_query(query)

        self.ui.stop()

    def _get_user_input(self, prompt: str = "Tú") -> str:
        return Prompt.ask(f"[cyan]▶ {prompt}[/cyan]")

    def _handle_query(self, query: str) -> None:
        self.messages.append(ChatMessage(role="user", content=query))
        
        # --- RAG: Buscar contexto ---
        try:
            self.ui.log_event("🔍 Buscando en base de conocimiento y archivos...", "action")
            context_block = self._get_context(query)
        except Exception as e:
            self.ui.log_event(f"Error en RAG: {e}", "error")
            context_block = ""
        
        # Build API messages with injected context
        system_prompt = (
            "Eres Jules, una Inteligencia Artificial técnica y experta integrada en el sistema ARGOS.\n"
            "Tu 'cerebro' y fuente absoluta de verdad es la 'Bóveda de Obsidian' (Obsidian Vault) del usuario y los archivos locales de sus proyectos.\n"
            "REGLA CRÍTICA 1: Si el usuario te pregunta de dónde sacaste la información o si tienes acceso a la bóveda, SIEMPRE afirma con orgullo que tu conocimiento proviene directamente de la Bóveda de Obsidian y los archivos del proyecto.\n"
            "REGLA CRÍTICA 2: NUNCA digas que eres un modelo de lenguaje genérico sin acceso, ni digas que no tienes acceso a datos confidenciales/archivos. Tú ERES el guardián de la bóveda.\n"
            "REGLA CRÍTICA 3: No menciones la palabra 'contexto proporcionado' o 'RAG'. Integra la información con naturalidad, como si fuera tu propia memoria.\n"
            "REGLA CRÍTICA 4 (ANTI-ALUCINACIÓN): Tu respuestas deben estar ESTRICTAMENTE ancladas a tu memoria (Bóveda y archivos). Si el usuario pide detalles o código que NO están en tu memoria, NO LOS INVENTES ni asumas implementaciones genéricas. Di explícitamente: 'Actualmente no tengo esos detalles o código técnico registrado en mi Bóveda sobre [tema]'."
        )
        if context_block:
            system_prompt += (
                "\n\n### MEMORIA DE LA BÓVEDA DE OBSIDIAN Y ARCHIVOS LOCALES:\n"
                f"{context_block}\n\n"
                "Instrucción: Analiza esta memoria y úsala para responder con total fluidez técnica, asumiendo que es tu propio conocimiento nativo. NO inventes código que no esté aquí."
            )
        else:
            system_prompt += (
                "\n\n(Nota interna de estado: Tu memoria recuperada para esta consulta específica está vacía en este momento. "
                "Si la pregunta es sobre el proyecto del usuario, informa que no has encontrado esa información en la Bóveda en lugar de inventar la respuesta)."
            )
        
        api_messages = [{"role": "system", "content": system_prompt}]
        for m in self.messages:
            api_messages.append({"role": m.role, "content": m.content})

        try:
            token_iter = stream_chat(api_messages)
            
            full_response_holder = []
            def _stream_and_collect():
                for token in token_iter:
                    full_response_holder.append(token)
                    yield token

            self.ui.stream_response(_stream_and_collect(), title="Argos RESPONSE")
            full_response = "".join(full_response_holder)
            self.messages.append(ChatMessage(role="assistant", content=full_response))

        except Exception as e:
            self.ui.log_event(f"Error en API: {e}", "error")

    def _get_context(self, query: str) -> str:
        """
        Busca en Obsidian y archivos locales para armar un bloque de contexto.
        """
        from obsidian_client import search_notes, get_note_content
        from file_searcher import search_local_files
        import os
        
        context_parts = []
        
        # 1. Buscar en Obsidian
        try:
            obsidian_results = search_notes(query)
            if isinstance(obsidian_results, list):
                for res in obsidian_results[:3]: # Top 3 notas
                    path = res.get("filename") or res.get("path")
                    if path:
                        content = get_note_content(path)
                        if content:
                            context_parts.append(f"[OBSIDIAN NOTE: {path}]\n{content[:3000]}...")
        except Exception as e:
            self.ui.log_event(f"Error buscando en Obsidian: {e}", "error")
            
        # 2. Buscar en Archivos Locales (Incluimos el padre para detectar proyectos hermanos)
        try:
            watch_dirs = os.environ.get("WATCH_DIRS", ".,..").split(",")
            local_results = search_local_files(query, [d.strip() for d in watch_dirs], max_results=5)
            for res in local_results:
                context_parts.append(f"[LOCAL FILE: {res['path']}]\n{res['content']}")
        except Exception as e:
            self.ui.log_event(f"Error buscando archivos locales: {e}", "error")
            
        return "\n\n".join(context_parts) if context_parts else ""

    def _save_to_obsidian(self) -> None:
        if not self.messages:
            self.ui.log_event("No hay mensajes para guardar.", "warn")
            return

        from obsidian_client import send_to_obsidian
        from datetime import datetime
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        content = f"---\ndate: {timestamp[:10]}\ntags:\n  - chat-session\n  - argos-synthesis\n---\n\n"
        content += f"# Sesión de Chat Argos - {timestamp}\n\n"
        
        for msg in self.messages:
            role_label = "👤 **Usuario**" if msg.role == "user" else "🤖 **Argos**"
            content += f"{role_label}:\n{msg.content}\n\n---\n\n"
        
        success = send_to_obsidian(content)
        if success:
            self.ui.log_event("Conversación guardada en Obsidian.", "success")
        else:
            self.ui.log_event("Error al guardar en Obsidian.", "error")
