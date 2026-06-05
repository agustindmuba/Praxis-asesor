"""Caso de uso: enviar el briefing diario por WhatsApp
(feat-41.4 + feat-42.4 — enriquecido con accionables del perfil).

Consolida en un solo mensaje las novedades del día para el despacho
y lo manda a cada destinatario activo que tenga el flag
`recibe_briefing_diario`.

**feat-42.4**: si para los BO + Noticias del día hay
`AccionableEvento` enriquecidos (generados con perfil opositor),
se priorizan e incluyen con título + acción sugerida en el texto.
Si no hay accionables enriquecidos, fallback al briefing plano
(número + tipo).

Pipeline:

1. Cargar despacho + destinatarios activos elegibles
   (`recibe_briefing_diario=True` + `puede_recibir(BRIEFING_DIARIO)`).
2. Resolver contenido del día:
   - Top N normas BO accionables (vía `NormaBOAccionableRepository`).
   - Top M artículos relevantes 24h (vía `ArticuloRelevanteRepository`).
   - Para cada uno: buscar `AccionableEvento` enriquecido si existe.
3. Componer 2 textos:
   - `resumen_corto` ≤180 chars — para la plantilla aprobada actual.
   - `body_rich` ≤1000 chars — para futuro modo text-free
     (cuando el destinatario respondió en las últimas 24h o cuando
     se aprueba plantilla v2).
4. Por cada destinatario: persist `EnvioWhatsApp` + llamar al sender.

El caso de uso NO commitea; el caller (Celery task) maneja la
sesión y commitea al final por despacho.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from praxis.application.ports import (
    AccionableEventoRepository,
    ArticuloRelevanteRepository,
    ArticuloRepository,
    DestinatarioRepository,
    EnvioWhatsAppRepository,
    NormaBOAccionableRepository,
    NormaBORepository,
    WhatsAppSender,
)
from praxis.domain import (
    AccionableEvento,
    AccionSugerida,
    Destinatario,
    EnvioWhatsApp,
    TipoEnvio,
    TipoEvento,
)

log = logging.getLogger(__name__)

PLANTILLA_BRIEFING_DIARIO = "briefing_diario"
TOP_BO_DEFAULT = 3
TOP_NOTICIAS_DEFAULT = 3
MAX_RESUMEN_CORTO_CHARS = 180
MAX_BODY_RICH_CHARS = 1000

# Código Meta para "recipient opted out" — marcamos al destinatario.
META_CODE_OPT_OUT = 131026

# Etiquetas cortas de acción para el body rich del WhatsApp (no usar
# las del UI que son más largas).
ACCION_SHORT: dict[AccionSugerida, str] = {
    AccionSugerida.PEDIDO_INFORMES: "📋 Informes",
    AccionSugerida.PROYECTO_CONTRAPOSICION: "📜 Contraproyecto",
    AccionSugerida.DECLARACION_CAMARA: "📢 Declaración",
    AccionSugerida.SILENCIO_ESTRATEGICO: "🤐 Silencio",
    AccionSugerida.RETWEET_CRITICO: "🔁 RT crítico",
    AccionSugerida.RETWEET_APOYO: "👍 RT apoyo",
    AccionSugerida.ARTICULO_OPINION: "✍️ Opinión",
    AccionSugerida.INTERPELACION: "⚖️ Interpelación",
    AccionSugerida.OTRO: "🔎 Revisar",
}


@dataclass(frozen=True, slots=True)
class ItemBriefing:
    """Renderable de una línea del briefing."""

    titulo_corto: str
    accion: AccionSugerida | None
    razon_breve: str | None


@dataclass(frozen=True, slots=True)
class ResultadoBriefingDiario:
    despacho_id: UUID
    destinatarios_objetivo: int
    enviados_ok: int
    fallidos_transitorios: int
    rechazados: int
    sin_contenido: bool
    correlativo_id: UUID
    resumen_corto: str = ""                 # debug / observabilidad
    body_rich: str = ""                     # debug / observabilidad
    items_bo: list[ItemBriefing] = field(default_factory=list)
    items_noticias: list[ItemBriefing] = field(default_factory=list)
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
        normas_bo: NormaBORepository | None = None,
        articulos: ArticuloRepository | None = None,
        accionables_enriquecidos: AccionableEventoRepository | None = None,
    ) -> None:
        self._destinatarios = destinatarios
        self._envios = envios
        self._accionables = accionables_bo
        self._relevantes = relevantes_noticias
        self._sender = sender
        # Opcionales para enriquecimiento — si no se pasan, fallback al
        # briefing plano original (compatibilidad con tests viejos).
        self._normas_bo = normas_bo
        self._articulos = articulos
        self._accionables_enriquecidos = accionables_enriquecidos

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

        items_bo, items_noticias = await self._resolver_items(
            despacho_id=despacho_id,
            fecha=fecha,
            ahora=ts,
            top_bo=top_bo,
            top_noticias=top_noticias,
        )

        if not items_bo and not items_noticias:
            return ResultadoBriefingDiario(
                despacho_id=despacho_id,
                destinatarios_objetivo=len(elegibles),
                enviados_ok=0,
                fallidos_transitorios=0,
                rechazados=0,
                sin_contenido=True,
                correlativo_id=correlativo_id,
            )

        resumen_corto = _componer_resumen_corto(
            n_bo=len(items_bo), n_noticias=len(items_noticias),
        )
        body_rich = _componer_body_rich(items_bo, items_noticias)

        if not elegibles:
            # Sin destinatarios pero hay contenido — devolvemos preview
            # igual (útil para UI preview / smoke).
            return ResultadoBriefingDiario(
                despacho_id=despacho_id,
                destinatarios_objetivo=0,
                enviados_ok=0,
                fallidos_transitorios=0,
                rechazados=0,
                sin_contenido=False,
                correlativo_id=correlativo_id,
                resumen_corto=resumen_corto,
                body_rich=body_rich,
                items_bo=items_bo,
                items_noticias=items_noticias,
            )

        enviados = 0
        fallidos_t = 0
        rechazados = 0
        errores: list[str] = []

        for dest in elegibles:
            try:
                ok, transitorio = await self._enviar_a(
                    dest=dest,
                    fecha=fecha,
                    resumen_corto=resumen_corto,
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
            resumen_corto=resumen_corto,
            body_rich=body_rich,
            items_bo=items_bo,
            items_noticias=items_noticias,
            errores=errores,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    async def _resolver_items(
        self,
        *,
        despacho_id: UUID,
        fecha: date,
        ahora: datetime,
        top_bo: int,
        top_noticias: int,
    ) -> tuple[list[ItemBriefing], list[ItemBriefing]]:
        """Carga accionables BO + Noticias y los enriquece con
        AccionableEvento si está disponible."""
        bo_raw = await self._accionables.listar_por_despacho_y_fecha(
            despacho_id=despacho_id, fecha=fecha, top_n=top_bo,
        )
        noticias_raw = await self._relevantes.listar_por_despacho_24h(
            despacho_id=despacho_id, hasta=ahora, top_n=top_noticias,
        )

        items_bo: list[ItemBriefing] = []
        for accionable in bo_raw:
            enr = await self._buscar_enriquecido(
                despacho_id=despacho_id,
                tipo=TipoEvento.NORMA_BO,
                evento_id=accionable.norma_id,
            )
            titulo = await self._titulo_norma(accionable.norma_id) or "norma BO"
            items_bo.append(
                ItemBriefing(
                    titulo_corto=titulo[:80],
                    accion=enr.accion_sugerida if enr else None,
                    razon_breve=enr.razon_para_despacho[:100] if enr else None,
                ),
            )

        items_noticias: list[ItemBriefing] = []
        for relevante in noticias_raw:
            enr = await self._buscar_enriquecido(
                despacho_id=despacho_id,
                tipo=TipoEvento.ARTICULO,
                evento_id=relevante.articulo_id,
            )
            titulo = await self._titulo_articulo(
                relevante.articulo_id,
            ) or "noticia"
            items_noticias.append(
                ItemBriefing(
                    titulo_corto=titulo[:80],
                    accion=enr.accion_sugerida if enr else None,
                    razon_breve=enr.razon_para_despacho[:100] if enr else None,
                ),
            )

        return items_bo, items_noticias

    async def _buscar_enriquecido(
        self, *, despacho_id: UUID, tipo: TipoEvento, evento_id: UUID,
    ) -> AccionableEvento | None:
        if self._accionables_enriquecidos is None:
            return None
        try:
            return await self._accionables_enriquecidos.buscar_por_evento(
                despacho_id=despacho_id,
                tipo_evento=tipo,
                evento_id=evento_id,
            )
        except Exception as exc:
            log.warning("buscar_por_evento falló (%s): %s", evento_id, exc)
            return None

    async def _titulo_norma(self, norma_id: UUID) -> str | None:
        if self._normas_bo is None:
            return None
        n = await self._normas_bo.buscar_por_id(norma_id)
        if n is None:
            return None
        return f"{n.tipo_norma} {n.numero_norma}"

    async def _titulo_articulo(self, articulo_id: UUID) -> str | None:
        if self._articulos is None:
            return None
        a = await self._articulos.buscar_por_id(articulo_id)
        return a.titulo if a is not None else None

    async def _enviar_a(
        self,
        *,
        dest: Destinatario,
        fecha: date,
        resumen_corto: str,
        correlativo_id: UUID,
        ahora: datetime,
    ) -> tuple[bool, bool]:
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
    primer = nombre_completo.strip().split(" ", 1)[0]
    return primer[:40] or "Despacho"


def _componer_resumen_corto(*, n_bo: int, n_noticias: int) -> str:
    """Resumen corto para el slot {{3}} de la plantilla aprobada
    (≤180 chars, conservador para no chocar con 131056)."""
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


def _componer_body_rich(
    items_bo: list[ItemBriefing], items_noticias: list[ItemBriefing],
) -> str:
    """Body rico para modo text-free (≤1000 chars). Render:

    📜 *Boletín Oficial*
    • [acción] Título corto — razón breve.
    • ...

    📰 *Noticias*
    • [acción] Título — razón.
    • ...

    Cuando no hay acción enriquecida, omite el prefijo.
    """
    partes: list[str] = []
    if items_bo:
        partes.append("📜 *Boletín Oficial*")
        for it in items_bo:
            partes.append("• " + _render_item(it))
    if items_noticias:
        if partes:
            partes.append("")
        partes.append("📰 *Noticias*")
        for it in items_noticias:
            partes.append("• " + _render_item(it))
    texto = "\n".join(partes)
    return texto[:MAX_BODY_RICH_CHARS]


def _render_item(it: ItemBriefing) -> str:
    prefijo = ""
    if it.accion is not None:
        prefijo = f"{ACCION_SHORT.get(it.accion, '🔎')} "
    base = f"{prefijo}{it.titulo_corto}"
    if it.razon_breve:
        base += f" — {it.razon_breve}"
    return base
