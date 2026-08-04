"""Domain services - business logic orchestration.

Services contain the core business logic, depending ONLY on ports (never on adapters directly).
This makes the business logic testable in isolation by mocking the ports.
"""

import json
import re
from typing import Optional

from app.domain.model import Radicado, ToolDefinition, UploadResult
from app.domain.ports import AIService, ConfigRepository, RadicadoRepository

# ─── Radicado extraction patterns (kept for UploadService backward compat) ───
RADICADO_PATTERNS = [
    re.compile(
        r'\b\d{5}[-\s]?\d{2}[-\s]?\d{2,3}[-\s]?\d{3}[-\s]?\d{4}[-\s]?\d{3,5}[-\s]?\d{2}\b'
    ),
    re.compile(r'\b\d{23}\b'),
    re.compile(r'\b\d{4}[-/]\d{4,6}[-/]?\d{0,2}\b'),
    re.compile(r'\b\d{2,}[-/]\d{2,}[-/]?\d*\b'),
]

# History truncation
MAX_HISTORY_CHARS = 8000
MAX_TOOL_ITERATIONS = 10


# ─── Tool Definitions ────────────────────────────────────────────────────────

TOOL_DEFINITIONS = [
    ToolDefinition(
        name="list_juzgados",
        description=(
            "Lista todos los juzgados disponibles en la base de datos. "
            "Usa esta herramienta cuando el usuario pregunte qué juzgados hay, "
            "o cuando necesites saber los nombres exactos de los juzgados."
        ),
        input_schema={
            "type": "object",
            "properties": {},
        },
    ),
    ToolDefinition(
        name="search_radicado",
        description=(
            "Busca UN radicado por número en la base de datos. "
            "Acepta búsquedas parciales (ej: '0421', '2024-0421', '065'). "
            "IMPORTANTE: Busca UN solo radicado por llamada. "
            "Si necesitas buscar varios, llama esta herramienta varias veces. "
            "El parámetro 'juzgado' debe ser el CÓDIGO exacto de la colección "
            "(ej: 'J2PF', 'J1CMIPIALES'), NO el nombre completo. "
            "Si no conoces el código, usa list_juzgados primero o no pases juzgado "
            "para buscar en todos."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": (
                        "Número o parte del número del radicado a buscar. "
                        "Normaliza antes: quita espacios extras, "
                        "ej: '2024 -00065' → '2024-00065'"
                    ),
                },
                "juzgado": {
                    "type": "string",
                    "description": (
                        "CÓDIGO exacto del juzgado (ej: 'J2PF', 'J1CMIPIALES'). "
                        "Usa list_juzgados para obtener los códigos válidos. "
                        "Si no lo conoces, omite este campo para buscar en todos."
                    ),
                },
            },
            "required": ["query"],
        },
    ),
    ToolDefinition(
        name="search_by_name",
        description=(
            "Busca radicados por nombre de la persona/parte en el campo 'relacion'. "
            "La búsqueda es case-insensitive y acepta nombres parciales. "
            "Si se proporciona juzgado, busca solo en ese; si no, busca en todos."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "name": {
                    "type": "string",
                    "description": "Nombre o parte del nombre de la persona a buscar",
                },
                "juzgado": {
                    "type": "string",
                    "description": (
                        "Nombre exacto del juzgado donde buscar (opcional). "
                        "Usa list_juzgados para ver los nombres disponibles."
                    ),
                },
            },
            "required": ["name"],
        },
    ),
    ToolDefinition(
        name="get_radicados",
        description=(
            "Obtiene una lista de radicados de un juzgado específico. "
            "Usa esta herramienta cuando el usuario quiera ver los radicados "
            "de un juzgado sin un criterio de búsqueda específico."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "juzgado": {
                    "type": "string",
                    "description": "Nombre exacto del juzgado",
                },
                "limit": {
                    "type": "integer",
                    "description": "Máximo de resultados (default 20, max 50)",
                },
            },
            "required": ["juzgado"],
        },
    ),
]


# ─── ToolUseChatService (replaces ChatService) ──────────────────────────────


