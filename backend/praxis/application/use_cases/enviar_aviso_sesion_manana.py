"""Caso de uso: avisar por WhatsApp que mañana hay sesión en HCDN
(feat-45.5).

Pipeline (corre el día anterior a las 18 ART, ver tasks_whatsapp.py):

1. Buscar ODs con `fecha_sesion = mañana` que provengan del scraping
   (`fuente=scraping_hcdn`).
2. Para cada despacho con perfil opositor cargado + destinatarios
   activos con opt-in:
   - Generar el briefing (GenerarBriefing) si no existe.
   - Mandar WhatsApp con plantilla `praxis_briefing_proxima_sesion`
     con 3 params:
       1. nombre del asesor (primer nombre del destinatario)
       2. tipo de sesión + fecha (ej. "Sesión Especial, jue 21/05")
       3. link al briefing en la app (https://.../briefings/{id})

3. Persistir cada `EnvioWhatsApp` para auditoría.

Idempotencia: si ya mandamos aviso para (despacho_id, orden_del_dia_id),
no volver a mandar (evita doble notificación si la task se corre dos
veces el mismo día).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import WhatsAppSender
from praxis.domain import EstadoEnvio, TipoEnvio

log = logging.getLogger(__name__)


PLANTILLA_PROXIMA_SESION = "praxis_briefing_proxima_sesion"

# Labels legibles de tipo de sesión para el param {{2}}.
TIPO_SESION_LABELS = {
    "ordinaria": "Sesión Ordinaria",
    "especial": "Sesión Especial",
    "extraordinaria": "Sesión Extraordinaria",
    "informativa": "Sesión Informativa",
}

_DIAS_SEMANA = ["lun", "mar", "mié", "jue", "vie", "sáb", "dom"]


@dataclass(frozen=True, slots=True)
class ResultadoAvisoSesion:
    fecha_destino: date                  # mañana
    ods_encontrados: int
    despachos_objetivo: int
    destinatarios_objetivo: int
    enviados_ok: int
    fallidos: int
    sin_perfil: int                      # despachos sin perfil opositor — skipeo
    duplicados: int                      # ya se mandó antes
    errores: list[str] = field(default_factory=list)


class EnviarAvisoSesionManana:
    """Use case principal de feat-45.5."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        sender: WhatsAppSender,
        base_url_app: str = "https://app.praxis-asesor.com",
    ) -> None:
        self._session = session
        self._sender = sender
        self._base_url = base_url_app.rstrip("/")

    async def ejecutar(
        self,
        *,
        ahora: datetime | None = None,
    ) -> ResultadoAvisoSesion:
        ahora = ahora or datetime.now(UTC)
        manana = ahora.date() + timedelta(days=1)

        ods = await self._ods_para_fecha(manana)
        log.info("aviso_sesion: %d OD(s) con fecha %s", len(ods), manana)

        despachos_set: set[UUID] = set()
        destinatarios_objetivo = 0
        enviados_ok = 0
        fallidos = 0
        sin_perfil = 0
        duplicados = 0
        errores: list[str] = []

        for od in ods:
            # Para cada OD del scraping: cada despacho con perfil opositor
            # y al menos un destinatario activo recibe aviso.
            despachos = await self._despachos_con_perfil_y_destinatarios()
            for d in despachos:
                despachos_set.add(d["despacho_id"])
                if d["destinatarios_count"] == 0:
                    continue
                if d["tiene_perfil"] != 1:
                    sin_perfil += 1
                    continue

                # Idempotencia: chequear si ya hay envío para
                # (despacho_id, plantilla=proxima_sesion, hoy o ayer).
                ya_enviado = await self._ya_se_envio_a(
                    despacho_id=d["despacho_id"],
                    od_id=od["id"],
                    ahora=ahora,
                )
                if ya_enviado:
                    duplicados += 1
                    continue

                # Pedir destinatarios + nombres
                destinatarios = await self._destinatarios_activos(
                    d["despacho_id"],
                )
                destinatarios_objetivo += len(destinatarios)

                tipo_y_fecha = self._formato_tipo_fecha(
                    od["titulo"], manana,
                )
                link = f"{self._base_url}/briefings/od/{od['id']}"

                for dest in destinatarios:
                    primer_nombre = self._primer_nombre(dest["nombre"])
                    params = [primer_nombre, tipo_y_fecha, link]
                    resultado = await self._sender.enviar(
                        telefono_e164=dest["telefono_e164"],
                        plantilla_name=PLANTILLA_PROXIMA_SESION,
                        idioma="es_AR",
                        body_params_ordered=params,
                    )
                    await self._registrar_envio(
                        despacho_id=d["despacho_id"],
                        destinatario_id=dest["id"],
                        params=params,
                        resultado=resultado,
                        ahora=ahora,
                    )
                    if resultado.exitoso:
                        enviados_ok += 1
                    else:
                        fallidos += 1
                        if resultado.error:
                            errores.append(resultado.error[:200])

        return ResultadoAvisoSesion(
            fecha_destino=manana,
            ods_encontrados=len(ods),
            despachos_objetivo=len(despachos_set),
            destinatarios_objetivo=destinatarios_objetivo,
            enviados_ok=enviados_ok,
            fallidos=fallidos,
            sin_perfil=sin_perfil,
            duplicados=duplicados,
            errores=errores,
        )

    # ------------------------------------------------------------------

    async def _ods_para_fecha(self, f: date) -> list[dict]:
        """Lista OD para una fecha. Filtra los que tienen 0 items
        (defensa contra parsers que fallaron y dejaron el OD vacío —
        mejor no avisar que avisar de algo sin contenido)."""
        r = await self._session.execute(text("""
            SELECT id, titulo, fecha_sesion, expedientes_ids
            FROM orden_del_dia
            WHERE fecha_sesion = :f AND fuente = 'scraping_hcdn'
        """), {"f": f})
        out: list[dict] = []
        for row in r.all():
            ids = row[3] or []
            if not ids:
                log.warning(
                    "ods_para_fecha: skip OD id=%s sin expedientes_ids",
                    row[0],
                )
                continue
            out.append({"id": row[0], "titulo": row[1], "fecha_sesion": row[2]})
        return out

    async def _despachos_con_perfil_y_destinatarios(self) -> list[dict]:
        """Lista despachos con perfil opositor cargado + cuántos destinatarios."""
        r = await self._session.execute(text("""
            SELECT
                d.id AS despacho_id,
                CASE WHEN p.despacho_id IS NOT NULL THEN 1 ELSE 0 END AS tiene_perfil,
                COUNT(des.id) FILTER (
                    WHERE des.activo AND des.recibe_briefing_diario
                          AND des.opt_in_en IS NOT NULL
                ) AS destinatarios_count
            FROM despacho d
            LEFT JOIN perfil_opositor_despacho p ON p.despacho_id = d.id
            LEFT JOIN destinatario des ON des.despacho_id = d.id
            GROUP BY d.id, p.despacho_id
        """))
        return [
            {
                "despacho_id": row[0],
                "tiene_perfil": int(row[1]),
                "destinatarios_count": int(row[2] or 0),
            }
            for row in r.all()
        ]

    async def _destinatarios_activos(self, despacho_id: UUID) -> list[dict]:
        r = await self._session.execute(text("""
            SELECT id, telefono_e164, nombre FROM destinatario
            WHERE despacho_id = :d AND activo
              AND recibe_briefing_diario AND opt_in_en IS NOT NULL
        """), {"d": despacho_id})
        return [
            {"id": row[0], "telefono_e164": row[1], "nombre": row[2] or ""}
            for row in r.all()
        ]

    async def _ya_se_envio_a(
        self, *, despacho_id: UUID, od_id: UUID, ahora: datetime,
    ) -> bool:
        """Verifica si hubo envío del briefing-próxima-sesión para este
        despacho en las últimas 24h (margen anti-doble-envío)."""
        ventana = ahora - timedelta(hours=24)
        r = await self._session.execute(text("""
            SELECT COUNT(*) FROM envio_whatsapp
            WHERE despacho_id = :d
              AND tipo = :t
              AND enviado_en >= :v
        """), {"d": despacho_id, "t": TipoEnvio.BRIEFING_PROXIMA_SESION.value, "v": ventana})
        return int(r.scalar() or 0) > 0

    async def _registrar_envio(
        self,
        *,
        despacho_id: UUID,
        destinatario_id: UUID,
        params: list[str],
        resultado,
        ahora: datetime,
    ) -> None:
        from uuid import uuid4
        await self._session.execute(text("""
            INSERT INTO envio_whatsapp (
                id, destinatario_id, despacho_id, plantilla_name, tipo,
                payload_params, correlativo_id, enviado_en, estado,
                message_id_meta, error
            )
            VALUES (
                :id, :did, :desp, :p, :t,
                CAST(:pp AS json), :cid, :en, :est,
                :mid, :err
            )
        """), {
            "id": uuid4(),
            "did": destinatario_id,
            "desp": despacho_id,
            "p": PLANTILLA_PROXIMA_SESION,
            "t": TipoEnvio.BRIEFING_PROXIMA_SESION.value,
            "pp": __import__("json").dumps({"params": params}),
            "cid": uuid4(),
            "en": ahora if resultado.exitoso else None,
            "est": (
                EstadoEnvio.ENVIADO.value if resultado.exitoso
                else EstadoEnvio.FALLIDO_TRANSITORIO.value
            ),
            "mid": resultado.message_id_meta,
            "err": resultado.error[:300] if resultado.error else None,
        })

    def _formato_tipo_fecha(self, titulo: str | None, f: date) -> str:
        # Inferir tipo desde el título guardado al crear el OD
        # ("Sesión especial HCDN (id 3581)").
        tipo = "Sesión"
        if titulo:
            low = titulo.lower()
            for clave, label in TIPO_SESION_LABELS.items():
                if clave in low:
                    tipo = label
                    break
        dia = _DIAS_SEMANA[f.weekday()]
        return f"{tipo}, {dia} {f.day}/{f.month:02d}"

    def _primer_nombre(self, nombre: str) -> str:
        if not nombre:
            return "asesor/a"
        first = nombre.strip().split()[0]
        return first[:30]
