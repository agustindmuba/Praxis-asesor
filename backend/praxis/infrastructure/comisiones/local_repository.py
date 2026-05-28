"""`LocalCatalogoComisiones`: implementación de `CatalogoComisiones` que lee
datos vendored localmente (CSV HCDN del Observatorio + JSON HSN oficial).

Los snapshots viven en `backend/data/comisiones/`. Se cargan eager al
construir el repositorio.

Ver `docs/specs/06-catalogo-comisiones.md`.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from praxis.application.ports import CatalogoComisiones
from praxis.domain import Camara, Comision, TipoComision

_DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "comisiones"


class LocalCatalogoComisiones(CatalogoComisiones):
    """Lee CSV HCDN + JSON HSN al construirse y sirve consultas en memoria."""

    def __init__(self, data_dir: Path | None = None) -> None:
        self._data_dir = data_dir or _DEFAULT_DATA_DIR
        self._by_camara: dict[Camara, list[Comision]] = {
            Camara.HCDN: _load_hcdn_csv(self._data_dir / "comisiones_hcdn_paridad.csv"),
            Camara.HSN: _load_hsn_json(self._data_dir / "comisiones_hsn.json"),
        }

    def listar(self, camara: Camara) -> list[Comision]:
        return list(self._by_camara.get(camara, []))

    def buscar_por_nombre(
        self,
        query: str,
        camara: Camara | None = None,
    ) -> list[Comision]:
        q = query.lower().strip()
        if not q:
            return []
        camaras = [camara] if camara is not None else list(Camara)
        resultados: list[Comision] = []
        for c in camaras:
            for com in self._by_camara.get(c, []):
                if q in com.nombre.lower():
                    resultados.append(com)
        return resultados


# -----------------------------------------------------------------------------
# Loaders
# -----------------------------------------------------------------------------


def _load_hcdn_csv(path: Path) -> list[Comision]:
    """CSV row-per-integrante del Observatorio. Deduplicar por `comision_slug`.

    Asignamos `TipoComision.PERMANENTE` por default — el CSV upstream no
    discrimina tipo. Ver caveat en `docs/specs/06-catalogo-comisiones.md`.
    """
    if not path.exists():
        raise FileNotFoundError(f"CSV de comisiones HCDN no encontrado: {path}")
    with path.open(encoding="utf-8") as f:
        lines = [line for line in f if not line.startswith("#")]
    reader = csv.DictReader(lines)
    vistos: dict[str, Comision] = {}
    for row in reader:
        slug = row.get("comision_slug", "").strip()
        if not slug or slug in vistos:
            continue
        nombre = row.get("comision_nombre", "").strip()
        if not nombre:
            continue
        categoria = row.get("categoria_tematica", "").strip() or None
        vistos[slug] = Comision(
            nombre=nombre,
            tipo=TipoComision.PERMANENTE,
            camara=Camara.HCDN,
            slug=slug,
            categoria_tematica=categoria,
        )
    return list(vistos.values())


def _load_hsn_json(path: Path) -> list[Comision]:
    """JSON oficial HSN: `{table: {rows: [{NOMBRE, TIPO_COMISION}, ...]}}`.

    El tipo viene como texto libre — lo mapeamos vía `TipoComision.from_text`.
    """
    if not path.exists():
        raise FileNotFoundError(f"JSON de comisiones HSN no encontrado: {path}")
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    rows = data.get("table", {}).get("rows", [])
    comisiones: list[Comision] = []
    for row in rows:
        nombre = (row.get("NOMBRE") or "").strip()
        if not nombre:
            continue
        tipo_text = (row.get("TIPO_COMISION") or "").strip()
        comisiones.append(
            Comision(
                nombre=nombre,
                tipo=TipoComision.from_text(tipo_text),
                camara=Camara.HSN,
                slug=None,
                categoria_tematica=None,
            )
        )
    return comisiones