class ToolUseChatService:
    """Agentic chat service using tool-use pattern.

    The LLM decides when and how to query MongoDB via tools,
    eliminating fragile regex/heuristic-based search logic.
    """

    def __init__(
        self,
        ai_service: AIService,
        config_repo: ConfigRepository,
        radicado_repo: RadicadoRepository,
        agent_id: str,
    ):
        self._ai = ai_service
        self._config_repo = config_repo
        self._radicado_repo = radicado_repo
        self._agent_id = agent_id

    def get_tool_definitions(self) -> list[ToolDefinition]:
        """Return the list of tools available to the LLM."""
        return TOOL_DEFINITIONS

    def execute_tool(self, tool_name: str, tool_input: dict) -> str:
        """Execute a tool and return the result as a string for the LLM."""
        handlers = {
            "list_juzgados": self._handle_list_juzgados,
            "search_radicado": self._handle_search_radicado,
            "search_by_name": self._handle_search_by_name,
            "get_radicados": self._handle_get_radicados,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return f"Error: la herramienta '{tool_name}' no existe."

        try:
            return handler(tool_input)
        except Exception as e:
            return f"Error ejecutando '{tool_name}': {str(e)}"

    def chat(
        self, message: str, conversation_history: Optional[list] = None
    ) -> tuple[str, str]:
        """Process a chat message using the agentic tool-use loop.

        Returns (response_text, model_id).
        """
        config = self._config_repo.get_agent_config(self._agent_id)
        tools = self.get_tool_definitions()

        # Build messages list
        messages = []
        if conversation_history:
            trimmed = self._truncate_history(conversation_history)
            for msg in trimmed:
                messages.append({"role": msg["role"], "content": msg["content"]})
        messages.append({"role": "user", "content": message})

        # Agentic loop
        model_id = config.model_id
        for _ in range(MAX_TOOL_ITERATIONS):
            response = self._ai.invoke_with_tools(
                messages=messages,
                system_prompt=config.system_prompt,
                config=config,
                tools=tools,
            )

            model_id = response.get("model", model_id)
            stop_reason = response.get("stop_reason", "end_turn")
            content_blocks = response.get("content", [])

            # If no tool use, extract text and return
            if stop_reason != "tool_use":
                return self._extract_text(content_blocks), model_id

            # Process tool calls
            messages.append({"role": "assistant", "content": content_blocks})

            tool_results = []
            for block in content_blocks:
                if block.get("type") == "tool_use":
                    tool_result = self.execute_tool(block["name"], block.get("input", {}))
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block["id"],
                        "content": tool_result,
                    })

            messages.append({"role": "user", "content": tool_results})

        # Safety: if we hit max iterations, return whatever we have
        return (
            "He alcanzado el límite de consultas. Por favor reformula tu pregunta.",
            model_id,
        )

    # ─── Tool Handlers ───────────────────────────────────────────────────────

    def _handle_list_juzgados(self, _input: dict) -> str:
        juzgados = self._radicado_repo.list_juzgados()
        # Provide descriptive names so the LLM can map PDF headers to codes
        descriptions = {
            "J1CMIPIALES": "Juzgado Primero Civil Municipal de Ipiales",
            "J2CMIPIALES": "Juzgado Segundo Civil Municipal de Ipiales",
            "J7FCALI": "Juzgado Séptimo de Familia de Cali",
            "JPMCORDOBA": "Juzgado Promiscuo Municipal de Córdoba",
            "JPMCONTADERO": "Juzgado Promiscuo Municipal de Contadero",
            "JPMCUMBAL": "Juzgado Promiscuo Municipal de Cumbal",
            "JPMGUACHUCAL": "Juzgado Promiscuo Municipal de Guachucal",
            "JPMPOTOSI": "Juzgado Promiscuo Municipal de Potosí",
            "JPMPUERRES": "Juzgado Promiscuo Municipal de Puerres",
            "JPMPUPIALES": "Juzgado Promiscuo Municipal de Pupiales",
            "J1PF": "Juzgado Primero Promiscuo de Familia de Ipiales",
            "J2PF": "Juzgado Segundo Promiscuo de Familia de Ipiales",
        }
        juzgado_list = [
            {"codigo": j, "nombre": descriptions.get(j, j)}
            for j in juzgados
        ]
        return json.dumps(
            {"juzgados": juzgado_list, "total": len(juzgados)}, ensure_ascii=False
        )

    def _handle_search_radicado(self, tool_input: dict) -> str:
        query = tool_input.get("query", "")
        juzgado = self._resolve_juzgado(tool_input.get("juzgado"))
        results = self._radicado_repo.search_radicado(juzgado, query)
        return self._format_results(results)

    def _handle_search_by_name(self, tool_input: dict) -> str:
        name = tool_input.get("name", "")
        juzgado = self._resolve_juzgado(tool_input.get("juzgado"))
        results = self._radicado_repo.search_by_name(juzgado, name)
        return self._format_results(results)

    def _handle_get_radicados(self, tool_input: dict) -> str:
        juzgado = tool_input.get("juzgado", "")
        limit = min(tool_input.get("limit", 20), 50)
        results = self._radicado_repo.get_radicados_sample(juzgado, limit)
        return self._format_results(results)

    # ─── Helpers ─────────────────────────────────────────────────────────────

    def _resolve_juzgado(self, juzgado_input: str | None) -> str | None:
        """Resolve a juzgado name/code to an actual collection code.

        Handles cases where the LLM passes the full descriptive name
        instead of the collection code (e.g., "Juzgado Segundo Promiscuo
        de Familia de Ipiales" → "J2PF").
        """
        if not juzgado_input:
            return None

        juzgado_input = juzgado_input.strip()
        collection_names = self._radicado_repo.list_juzgados()

        # Direct match
        if juzgado_input in collection_names:
            return juzgado_input

        # Case-insensitive match
        upper_input = juzgado_input.upper()
        for name in collection_names:
            if name.upper() == upper_input:
                return name

        # Fuzzy: check if any collection code is contained in the input
        for name in collection_names:
            if name.upper() in upper_input:
                return name

        # No match found — search all juzgados
        return None

    @staticmethod
    def _format_results(results: list[Radicado]) -> str:
        """Format radicado results as JSON for the LLM."""
        if not results:
            return json.dumps(
                {"results": [], "total": 0, "message": "No se encontraron resultados."},
                ensure_ascii=False,
            )
        return json.dumps(
            {
                "results": [r.to_dict() for r in results],
                "total": len(results),
            },
            ensure_ascii=False,
        )

    @staticmethod
    def _extract_text(content_blocks: list) -> str:
        """Extract text from content blocks."""
        texts = []
        for block in content_blocks:
            if isinstance(block, dict) and block.get("type") == "text":
                texts.append(block["text"])
        return "\n".join(texts) if texts else "No pude generar una respuesta."

    @staticmethod
    def _truncate_history(conversation_history: list) -> list:
        """Truncate conversation history by character count (~tokens)."""
        total_chars = 0
        trimmed = []
        for msg in reversed(conversation_history):
            content = msg.get("content", "")
            msg_len = len(content) if isinstance(content, str) else len(json.dumps(content))
            if total_chars + msg_len > MAX_HISTORY_CHARS:
                break
            trimmed.insert(0, msg)
            total_chars += msg_len
        return trimmed


