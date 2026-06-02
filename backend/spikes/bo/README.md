# Fixtures del spike Boletín Oficial

Capturados por `scripts/spike_bo.py` + `scripts/spike_bo_round2.py`.

Ver `docs/spikes/39-boletin-oficial.md` para la conclusión completa.

## Inventario

| Archivo | Origen | Uso |
|---|---|---|
| `_robots.txt` | `boletinoficial.gob.ar/robots.txt` | Evidencia: prohíbe sección segunda |
| `_homepage.html` | `boletinoficial.gob.ar/` | Shell SPA React para referencia |
| `legislacion__2026-06-01.html` | `/seccion/primera/*` | **Evidencia del shell SPA React**. Se capturaron 3 fechas (`2026-05-25`, `2026-05-31`, `2026-06-01`) y el MD5 fue idéntico — el portal no devuelve HTML por fecha, el contenido lo carga JS. Sólo dejamos 1 HTML por sección en el repo; la duplicación es ruido. |
| `designaciones__2026-06-01.html` | `/seccion/cuarta/*` | Idem |
| `pdf_del_dia__primera.pdf` | `s3.arsat.com.ar/cdn-bo-001/pdf-del-dia/primera.pdf` | **Fixture real** del PDF de Legislación del día del spike. Sirve para tests del parser PDF. |
| `pdf_del_dia__cuarta.pdf` | Idem para Designaciones | **Fixture real**. |

## Lo que NO está

- **`pdf_del_dia__segunda.pdf`**: borrado tras descargar. La sección
  segunda (Avisos Oficiales) está prohibida por el robots del portal
  origen; aunque el PDF vive en S3 (dominio distinto), respetamos el
  espíritu del robots y no la procesamos en MVP.
- **`pdf_del_dia__tercera.pdf`**: borrado. La sección tercera
  (Convocatorias, Edictos Judiciales) está explícitamente fuera del
  scope MVP (spec 15 §"Fuera de alcance v1").
- **PDFs de fechas pasadas**: no encontramos un patrón S3 viable.
  Pendiente para v2 si entra un spike SAIJ.

## Cómo reproducir / refrescar

```bash
cd backend
PYTHONUTF8=1 .venv/Scripts/python -m scripts.spike_bo
PYTHONUTF8=1 .venv/Scripts/python -m scripts.spike_bo_round2
```
