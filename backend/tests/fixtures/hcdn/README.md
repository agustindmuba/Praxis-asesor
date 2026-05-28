# Fixtures HCDN

HTML capturado del portal HCDN durante el spike (`feat/scraping-spike`). Se usan como input estable para los tests de contrato del parser, sin requerir red.

| Archivo | Expediente | Notas |
|---|---|---|
| `hcdn_1497-D-2024.html` | 1497-D-2024 | Propato, Datos Personales. 1 firmante, 1 giro, trámite con adhesiones. |
| `hcdn_0001-D-2024.html` | 0001-D-2024 | Educación como servicio esencial. 2 firmantes, 3 giros, sin trámite todavía. |
| `hcdn_0001-PE-2024.html` | 0001-PE-2024 | Mensaje del Poder Ejecutivo (Crimen Organizado). 4 firmantes, 2 giros, trámite con 6 eventos. |

Cuando el portal HCDN cambie su estructura, estos fixtures pueden quedar desactualizados. Política:

1. Si el portal cambia y el parser sigue extrayendo todo correctamente, no hay nada que hacer.
2. Si el portal cambia y se requiere ajustar el parser, re-capturar los fixtures (correr `spike/hcdn/explore.py`) y copiarlos acá.
3. Si los campos disponibles cambian (HCDN deja de exponer X), abrir un ADR sobre cómo manejar la nueva forma.
