"""`CsvPadronRepository`: implementación de `CatalogoLegisladores` que lee
los CSVs vendored del Observatorio (CC BY 4.0).

Los CSVs viven en `backend/data/padron/`. Se cargan al construir el
repositorio (eager) y se cachean en memoria; el padrón cambia poco
y son ~330 filas total.

Ver `docs/specs/05-catalogo-legisladores.md` para el contexto del vendor.
"""

from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

from praxis.application.ports import CatalogoLegisladores
from praxis.domain import Camara
from praxis.domain.legislador import Bloque, Legislador

# Default: los CSVs vendored en `backend/data/padron/`.
_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "padron"


class CsvPadronRepository(CatalogoLegisladores):
    """Carga el padrón desde dos CSVs (HCDN + HSN) y sirve consultas en memoria."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or _DEFAULT_DATA_DIR
        self._by_camara: dict[Camara, list[Legislador]] = {
            Camara.HCDN: _load_csv(self._data_dir / "padron_diputados.csv", Camara.HCDN),
            Camara.HSN: _load_csv(self._data_dir / "padron_senado.csv", Camara.HSN),
        }
        self._by_slug: dict[tuple[Camara, str], Legislador] = {
            (leg.camara, leg.slug): leg for legs in self._by_camara.values() for leg in legs
        }

    def listar(self, camara: Camara) -> list[Legislador]:
        # Copia defensiva — el llamador no debería mutar la lista cacheada.
        return list(self._by_camara.get(camara, []))

    def buscar_por_slug(self, slug: str, camara: Camara) -> Legislador:
        key = (camara, slug)
        if key not in self._by_slug:
            raise KeyError(f"Slug '{slug}' no encontrado en {camara.value}")
        return self._by_slug[key]

    def buscar_por_nombre(self, query: str) -> list[Legislador]:
        q = query.lower().strip()
        if not q:
            return []
        resultados: list[Legislador] = []
        for legs in self._by_camara.values():
            for leg in legs:
                if q in leg.apellido.lower() or q in leg.nombre.lower():
                    resultados.append(leg)
        return resultados


# -----------------------------------------------------------------------------
# Helpers de carga / parseo
# -----------------------------------------------------------------------------


def _load_csv(path: Path, camara: Camara) -> list[Legislador]:
    """Lee un CSV del Observatorio (con headers comentados al inicio).

    Filtra las líneas que empiezan con `#` y parsea el resto como CSV
    estándar con DictReader.
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV de padrón no encontrado: {path}")
    with path.open(encoding="utf-8") as f:
        # Saltear líneas-comentario (formato Observatorio).
        lines = [line for line in f if not line.startswith("#")]
    reader = csv.DictReader(lines)
    legisladores: list[Legislador] = []
    for row in reader:
        legisladores.append(_row_to_legislador(row, camara))
    return legisladores


def _row_to_legislador(row: dict[str, str], camara: Camara) -> Legislador:
    """Convierte una fila del CSV a un `Legislador` del dominio."""
    bloque = Bloque(nombre=row["bloque"].strip(), camara=camara)
    return Legislador(
        slug=row["slug"].strip(),
        apellido=row["apellido"].strip(),
        nombre=row["nombre"].strip(),
        camara=camara,
        distrito=row["distrito"].strip(),
        bloque=bloque,
        periodo_mandato=row["periodo_mandato"].strip(),
        fecha_inicio_mandato=_parse_date(row["fecha_inicio_mandato"]) or date(1900, 1, 1),
        fecha_fin_mandato=_parse_date(row["fecha_fin_mandato"]) or date(2099, 12, 31),
        fecha_nacimiento=_parse_date(row.get("fecha_nacimiento", "")),
        edad_anios=_parse_int(row.get("edad_anios", "")),
        genero=row.get("genero", "").strip() or None,
        profesion=row.get("profesion", "").strip() or None,
        profesion_categoria=row.get("profesion_categoria", "").strip() or None,
        foto_url=row.get("foto_url", "").strip() or None,
        padron_snapshot_fecha=_parse_date(row.get("padron_snapshot_fecha", "")),
    )


def _parse_date(s: str | None) -> date | None:
    """Parsea ISO `YYYY-MM-DD` o devuelve None si vacío/inválido."""
    if not s or not s.strip():
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def _parse_int(s: str | None) -> int | None:
    if not s or not s.strip():
        return None
    try:
        return int(s.strip())
    except ValueError:
        return None
