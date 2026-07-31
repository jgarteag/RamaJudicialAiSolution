"""Domain services - business logic orchestration.

Services contain the core business logic, depending ONLY on ports (never on adapters directly).
This makes the business logic testable in isolation by mocking the ports.
"""

import re
from typing import Optional

from app.domain.model import Radicado, UploadResult
from app.domain.ports import AIService, ConfigRepository, RadicadoRepository

# ─── Radicado extraction patterns ────────────────────────────────────────────
RADICADO_PATTERNS = [
    re.compile(r'\b\d{5}[-\s]?\d{2}[-\s]?\d{2,3}[-\s]?\d{3}[-\s]?\d{4}[-\s]?\d{3,5}[-\s]?\d{2}\b'),
    re.compile(r'\b\d{23}\b'),
    re.compile(r'\b\d{4}[-/]\d{4,6}[-/]?\d{0,2}\b'),
    re.compile(r'\b\d{2,}[-/]\d{2,}[-/]?\d*\b'),
]

# ─── City to Juzgados mapping ────────────────────────────────────────────────
CITY_TO_JUZGADOS = {
    "ipiales": ["J1CMIPIALES", "J2CMIPIALES"],
    "cali": ["J7FCALI"],
    "pupiales": ["JPMPUPIALES"],
    "contadero": ["JPMCONTADERO"],
    "cordoba": ["JPMCORDOBA"],
    "córdoba": ["JPMCORDOBA"],
    "cumbal": ["JPMCUMBAL"],
    "guachucal": ["JPMGUACHUCAL"],
    "potosi": ["JPMPOTOSI"],
    "potosí": ["JPMPOTOSI"],
}

# History truncation
MAX_HISTORY_CHARS = 8000


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
        # Plain numeric sequences (5+ digits) that could be 'numero' field
        for m in re.findall(r'\b\d{5,}\b', text):
            candidates.add(m)
        return list(candidates)

    def search_in_juzgado(self, juzgado: str, text: str) -> list[Radicado]:
        """Search for matching radicados in a specific juzgado."""
        candidates = self.extract_candidates(text)
        if not candidates:
            return []

        results = self._repo.search_by_candidates(juzgado, candidates)

        # Add context snippet showing where the match was found
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


class ChatService:
    """Business logic for AI-powered chat with MongoDB context."""

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

    def chat(self, message: str, conversation_history: Optional[list] = None) -> tuple[str, str]:
        """Process a chat message. Returns (response, model_id)."""
        config = self._config_repo.get_agent_config(self._agent_id)

        # Build system prompt with MongoDB context if relevant
        system_prompt = config.system_prompt
        extra_context = self._get_mongo_context(message)
        if extra_context:
            system_prompt += f"\n\nContexto adicional:\n{extra_context}"

        # Truncate history by token estimate
        trimmed_history = self._truncate_history(conversation_history)

        return self._ai.invoke(message, system_prompt, config, trimmed_history)

    def _detect_juzgados(self, message: str, juzgados_list: list[str]) -> list[str]:
        """Detect juzgado references in user message against the real list of collections."""
        msg_upper = message.upper()
        msg_lower = message.lower()

        # Check exact juzgado codes (dynamic, matches whatever collections exist in Mongo)
        found = [j for j in juzgados_list if j.upper() in msg_upper]
        if found:
            return found

        # Check city names with number disambiguation (human-friendly aliases)
        for city, juzgados in CITY_TO_JUZGADOS.items():
            if city in msg_lower:
                juzgados = [j for j in juzgados if j in juzgados_list]
                if not juzgados:
                    continue
                if len(juzgados) > 1:
                    if "1" in message or "primero" in msg_lower or "primer" in msg_lower:
                        return [juzgados[0]]
                    elif "2" in message or "segundo" in msg_lower:
                        return [juzgados[1]]
                return juzgados

        return []

    def _get_mongo_context(self, message: str) -> Optional[str]:
        """Build MongoDB context for the AI when user asks about juzgados/radicados."""
        msg_upper = message.upper()
        juzgados_list = self._radicado_repo.list_juzgados()
        mentioned_juzgados = self._detect_juzgados(message, juzgados_list)

        asking_general = any(w in msg_upper for w in [
            "TODOS LOS RADICADO", "TODOS LOS ESTADO", "QUÉ RADICADO", "QUE RADICADO",
            "QUÉ ESTADO", "QUE ESTADO", "CUÁLES RADICADO", "CUALES RADICADO",
            "MUÉSTRAME", "MUESTRAME", "LISTAR", "LISTADO",
        ])

        if not mentioned_juzgados and not asking_general:
            return None

        context_parts = []

        if mentioned_juzgados:
            for juzgado in mentioned_juzgados:
                if juzgado in juzgados_list:
                    docs = self._radicado_repo.get_radicados_sample(juzgado, limit=50)
                    if docs:
                        context_parts.append(
                            f"Juzgado {juzgado} ({len(docs)} radicados):\n"
                            + "\n".join([
                                f"  - Radicado: {d.radicado or 'N/A'}, "
                                f"Relación: {d.relacion or 'N/A'}, "
                                f"Año: {d.ano_estado or 'N/A'}"
                                for d in docs
                            ])
                        )
                    else:
                        context_parts.append(f"Juzgado {juzgado}: sin radicados registrados")
        elif asking_general:
            for col_name in juzgados_list:
                count = self._radicado_repo.count_radicados(col_name)
                if count > 0:
                    docs = self._radicado_repo.get_radicados_sample(col_name, limit=5)
                    sample = ", ".join([d.radicado for d in docs[:3] if d.radicado])
                    context_parts.append(
                        f"Juzgado {col_name}: {count} radicados (ej: {sample})"
                    )
                else:
                    context_parts.append(f"Juzgado {col_name}: sin radicados")

        if context_parts:
            return "Datos reales de la base de datos:\n" + "\n\n".join(context_parts)
        return None

    @staticmethod
    def _truncate_history(conversation_history: Optional[list]) -> list:
        """Truncate conversation history by character count (~tokens)."""
        if not conversation_history:
            return []

        total_chars = 0
        trimmed = []
        for msg in reversed(conversation_history):
            msg_len = len(msg.get("content", ""))
            if total_chars + msg_len > MAX_HISTORY_CHARS:
                break
            trimmed.insert(0, msg)
            total_chars += msg_len

        return trimmed


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

            # Validate extension
            import os
            ext = os.path.splitext(filename.lower())[1]
            supported = {".pdf", ".docx", ".doc", ".txt", ".text"}
            if ext and ext not in supported:
                skipped_files.append(
                    {"filename": filename, "reason": f"Formato {ext} no soportado"}
                )
                continue

            # Decode and extract text
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

            # Search radicados
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

        # Generate AI summary
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
