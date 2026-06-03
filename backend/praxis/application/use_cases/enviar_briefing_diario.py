"""Caso de uso: enviar el briefing diario por WhatsApp (feat-41.4).

Consolida en un solo mensaje las novedades del día para el despacho
y lo manda a cada destinatario activo que tenga el flag
`recibe_briefing_diario`.

Pipeline (spec 17 §"Briefing diario"):

1. Cargar el despacho + sus destinatarios activos.
2. Filtrar destinatarios que tengan `recibe_briefing_diario=True` y
   `puede_recibir(TipoEnvio.BRIEFING_DIARIO)` → respeta opt-in/flags.
3. Resolver el contenido del briefing del día:
   - Top N accionables del BO (vía `NormaBOAccionableRepository`).
   - Top M artículos relevantes 24h (vía `ArticuloRelevanteRepository`).
4. Componer `resumen_corto` ≤180 chars (cap conservador para no
   romper el límite de Meta — los params de plantilla tienen tope
   técnico de 1024 chars cada uno pero Meta puede rechazar
   contenido > 200 con código 131056).
5. Por cada destinatario:
   - Crear `EnvioWhatsApp(estado=PENDIENTE)` en DB.
   - Llamar `WhatsAppSender.enviar(plantilla="briefing_diario",
     body_params=[nombre, fecha, resumen_corto])`.
   - Si éxito → `marcar_enviado(message_id, enviado_en)`.
   - Si rechazo → `marcar_fallido(error, rechazado=True)` Y si el
     code corresponde a opt-out (131026), también marcar el
     destinatario como `opt_out_en=ahora, activo=False` para no
     reintentarlo mañana.
   - Si fallido transitorio → `marcar_fallido(error)` sin tocar el
     destinatario; mañana se vuelve a intentar.

El caso de uso NO commitea; el caller (Celery task de 41.5) maneja
la sesión y commitea al final por despacho.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from praxis.application.ports import (
    ArticuloRelevanteRepository,
    DestinatarioRepository,
    EnvioWhatsAppRepository,
    NormaBOAccionableRepository,
    WhatsAppSender,
)
from praxis.domain import (
    Destinatario,
    EnvioWhatsApp,
    TipoEnvio,
)

log = logging.getLogger(__name__)

PLANTILLA_BRIEFING_DIARIO = "briefing_diario"
TOP_BO_DEFAULT = 3
TOP_NOTICIAS_DEFAULT = 3
MAX_RESUMEN_CORTO_CHARS = 180

# Código Meta para "recipient opted out" — marcamos al destinatario.
META_CODE_OPT_OUT = 131026


@dataclass(frozen=True, slots=True)
class ResultadoBriefingDiario:
    despacho_id: UUID
    destinatarios_objetivo: int
    enviados_ok: int
    fallidos_transitorios: int
    rechazados: int
    sin_contenido: bool  # True si el día no tuvo BO ni noticias
    correlativo_id: UUID
    errores: list[str] = field(default_factory=list)


class EnviarBriefingDiario:
    """Caso de uso: 1 ejecución por (despacho, fecha)."""

    def __init__(
        self,
        *,
        destinatarios: DestinatarioRepository,
        envios: EnvioWhatsAppRepository,
        accionables_bo: NormaBOAccionableRepository,
        relevantes_noticias: ArticuloRelevanteRepository,
        sender: WhatsAppSender,
    ) -> None:
        self._destinatarios = destinatarios
        self._envios = envios
        self._accionables = accionables_bo
        self._relevantes = relevantes_noticias
        self._sender = sender

    async def ejecutar(
        self,
        *,
        despacho_id: UUID,
        fecha: date,
        ahora: datetime | None = None,
        top_bo: int = TOP_BO_DEFAULT,
        top_noticias: int = TOP_NOTICIAS_DEFAULT,
    ) -> ResultadoBriefingDiario:
        ts = ahora or datetime.now(UTC)
        correlativo_id = uuid4()

        destinatarios = await self._destinatarios.listar_por_despacho(
            despacho_id, solo_activos=True,
        )
        elegibles = [
            d for d in destinatarios
            if d.puede_recibir(TipoEnvio.BRIEFING_DIARIO)
        ]
        if not elegibles:
            return ResultadoBriefingDiario(
                despacho_id=despacho_id,
                destinatarios_objetivo=0,
                enviados_ok=0,
                fallidos_transitorios=0,
                rechazados=0,
                sin_contenido=False,
                correlativo_id=correlativo_id,
            )

        # Resolver contenido del día. Si NO hay nada para contar,
        # devolvemos sin_contenido=True y no mandamos mensaje
        # (evita mandar plantilla con "0 normas, 0 noticias" todos los
        # findes y feriados).
        n_bo, n_noticias = await self._contar_contenido(
            despacho_id=despacho_id,
            fecha=fecha,
            ahora=ts,
            top_bo=top_bo,
            top_noticias=top_noticias,
        )
        if n_bo == 0 and n_noticias == 0:
            return ResultadoBriefingDiario(
                despacho_id=despacho_id,
                destinatarios_objetivo=len(elegibles),
                enviados_ok=0,
                fallidos_transitorios=0,
                rechazados=0,
                sin_contenido=True,
                correlativo_id=correlativo_id,
            )

        resumen = _componer_resumen(n_bo=n_bo, n_noticias=n_noticias)
        enviados = 0
        fallidos_t = 0
        rechazados = 0
        errores: list[str] = []

        for dest in elegibles:
            try:
                ok, transitorio = await self._enviar_a(
                    dest=dest,
                    fecha=fecha,
                    resumen_corto=resumen,
                    correlativo_id=correlativo_id,
                    ahora=ts,
                )
                if ok:
                    enviados += 1
                elif transitorio:
                    fallidos_t += 1
                else:
                    rechazados += 1
            except Exception as exc:
                errores.append(f"{dest.telefono_e164}: {exc}")
                log.warning(
                    "Briefing diario falló para %s: %s",
                    dest.telefono_e164, exc,
                )

        return ResultadoBriefingDiario(
            despacho_id=despacho_id,
            destinatarios_objetivo=len(elegibles),
            enviados_ok=enviados,
            fallidos_transitorios=fallidos_t,
            rechazados=rechazados,
            sin_contenido=False,
            correlativo_id=correlativo_id,
            errores=errores,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _contar_contenido(
        self,
        *,
        despacho_id: UUID,
        fecha: date,
        ahora: datetime,
        top_bo: int,
        top_noticias: int,
    ) -> tuple[int, int]:
        """Devuelve (n_bo_accionables, n_noticias_relevantes_24h)."""
        bo = await self._accionables.listar_por_despacho_y_fecha(
            despacho_id=despacho_id, fecha=fecha, top_n=top_bo,
        )
        # Noticias relevantes en ventana 24h hasta `ahora`. Esto cubre
        # el ciclo de polling (cada 15 min, 96 corridas por día).
        noticias = await self._relevantes.listar_por_despacho_24h(
            despacho_id=despacho_id, hasta=ahora, top_n=top_noticias,
        )
        return len(bo), len(noticias)

    async def _enviar_a(
        self,
        *,
        dest: Destinatario,
        fecha: date,
        resumen_corto: str,
        correlativo_id: UUID,
        ahora: datetime,
    ) -> tuple[bool, bool]:
        """Manda al destinatario individual. Devuelve (ok, transitorio)
        donde transitorio solo aplica si !ok."""
        assert dest.id is not None
        envio = await self._envios.crear(
            EnvioWhatsApp(
                id=None,
                destinatario_id=dest.id,
                despacho_id=dest.despacho_id,
                plantilla_name=PLANTILLA_BRIEFING_DIARIO,
                tipo=TipoEnvio.BRIEFING_DIARIO,
                payload_params={
                    "nombre": _primer_nombre(dest.nombre),
                    "fecha": fecha.isoformat(),
                    "resumen_corto": resumen_corto,
                },
                correlativo_id=correlativo_id,
            ),
        )
        resultado = await self._sender.enviar(
            telefono_e164=dest.telefono_e164,
            plantilla_name=PLANTILLA_BRIEFING_DIARIO,
            idioma="es_AR",
            body_params_ordered=[
                _primer_nombre(dest.nombre),
                fecha.isoformat(),
                resumen_corto,
            ],
        )
        assert envio.id is not None
        if resultado.exitoso and resultado.message_id_meta:
            await self._envios.marcar_enviado(
                envio_id=envio.id,
                message_id_meta=resultado.message_id_meta,
                enviado_en=ahora,
            )
            return True, False

        await self._envios.marcar_fallido(
            envio_id=envio.id,
            error=resultado.error or "sin_detalle",
            rechazado=resultado.rechazado,
        )
        # Si fue opt-out de Meta, marcar al destinatario para no
        # reintentar mañana.
        if (
            resultado.rechazado
            and resultado.error_meta_code == META_CODE_OPT_OUT
        ):
            await self._marcar_destinatario_opt_out(dest, ts=ahora)

        return False, not resultado.rechazado

    async def _marcar_destinatario_opt_out(
        self, dest: Destinatario, *, ts: datetime,
    ) -> None:
        opt_in_en = dest.opt_in_en or (ts - timedelta(seconds=1))
        nuevo = Destinatario(
            id=dest.id,
            despacho_id=dest.despacho_id,
            usuario_id=dest.usuario_id,
            nombre=dest.nombre,
            rol_interno=dest.rol_interno,
            telefono_e164=dest.telefono_e164,
            recibe_briefing_diario=dest.recibe_briefing_diario,
            recibe_alertas_menciones=dest.recibe_alertas_menciones,
            recibe_alertas_otras=dest.recibe_alertas_otras,
            opt_in_en=opt_in_en,
            opt_out_en=ts,
            activo=False,
        )
        await self._destinatarios.actualizar(nuevo)


# ---------------------------------------------------------------------------
# Funciones puras
# ---------------------------------------------------------------------------


def _primer_nombre(nombre_completo: str) -> str:
    """Para la plantilla mostramos solo el primer nombre — más
    natural y respeta cualquier límite de chars."""
    primer = nombre_completo.strip().split(" ", 1)[0]
    return primer[:40] or "Despacho"


def _componer_resumen(*, n_bo: int, n_noticias: int) -> str:
    """Compone el resumen corto que va como {{3}} en la plantilla.

    Cap conservador 180 chars (la plantilla está aprobada con texto
    de tamaño X; Meta rechaza con código 131056 si el contenido
    excede mucho ese tamaño).
    """
    partes: list[str] = []
    if n_bo > 0:
        partes.append(
            f"{n_bo} norma{'s' if n_bo != 1 else ''} accionable"
            f"{'s' if n_bo != 1 else ''} del BO",
        )
    if n_noticias > 0:
        partes.append(
            f"{n_noticias} noticia{'s' if n_noticias != 1 else ''} "
            "relevante" + ("s" if n_noticias != 1 else ""),
        )
    texto = " y ".join(partes) if partes else "sin novedades"
    return texto[:MAX_RESUMEN_CORTO_CHARS]
