from dataclasses import dataclass
from typing import Optional


@dataclass
class Radicado:
    numero: str = ""
    ano_estado: str = ""
    relacion: str = ""
    tipo: str = ""
    radicado: str = ""
    juzgado: Optional[str] = None
    source_file: Optional[str] = None

    def to_dict(self) -> dict:
        result = {
            "numero": self.numero,
            "ano_estado": self.ano_estado,
            "relacion": self.relacion,
            "tipo": self.tipo,
            "radicado": self.radicado,
        }
        if self.juzgado:
            result["juzgado"] = self.juzgado
        if self.source_file:
            result["source_file"] = self.source_file
        return result
