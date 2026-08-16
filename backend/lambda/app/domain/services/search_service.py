from dataclasses import dataclass
from typing import Optional

from app.domain.model import Radicado

DEFAULT_MIN_NUMERO_LENGTH = 3


@dataclass
class Match:
    filename: str
    radicado: Radicado

    def to_dict(self) -> dict:
        return {
            "filename": self.filename,
            "numero": self.radicado.numero,
            "radicado": self.radicado.radicado,
            "juzgado": self.radicado.juzgado or "",
            "relacion": self.radicado.relacion,
            "ano_estado": self.radicado.ano_estado,
            "tipo": self.radicado.tipo,
        }


class SearchService:

    @staticmethod
    def search(
        files: list[dict],
        radicados: list[Radicado],
        min_numero_length: int = DEFAULT_MIN_NUMERO_LENGTH,
        juzgado_filter: Optional[str] = None,
    ) -> list[Match]:
        filtered = radicados
        if juzgado_filter:
            filtered = [r for r in radicados if r.juzgado == juzgado_filter]

        matches: list[Match] = []
        seen: set[tuple[str, str]] = set()

        for file in files:
            filename = file["filename"]
            text = file["text"]

            for radicado in filtered:
                if len(radicado.numero) < min_numero_length:
                    continue

                key = (filename, radicado.numero)
                if key in seen:
                    continue

                if radicado.numero in text:
                    matches.append(Match(filename=filename, radicado=radicado))
                    seen.add(key)

        return matches

    @staticmethod
    def format_response(matches: list[Match]) -> str:
        if not matches:
            return "No se encontraron coincidencias en los documentos cargados."

        lines = [f"Se encontraron **{len(matches)}** coincidencia(s):\n"]
        for m in matches:
            lines.append(
                f"- En el archivo **{m.filename}** se encontró el radicado "
                f"**{m.radicado.radicado}** (No. {m.radicado.numero}) "
                f"del juzgado **{m.radicado.juzgado}** — {m.radicado.relacion}"
            )
        return "\n".join(lines)
