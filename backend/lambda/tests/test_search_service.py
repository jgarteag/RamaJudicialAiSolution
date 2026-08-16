
from app.domain.model import Radicado
from app.domain.services.search_service import Match, SearchService


class TestSearchService:

    def _make_radicado(self, numero, radicado, juzgado="J1PF", relacion="PERSONA"):
        return Radicado(
            numero=numero,
            radicado=radicado,
            ano_estado="2024",
            relacion=relacion,
            tipo=juzgado,
            juzgado=juzgado,
        )

    def test_finds_exact_numero_in_text(self):
        radicados = [self._make_radicado("0421", "2024-0421")]
        files = [{"filename": "estados.pdf", "text": "El radicado 0421 fue notificado"}]

        results = SearchService.search(files, radicados)

        assert len(results) == 1
        assert results[0].filename == "estados.pdf"
        assert results[0].radicado.numero == "0421"

    def test_finds_numero_as_substring(self):
        radicados = [self._make_radicado("0056", "2024-00056")]
        files = [{"filename": "9393.pdf", "text": "Referencia 2026-00056-00 estado"}]

        results = SearchService.search(files, radicados)

        assert len(results) == 1
        assert results[0].filename == "9393.pdf"
        assert results[0].radicado.numero == "0056"

    def test_finds_across_multiple_files(self):
        radicados = [self._make_radicado("0211", "2022-00211")]
        files = [
            {"filename": "doc1.pdf", "text": "Sin coincidencias aquí"},
            {"filename": "doc2.pdf", "text": "Proceso 0211 resuelto"},
        ]

        results = SearchService.search(files, radicados)

        assert len(results) == 1
        assert results[0].filename == "doc2.pdf"

    def test_finds_multiple_radicados_in_same_file(self):
        radicados = [
            self._make_radicado("0421", "2024-0421", "J1CMIPIALES"),
            self._make_radicado("0211", "2022-00211", "J1PF"),
        ]
        files = [{"filename": "lote.pdf", "text": "Radicados 0421 y 0211 notificados"}]

        results = SearchService.search(files, radicados)

        assert len(results) == 2
        numeros = {r.radicado.numero for r in results}
        assert numeros == {"0421", "0211"}

    def test_no_matches_returns_empty(self):
        radicados = [self._make_radicado("9999", "2024-9999")]
        files = [{"filename": "vacio.pdf", "text": "No hay nada relevante aquí"}]

        results = SearchService.search(files, radicados)

        assert results == []

    def test_match_includes_juzgado(self):
        radicados = [self._make_radicado("072", "2023-00072", "J2CMIPIALES")]
        files = [{"filename": "estado.txt", "text": "072 publicado"}]

        results = SearchService.search(files, radicados)

        assert results[0].radicado.juzgado == "J2CMIPIALES"

    def test_ignores_short_numeros_to_avoid_false_positives(self):
        radicados = [self._make_radicado("1", "2024-1")]
        files = [{"filename": "doc.pdf", "text": "Artículo 1 del código"}]

        results = SearchService.search(files, radicados, min_numero_length=3)

        assert results == []

    def test_deduplicates_same_radicado_in_same_file(self):
        radicados = [self._make_radicado("0421", "2024-0421")]
        files = [{"filename": "doc.pdf", "text": "0421 mencionado dos veces 0421"}]

        results = SearchService.search(files, radicados)

        assert len(results) == 1

    def test_filters_by_juzgado(self):
        radicados = [
            self._make_radicado("0421", "2024-0421", "J1CMIPIALES"),
            self._make_radicado("0211", "2022-00211", "J1PF"),
        ]
        files = [{"filename": "doc.pdf", "text": "0421 y 0211 ambos"}]

        results = SearchService.search(files, radicados, juzgado_filter="J1PF")

        assert len(results) == 1
        assert results[0].radicado.juzgado == "J1PF"


class TestMatchFormatting:

    def test_match_to_dict(self):
        radicado = Radicado(
            numero="0421",
            radicado="2024-0421",
            ano_estado="2024",
            relacion="JUAN PEREZ",
            tipo="J1CMIPIALES",
            juzgado="J1CMIPIALES",
        )
        match = Match(filename="estados.pdf", radicado=radicado)

        result = match.to_dict()

        assert result["filename"] == "estados.pdf"
        assert result["numero"] == "0421"
        assert result["radicado"] == "2024-0421"
        assert result["juzgado"] == "J1CMIPIALES"
        assert result["relacion"] == "JUAN PEREZ"

    def test_format_response_with_matches(self):
        matches = [
            Match(
                filename="9393.pdf",
                radicado=Radicado(
                    numero="0421",
                    radicado="2024-0421",
                    ano_estado="2024",
                    relacion="MARIA LOPEZ",
                    tipo="J1CMIPIALES",
                    juzgado="J1CMIPIALES",
                ),
            ),
        ]

        response = SearchService.format_response(matches)

        assert "9393.pdf" in response
        assert "0421" in response
        assert "J1CMIPIALES" in response

    def test_format_response_no_matches(self):
        response = SearchService.format_response([])

        assert "No se encontraron coincidencias" in response
