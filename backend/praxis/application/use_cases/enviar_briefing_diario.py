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
    ComisionHcdnRepository,
    DestinatarioRepository,
    EnvioWhatsAppRepository,
    MencionRepository,
    NormaBOAccionableRepository,
    NormaBORepository,
    OrdenDelDiaRepository,
    WhatsAppSender,
)
from praxis.domain import (
    AccionableEvento,
    AccionSugerida,
    Destinatario,
    EnvioWhatsApp,
    OrdenDelDia,
    ReunionComision,
    TipoEnvio,
    TipoEvento,
    TonoMencion,
)

log = logging.getLogger(__name__)

PLANTILLA_BRIEFING_DIARIO = "briefing_diario_v2"
# Idioma de la plantilla v2 subida a Meta (Spanish sin variante regional).
IDIOMA_PLANTILLA = "es"
# v2: en el WhatsApp solo entran 2 ítems por sección (uno arriba, otro
# abajo). Pero pedimos hasta 5 al repositorio para (a) alimentar la UI
# preview y (b) poder decir "Y N más" cuando hay más de 2.
TOP_BO_DEFAULT = 5
TOP_NOTICIAS_DEFAULT = 5
# En el mensaje van solo estos.
ITEMS_POR_SECCION_EN_MSG = 2
TOP_MENCIONES_DEFAULT = 2
# 1024 chars permite Meta en el body — 174 fijos del template = 850 libres.
MAX_RESUMEN_CORTO_CHARS = 850
MAX_BODY_RICH_CHARS = 1000
LINK_BRIEFING_DEFAULT = "praxisasesor.app/d"

# Máximo por variable individual del template. Meta permite 1024 pero
# WhatsApp corta feo si un ítem supera ~140 chars, así que rateamos ahí.
MAX_ITEM_CHARS = 140
# Máximo del título dentro del ítem (antes del ": dominio/path").
MAX_TITULO_CHARS = 95

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
    # v2 template: cada item lleva su link. Puede ser None cuando la
    # fuente no persiste URL (menciones sin artículo asociado).
    url: str | None = None