# ─── RadicadoSearchService (kept for UploadService backward compat) ──────────


class RadicadoSearchService:
    """Business logic for searching radicados in documents."""

    def __init__(self, repository: RadicadoRepository):
        self._repo = repository

    def extract_candidates(self, text: str) -> list[str]:
        """Extract potential radicado numbers from text using regex patterns."""
        candidates = set()
        for pattern in RADICADO_PATTERNS:
            for m in pattern.findall(text):
                candidates.add(m.strip())
                normalized = re.sub(r'[-/\s]', '', m.strip())
                if normalized != m.strip():
                    candidates.add(normalized)
        for m in re.findall(r'\b\d{5,}\b', text):
            candidates.add(m)
        return list(candidates)

    def search_in_juzgado(self, juzgado: str, text: str) -> list[Radicado]:
        """Search for matching radicados in a specific juzgado."""
        candidates = self.extract_candidates(text)
        if not candidates:
            return []

        results = self._repo.search_by_candidates(juzgado, candidates)

        for rad in results:
            match_term = rad.numero if rad.numero in text else rad.radicado
            if match_term and match_term in text:
                idx = text.find(match_term)
                contexto = text[max(0, idx - 60):min(len(text), idx + len(match_term) + 60)]
                rad.contexto = contexto.strip()

        return results

    def search_all_juzgados(self, text: str) -> list[Radicado]:
        """Search for radicados across all available juzgados."""
        all_results = []
        for juzgado in self._repo.list_juzgados():
            matches = self.search_in_juzgado(juzgado, text)
            for match in matches:
                match.juzgado = juzgado
            all_results.extend(matches)
        return all_results

    def list_juzgados(self) -> list[str]:
        """List all available juzgados."""
        return self._repo.list_juzgados()


