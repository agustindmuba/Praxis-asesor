# Fixtures HSN

HTML capturado del portal HSN durante el spike (`feat/scraping-spike`). Se usan como input estable para los tests de contrato del parser, sin requerir red.

| Archivo | Expediente | Notas |
|---|---|---|
| `hsn_239_24_S_PL.html` | 239/24 (S, PL) | Sapag — etiquetado transgénicos. Autor presente, giros con fechas in/out. |
| `hsn_1_24_CD_PL.html` | 1/24 (CD, PL) | Ley Bases (revisión desde Diputados). **Sin autores** en HSN (viven en HCDN); 3 giros. |
| `hsn_1497_20_S_PC.html` | 1497/20 (S, PC) | Blanco/Basualdo — comunicación. Histórico 2020. |

## Política

Igual que en `tests/fixtures/hcdn/README.md`: si el portal HSN cambia su estructura y los tests rompen, **re-capturar** los fixtures correindo `uv run spike/hsn/explore.py` y copiarlos acá conscientemente. Si los campos disponibles cambian (HSN deja de exponer X), abrir ADR sobre cómo manejarlo.