@dataclass(frozen=True, slots=True)
class ResumenMenciones:
    """Resumen 24hs para el bloque MENCIONES del briefing v2."""

    total: int
    criticas: int
    top: list[ItemBriefing]           # 2 más recientes con URL del artículo


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
        menciones: MencionRepository | None = None,
        ordenes_del_dia: OrdenDelDiaRepository | None = None,
        comisiones: ComisionHcdnRepository | None = None,
        legislador_titular_apellido: str | None = None,
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
        self._menciones = menciones
        self._ordenes_del_dia = ordenes_del_dia
        self._comisiones = comisiones
        self._legislador_apellido = legislador_titular_apellido

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

        proxima_od = await self._resolver_proxima_sesion(
            despacho_id=despacho_id, hoy=fecha,
        )
        menciones_24h = await self._resumir_menciones_24h(
            despacho_id=despacho_id, ahora=ts,
        )
        agenda = await self._resolver_agenda_comisiones(
            hoy=fecha,
        )

        if (
            not items_bo
            and not items_noticias
            and proxima_od is None
            and menciones_24h.total == 0
            and not agenda
        ):
            return ResultadoBriefingDiario(
                despacho_id=despacho_id,
                destinatarios_objetivo=len(elegibles),
                enviados_ok=0,
                fallidos_transitorios=0,
                rechazados=0,
                sin_contenido=True,
                correlativo_id=correlativo_id,
            )

        # Precomputamos los 10 params una sola vez con nombre placeholder
        # del despacho — cuando enviemos por destinatario, sustituimos {{1}}
        # por el primer nombre real, todo lo demás no varía.
        params_base = _componer_params_v2(
            nombre="Despacho",
            fecha=fecha,
            agenda=agenda,
            proxima_sesion=proxima_od,
            items_bo=items_bo,
            items_noticias=items_noticias,
            resumen_menciones=menciones_24h,
        )
        resumen_corto = _preview_multilinea(params_base)
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
                    params_base=params_base,
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
            titulo_url = await self._titulo_url_norma(accionable.norma_id)
            titulo, url = titulo_url or ("norma BO", "")
            items_bo.append(
                ItemBriefing(
                    titulo_corto=titulo[:MAX_TITULO_CHARS],
                    accion=enr.accion_sugerida if enr else None,
                    razon_breve=enr.razon_para_despacho[:100] if enr else None,
                    url=url or None,
                ),
            )

        items_noticias: list[ItemBriefing] = []
        for relevante in noticias_raw:
            enr = await self._buscar_enriquecido(
                despacho_id=despacho_id,
                tipo=TipoEvento.ARTICULO,
                evento_id=relevante.articulo_id,
            )
            titulo_url = await self._titulo_url_articulo(relevante.articulo_id)
            titulo, url = titulo_url or ("noticia", "")
            items_noticias.append(
                ItemBriefing(
                    titulo_corto=titulo[:MAX_TITULO_CHARS],
                    accion=enr.accion_sugerida if enr else None,
                    razon_breve=enr.razon_para_despacho[:100] if enr else None,
                    url=url or None,
                ),
            )

        return items_bo, items_noticias

    async def _resolver_agenda_comisiones(
        self, *, hoy: date,
    ) -> list[tuple[ReunionComision, str, str]]:
        """Próximas reuniones (hasta 5) de las comisiones que integra el
        legislador titular, en los próximos 7 días. Devuelve
        `(reunion, nombre_comision, url_oficial)`."""
        if self._comisiones is None or not self._legislador_apellido:
            return []
        try:
            return await self._comisiones.proximas_reuniones_por_apellido(
                apellido=self._legislador_apellido,
                desde=hoy,
                hasta=hoy + timedelta(days=7),
                limit=5,
            )
        except Exception as exc:
            log.warning("agenda comisiones falló: %s", exc)
            return []

    async def _resolver_proxima_sesion(
        self, *, despacho_id: UUID, hoy: date,
    ) -> OrdenDelDia | None:
        """Devuelve la próxima OD con `fecha_sesion >= hoy`, o None."""
        if self._ordenes_del_dia is None:
            return None
        try:
            ods = await self._ordenes_del_dia.listar_por_despacho(
                despacho_id, limit=20,
            )
        except Exception as exc:
            log.warning("listar OD falló: %s", exc)
            return None
        futuras = sorted(
            (od for od in ods if od.fecha_sesion >= hoy),
            key=lambda od: od.fecha_sesion,
        )
        return futuras[0] if futuras else None

    async def _resumir_menciones_24h(
        self, *, despacho_id: UUID, ahora: datetime,
    ) -> ResumenMenciones:
        """Cuenta menciones por tono en las últimas 24h + top 2 con link
        al artículo original para el briefing v2."""
        if self._menciones is None:
            return ResumenMenciones(total=0, criticas=0, top=[])
        try:
            ms = await self._menciones.listar_historico(
                despacho_id=despacho_id,
                desde=ahora - timedelta(hours=24),
                hasta=ahora,
            )
        except Exception as exc:
            log.warning("listar menciones falló: %s", exc)
            return ResumenMenciones(total=0, criticas=0, top=[])
        criticas = sum(1 for m in ms if m.tono == TonoMencion.CRITICO)

        # Ordenar críticas primero, después por detectado_en desc.
        def _key(m):
            return (
                0 if m.tono == TonoMencion.CRITICO else 1,
                -(m.detectado_en.timestamp()) if m.detectado_en else 0,
            )
        ranked = sorted(ms, key=_key)

        top: list[ItemBriefing] = []
        for m in ranked[:TOP_MENCIONES_DEFAULT]:
            titulo_url = await self._titulo_url_articulo(m.articulo_id)
            if titulo_url is None:
                # sin artículo cacheado: mostramos el snippet como
                # fallback, sin URL.
                titulo = m.snippet_contexto.strip()[:MAX_TITULO_CHARS]
                top.append(ItemBriefing(
                    titulo_corto=titulo,
                    accion=None,
                    razon_breve=None,
                    url=None,
                ))
                continue
            titulo, url = titulo_url
            top.append(ItemBriefing(
                titulo_corto=titulo[:MAX_TITULO_CHARS],
                accion=None,
                razon_breve=None,
                url=url or None,
            ))
        return ResumenMenciones(
            total=len(ms), criticas=criticas, top=top,
        )

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

    async def _titulo_url_norma(
        self, norma_id: UUID,
    ) -> tuple[str, str] | None:
        """Devuelve `(titulo_compuesto, url_oficial)` o None."""
        if self._normas_bo is None:
            return None
        n = await self._normas_bo.buscar_por_id(norma_id)
        if n is None:
            return None
        titulo = f"{n.tipo_norma} {n.numero_norma}"
        # Enriquecemos con el organismo emisor abreviado para que se
        # entienda de qué se trata sin abrir el link.
        sumario_corto = (n.sumario or "").strip().split(".")[0][:60]
        if sumario_corto:
            titulo = f"{titulo} {sumario_corto}"
        return (titulo, n.url_oficial or "")

    async def _titulo_url_articulo(
        self, articulo_id: UUID,
    ) -> tuple[str, str] | None:
        """Devuelve `(titulo_articulo, url_articulo)` o None."""
        if self._articulos is None:
            return None
        a = await self._articulos.buscar_por_id(articulo_id)
        if a is None:
            return None
        return (a.titulo, a.url or "")

    async def _enviar_a(
        self,
        *,
        dest: Destinatario,
        fecha: date,
        params_base: list[str],
        correlativo_id: UUID,
        ahora: datetime,
    ) -> tuple[bool, bool]:
        assert dest.id is not None
        # Copiamos y sustituimos {{1}} por el nombre real del destinatario.
        params_dest = list(params_base)
        params_dest[0] = _sanitizar_para_meta(
            _primer_nombre(dest.nombre),
        )[:40] or "Despacho"
        envio = await self._envios.crear(
            EnvioWhatsApp(
                id=None,
                destinatario_id=dest.id,
                despacho_id=dest.despacho_id,
                plantilla_name=PLANTILLA_BRIEFING_DIARIO,
                tipo=TipoEnvio.BRIEFING_DIARIO,
                payload_params={
                    f"p{i + 1}": val for i, val in enumerate(params_dest)
                },
                correlativo_id=correlativo_id,
            ),
        )
        resultado = await self._sender.enviar(
            telefono_e164=dest.telefono_e164,
            plantilla_name=PLANTILLA_BRIEFING_DIARIO,
            idioma=IDIOMA_PLANTILLA,
            body_params_ordered=params_dest,
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


_MESES_ES = [
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
]


def _fecha_humana(fecha: date) -> str:
    """`2026-06-23` → `23 de junio`. Sin año en el día a día."""
    return f"{fecha.day} de {_MESES_ES[fecha.month - 1]}"


def _sanitizar_para_meta(texto: str) -> str:
    """Meta rechaza cualquier whitespace que no sea ` ` simple en parámetros
    de templates (error 132018). Mapeamos todo whitespace consecutivo
    (incl. \\n, \\r, \\t, no-break-space, etc.) a un único espacio."""
    import re as _re
    return _re.sub(r"\s+", " ", texto).strip()


def _dominio_recortado(url: str) -> str:
    """`https://boletinoficial.gob.ar/xxx?a=b` → `boletinoficial.gob.ar/xxx`.

    - Saca scheme y `www.`.
    - Descarta query string y fragment.
    - Corta a 50 chars manteniendo el dominio (WhatsApp igual detecta
      el link aunque venga truncado, siempre que sea host reconocible).
    """
    limpio = url.strip()
    for prefijo in ("https://", "http://"):
        if limpio.startswith(prefijo):
            limpio = limpio[len(prefijo):]
    if limpio.startswith("www."):
        limpio = limpio[4:]
    # Descartar query / fragment.
    for sep in ("?", "#"):
        idx = limpio.find(sep)
        if idx != -1:
            limpio = limpio[:idx]
    if len(limpio) > 50:
        # Preservar dominio + cola.
        limpio = limpio[:50]
    return limpio


def _formato_item(titulo: str, url: str | None) -> str:
    """`Título: dominio/path`, saneado y capado a MAX_ITEM_CHARS."""
    titulo_limpio = _sanitizar_para_meta(titulo)[:MAX_TITULO_CHARS]
    if url:
        return f"{titulo_limpio}: {_dominio_recortado(url)}"[:MAX_ITEM_CHARS]
    return titulo_limpio[:MAX_ITEM_CHARS]


def _dos_items(
    items: list[ItemBriefing],
    n_total: int,
    *,
    label_vacio: str,
    label_solo_uno: str = "Sin más novedades hoy",
) -> tuple[str, str]:
    """Devuelve `(item1, item2)` para una sección, siguiendo reglas de
    relleno del briefing v2:

    - 2+ items: los dos con link; si `n_total > 2`, item2 lleva
      cola ` — Y N más en Praxis Asesor`.
    - 1 item: item1 con link, item2 = `label_solo_uno` o "Y N más..."
    - 0 items: item1 = `label_vacio`, item2 = "—".
    """
    if not items:
        return (label_vacio, "—")
    item_1 = _formato_item(items[0].titulo_corto, items[0].url)
    if len(items) >= 2:
        item_2 = _formato_item(items[1].titulo_corto, items[1].url)
        if n_total > 2:
            item_2 = (
                f"{item_2} — Y {n_total - 2} más en Praxis Asesor"
            )[:MAX_ITEM_CHARS]
        return (item_1, item_2)
    # len == 1
    if n_total > 1:
        return (item_1, f"Y {n_total - 1} más en Praxis Asesor")
    return (item_1, label_solo_uno)


def _item_agenda(reunion: ReunionComision, nombre_com: str, url: str) -> str:
    """`AsuntosConstitucionales se reúne mañana 15hs: interpelación…`."""
    from datetime import date as _date
    hoy = _date.today()
    delta = (reunion.fecha - hoy).days
    cuando = (
        "hoy" if delta == 0
        else "mañana" if delta == 1
        else reunion.fecha.strftime("%d/%m")
    )
    hora = (
        f" {reunion.hora.strftime('%H:%M')}hs"
        if reunion.hora else ""
    )
    tema = (reunion.tema_corto or reunion.descripcion or "").strip()
    if tema:
        tema_corto = _sanitizar_para_meta(tema)[:60]
        titulo = f"{nombre_com} {cuando}{hora}, {tema_corto}"
    else:
        titulo = f"{nombre_com} se reúne {cuando}{hora}"
    return _formato_item(titulo, url or None)


def _dos_items_agenda(
    agenda: list[tuple[ReunionComision, str, str]],
    proxima_sesion: OrdenDelDia | None,
    hoy: date,
) -> tuple[str, str]:
    """Compone los 2 slots de AGENDA para el template v2."""
    if agenda:
        n = len(agenda)
        item_1 = _item_agenda(*agenda[0])
        if n >= 2:
            item_2 = _item_agenda(*agenda[1])
            if n > 2:
                item_2 = (
                    f"{item_2} — Y {n - 2} más esta semana"
                )[:MAX_ITEM_CHARS]
            return (item_1, item_2)
        # Solo 1 reunión de comisión — fallback en item 2 con sesión de
        # recinto si hay.
        if proxima_sesion is not None:
            titulo = (proxima_sesion.titulo or "Sesión convocada").strip()
            delta = (proxima_sesion.fecha_sesion - hoy).days
            cuando = (
                "hoy" if delta == 0
                else "mañana" if delta == 1
                else proxima_sesion.fecha_sesion.strftime("%d/%m")
            )
            item_2 = _formato_item(
                f"Recinto: {titulo} ({cuando})", None,
            )
            return (item_1, item_2)
        return (item_1, "Sin más reuniones esta semana")
    # No hay agenda de comisiones — si hay sesión de recinto, arriba.
    if proxima_sesion is not None:
        titulo = (proxima_sesion.titulo or "Sesión convocada").strip()
        delta = (proxima_sesion.fecha_sesion - hoy).days
        cuando = (
            "hoy" if delta == 0
            else "mañana" if delta == 1
            else proxima_sesion.fecha_sesion.strftime("%d/%m")
        )
        item_1 = _formato_item(f"Recinto: {titulo} ({cuando})", None)
        return (item_1, "Sin reuniones de comisión esta semana")
    return (
        "Sin reuniones esta semana en tus comisiones",
        "—",
    )


def _componer_params_v2(
    *,
    nombre: str,
    fecha: date,
    agenda: list[tuple[ReunionComision, str, str]],
    proxima_sesion: OrdenDelDia | None,
    items_bo: list[ItemBriefing],
    items_noticias: list[ItemBriefing],
    resumen_menciones: ResumenMenciones,
) -> list[str]:
    """Devuelve los 10 valores ordenados que consumen `{{1}}..{{10}}`
    de la plantilla `briefing_diario_v2`. Todos vienen ya sanitizados
    (sin `\\n`, sin tabs) y bajo MAX_ITEM_CHARS por elemento."""
    p1 = _sanitizar_para_meta(nombre)[:40] or "Despacho"
    p2 = _fecha_humana(fecha)

    p3, p4 = _dos_items_agenda(agenda, proxima_sesion, fecha)
    p5, p6 = _dos_items(
        items_bo,
        n_total=len(items_bo),
        label_vacio="Sin novedades accionables hoy",
    )
    p7, p8 = _dos_items(
        items_noticias,
        n_total=len(items_noticias),
        label_vacio="Sin novedades en medios relevantes",
    )
    # Menciones: si hay 0, mensaje limpio; si hay 1 con URL, va + fallback;
    # si hay 2+ con URL, van dos + cola.
    if resumen_menciones.total == 0:
        p9 = "Sin menciones al despacho en 24 horas"
        p10 = "—"
    else:
        # Reutilizamos _dos_items con la lista top ya recortada.
        # Marcamos n_total = total real de menciones para la cola.
        p9, p10 = _dos_items(
            resumen_menciones.top,
            n_total=resumen_menciones.total,
            label_vacio="Sin menciones al despacho en 24 horas",
        )
    return [
        _sanitizar_para_meta(x)[:MAX_ITEM_CHARS]
        for x in (p1, p2, p3, p4, p5, p6, p7, p8, p9, p10)
    ]


def _preview_multilinea(params: list[str]) -> str:
    """Reconstruye visualmente el mensaje para la preview UI, con las
    mismas secciones que el template. No se manda por WhatsApp — solo
    se guarda en `ResultadoBriefingDiario.resumen_corto`."""
    assert len(params) == 10
    nombre, fecha, a1, a2, b1, b2, n1, n2, m1, m2 = params
    return (
        f"Hola {nombre}, tu briefing diario del {fecha}.\n\n"
        f"AGENDA DE COMISIONES\n• {a1}\n• {a2}\n\n"
        f"BOLETÍN OFICIAL\n• {b1}\n• {b2}\n\n"
        f"NOTICIAS DEL DÍA\n• {n1}\n• {n2}\n\n"
        f"MENCIONES AL DESPACHO\n• {m1}\n• {m2}\n\n"
        "— Praxis Asesor"
    )[:MAX_RESUMEN_CORTO_CHARS]


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