# ─── ChatService (DEPRECATED - kept for backward compat, use ToolUseChatService)


class ChatService:
    """DEPRECATED: Use ToolUseChatService instead.

    Kept for backward compatibility during migration.
    """

    def __init__(
        self,
        ai_service: AIService,
        config_repo: ConfigRepository,
        radicado_repo: RadicadoRepository,
        agent_id: str,
    ):
        self._delegate = ToolUseChatService(
            ai_service=ai_service,
            config_repo=config_repo,
            radicado_repo=radicado_repo,
            agent_id=agent_id,
        )

    def chat(self, message: str, conversation_history: Optional[list] = None) -> tuple[str, str]:
        """Delegate to ToolUseChatService."""
        return self._delegate.chat(message, conversation_history)


# ─── UploadService ───────────────────────────────────────────────────────────


class UploadService:
    """Business logic for processing document uploads."""

    def __init__(
        self,
        search_service: RadicadoSearchService,
        ai_service: AIService,
        config_repo: ConfigRepository,
        agent_id: str,
    ):
        self._search = search_service
        self._ai = ai_service
        self._config_repo = config_repo
        self._agent_id = agent_id

    def process_files(
        self,
        files_data: list[dict],
        juzgado: str,
        extract_text_fn,
    ) -> UploadResult:
        """Process uploaded files, search radicados, and generate AI summary."""
        all_matches = []
        processed_files = []
        skipped_files = []

        for file_item in files_data:
            file_base64 = file_item.get("file", "")
            filename = file_item.get("filename", "document.pdf")

            if not file_base64:
                skipped_files.append({"filename": filename, "reason": "Archivo vacío"})
                continue

            import os
            ext = os.path.splitext(filename.lower())[1]
            supported = {".pdf", ".docx", ".doc", ".txt", ".text"}
            if ext and ext not in supported:
                skipped_files.append(
                    {"filename": filename, "reason": f"Formato {ext} no soportado"}
                )
                continue

            try:
                import base64
                file_bytes = base64.b64decode(file_base64)
                text = extract_text_fn(file_bytes, filename)
            except Exception as e:
                skipped_files.append(
                    {"filename": filename, "reason": f"Error extrayendo texto: {str(e)}"}
                )
                continue

            if not text.strip():
                skipped_files.append({"filename": filename, "reason": "No se pudo extraer texto"})
                continue

            processed_files.append(filename)

            if juzgado:
                matches = self._search.search_in_juzgado(juzgado, text)
                for m in matches:
                    m.juzgado = juzgado
                    m.source_file = filename
            else:
                matches = self._search.search_all_juzgados(text)
                for m in matches:
                    m.source_file = filename

            all_matches.extend(matches)

        if not processed_files:
            return UploadResult(
                ai_response="",
                skipped_files=skipped_files,
            )

        ai_prompt = self._build_summary_prompt(all_matches, processed_files, juzgado)
        config = self._config_repo.get_agent_config(self._agent_id)
        ai_response, model = self._ai.invoke(ai_prompt, config.system_prompt, config)

        return UploadResult(
            ai_response=ai_response,
            matches=[r.to_dict() for r in all_matches],
            files_processed=processed_files,
            skipped_files=skipped_files,
            model=model,
            juzgado_filter=juzgado or "todos",
        )

    @staticmethod
    def _build_summary_prompt(matches: list[Radicado], files: list[str], juzgado: str) -> str:
        """Build the prompt for AI summarization of upload results."""
        if matches:
            resumen = "\n".join([
                f"- Radicado {r.radicado} ({r.relacion or 'N/A'}) "
                f"del juzgado {r.juzgado or 'N/A'}, año {r.ano_estado or '?'}, "
                f"encontrado en: {r.source_file or 'N/A'}"
                for r in matches
            ])
            return (
                f"Encontré {len(matches)} radicados en {len(files)} "
                f"documento(s) ({', '.join(files)}) que coinciden con estados "
                f"judiciales registrados:\n{resumen}\n\n"
                f"Genera un resumen claro. Sé conciso y usa markdown."
            )
        else:
            return (
                f"No encontré coincidencias de radicados en {len(files)} "
                f"documento(s) ({', '.join(files)}) "
                f"{'del juzgado ' + juzgado if juzgado else 'en ningún juzgado'}. "
                f"Indica al usuario que no se encontraron coincidencias."
            )
