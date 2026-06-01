"""Caso de uso: generar el Briefing pre-sesión.

Orquesta todo lo que armamos en feat/24, 25, 27, 28 + las votaciones
nominales de feat/26 para producir el `Briefing` que alimenta el PDF.

Diseño:
- Cache-aware: si ya hay un briefing para (despacho, OD) → devolverlo.
- Recibe `AsyncSession` directo (anti-pattern documentado, igual que
  `CalcularInteligenciaExpediente`) para hacer queries ad-hoc.
- Composición: usa `SugerirCofirmantes`, `BuscarAntecedenteParecido`,
  `CalcularInteligenciaExpediente`, `ClasificarExpedienteTematicamente`
  como sub-use-cases.

Limitaciones v1:
- Recomendación de voto en página 3 es heurística simple basada en
  antecedentes. No usa todavía votaciones nominales reales por bloque —
  eso queda para v2 (cuando enchufemos consulta a `voto_legislador`).
- Alertas son básicas. No detecta "proyecto rival entra al OD en mi área"
  todavía — se agrega cuando enchufemos áreas en alertas.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from uuid import UUID, uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from praxis.application.ports import (
    BriefingRepository,
    ExpedienteAreaTematicaRepository,
    ExpedienteRepository,
    LlmProvider,
    OrdenDelDiaRepository,
    SeguimientoExpedienteRepository,
)
from praxis.application.use_cases.buscar_antecedente_parecido import (
    BuscarAntecedenteParecido,
)
from praxis.application.use_cases.calcular_inteligencia import (
    CalcularInteligenciaExpediente,
)
from praxis.application.use_cases.clasificar_area_tematica import (
    ClasificarExpedienteTematicamente,
)
from praxis.application.use_cases.sugerir_cofirmantes import (
    SugerirCofirmantes,
)
from praxis.domain import (
    AlertaBriefing,
    AntecedenteParecido,
    AreaTematica,
    Briefing,
    EstadoExpediente,
    Expediente,
    ProyectoEnAreaBriefing,
    RecomendacionVoto,
    RolEnDespacho,
    SeccionAreaBriefing,
    SeccionProyectoBriefing,
)

# Cantidad máxima de alertas en página 1.
_MAX_ALERTAS = 5
# Threshold de "caduca pronto" para alerta media.
_DIAS_PARA_CADUCAR_ALERTA = 30


class GenerarBriefing:
    """Caso de uso principal del briefing pre-sesión."""

    def __init__(
        self,
        *,
        session: AsyncSession,
        expedientes: ExpedienteRepository,
        seguimientos: SeguimientoExpedienteRepository,
        clasificaciones: ExpedienteAreaTematicaRepository,
        ordenes_del_dia: OrdenDelDiaRepository,
        briefings: BriefingRepository,
        llm: LlmProvider,
    ) -> None:
        self._session = session
        self._expedientes = expedientes
        self._seguimientos = seguimientos
        self._clasificaciones = clasificaciones
        self._ordenes_del_dia = ordenes_del_dia
        self._briefings = briefings
        self._llm = llm

    async def execute(
        self,
        *,
        despacho_id: UUID,
        orden_del_dia_id: UUID,
        regenerar: bool = False,
        bloque_despacho: str | None = None,
        firmantes_despacho: list[str] | None = None,
    ) -> Briefing:
        # 1. Cache hit
        if not regenerar:
            cacheado = await self._briefings.buscar_por_despacho_y_od(
                despacho_id=despacho_id,
                orden_del_dia_id=orden_del_dia_id,
            )
            if cacheado is not None:
                return cacheado
        else:
            await self._briefings.eliminar(
                despacho_id=despacho_id,
                orden_del_dia_id=orden_del_dia_id,
            )

        od = await self._ordenes_del_dia.buscar_por_id(orden_del_dia_id)
        if od is None:
            raise ValueError(
                f"OrdenDelDia {orden_del_dia_id} no existe para despacho {despacho_id}"
            )

        # 2. Cargar expedientes del OD
        expedientes_od: list[Expediente] = []
        for exp_id in od.expedientes_ids:
            exp = await self._expedientes.buscar_por_id(exp_id)
            if exp is not None:
                expedientes_od.append(exp)

        # 3. Cruzar con seguimientos del despacho
        seguimientos = await self._seguimientos.listar_por_despacho(
            despacho_id, incluir_archivados=False,
        )
        seguimientos_por_exp_id: dict[UUID, bool] = {
            s.expediente_id: True for s in seguimientos
        }

        # 4. Asegurar área temática de cada expediente del OD (clasifica
        #    los que no estén cacheados). El sub-use-case es idempotente.
        clasificador = ClasificarExpedienteTematicamente(
            expedientes=self._expedientes,
            clasificaciones=self._clasificaciones,
            llm=self._llm,
        )
        for exp in expedientes_od:
            if exp.id is None:
                continue
            await clasificador.execute(exp.id)

        # 5. Secciones de página 2 (proyectos del despacho)
        secciones_proyectos: list[SeccionProyectoBriefing] = []
        alertas: list[AlertaBriefing] = []
        autor_count = 0
        cofirmante_count = 0

        cofirmantes_uc = SugerirCofirmantes(
            session=self._session,
            expedientes=self._expedientes,
            clasificaciones=self._clasificaciones,
        )
        antecedente_uc = BuscarAntecedenteParecido(
            session=self._session,
            expedientes=self._expedientes,
            clasificaciones=self._clasificaciones,
        )
        inteligencia_uc = CalcularInteligenciaExpediente(
            session=self._session,
            expedientes=self._expedientes,
        )

        for exp in expedientes_od:
            if exp.id is None:
                continue
            if exp.id not in seguimientos_por_exp_id:
                continue

            rol = _rol_del_despacho(exp, firmantes_despacho or [])
            if rol == "autor":
                autor_count += 1
            else:
                cofirmante_count += 1

            clasif = await self._clasificaciones.buscar_por_expediente(exp.id)
            area = clasif.area if clasif is not None else AreaTematica.OTROS

            argumentos = await self._llm.generar_argumentos(exp)
            contraargumentos = await self._llm.generar_argumentos(
                exp, contraargumentos=True,
            )

            cofirmantes = await cofirmantes_uc.execute(
                exp.id,
                excluir_bloques=[bloque_despacho] if bloque_despacho else (),
                excluir_firmantes=firmantes_despacho or (),
            )
            antecedente = await antecedente_uc.execute(exp.id)

            inteligencia = await inteligencia_uc.execute(exp.id)
            dias_en_etapa = inteligencia.progreso.dias_en_etapa_actual

            secciones_proyectos.append(
                SeccionProyectoBriefing(
                    expediente_id=exp.id,
                    numero=exp.numero,
                    titulo=exp.titulo,
                    estado=exp.estado,
                    tipo=exp.tipo,
                    rol_despacho=rol,
                    area=area,
                    dias_en_etapa=dias_en_etapa,
                    argumentos=argumentos,
                    contraargumentos=contraargumentos,
                    cofirmantes_naturales=cofirmantes,
                    antecedente=antecedente,
                )
            )

            # Alertas asociadas a este proyecto.
            alertas.extend(_alertas_para(exp, antecedente))

        # 6. Página 3: el resto del OD por área temática
        secciones_areas = await self._construir_secciones_areas(
            expedientes_od,
            seguimientos_por_exp_id,
            antecedente_uc=antecedente_uc,
        )

        # 7. Ordenar + recortar alertas
        alertas = _priorizar(alertas)[:_MAX_ALERTAS]

        # 8. Construir + persistir el Briefing
        briefing = Briefing(
            id=uuid4(),
            despacho_id=despacho_id,
            orden_del_dia_id=orden_del_dia_id,
            modelo_llm=self._llm.nombre_modelo,
            proyectos_del_despacho_total=autor_count + cofirmante_count,
            proyectos_como_autor=autor_count,
            proyectos_como_cofirmante=cofirmante_count,
            alertas=alertas,
            secciones_proyectos=secciones_proyectos,
            secciones_areas=secciones_areas,
        )
        return await self._briefings.crear(briefing)

    async def _construir_secciones_areas(
        self,
        expedientes_od: list[Expediente],
        seguimientos_por_exp_id: dict[UUID, bool],
        *,
        antecedente_uc: BuscarAntecedenteParecido,
    ) -> list[SeccionAreaBriefing]:
        por_area: dict[AreaTematica, list[ProyectoEnAreaBriefing]] = defaultdict(
            list
        )
        for exp in expedientes_od:
            if exp.id is None:
                continue
            if exp.id in seguimientos_por_exp_id:
                continue  # los del despacho van a página 2
            clasif = await self._clasificaciones.buscar_por_expediente(exp.id)
            area = clasif.area if clasif is not None else AreaTematica.OTROS

            recomendacion, razon = await _recomendacion_voto(
                exp, antecedente_uc,
            )

            autor = exp.autor_principal
            por_area[area].append(
                ProyectoEnAreaBriefing(
                    expediente_id=exp.id,
                    numero=exp.numero,
                    titulo=exp.titulo,
                    autor_principal=autor.nombre if autor else None,
                    bloque_autor=autor.bloque if autor else None,
                    recomendacion=recomendacion,
                    razon=razon,
                )
            )
        return [
            SeccionAreaBriefing(area=area, proyectos=proys)
            for area, proys in sorted(por_area.items(), key=lambda x: x[0].value)
        ]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _rol_del_despacho(
    expediente: Expediente, firmantes_despacho: list[str],
) -> RolEnDespacho:
    """Devuelve 'autor' si el legislador titular firma con orden=1, else cofirmante."""
    if not firmantes_despacho:
        # Sin info de firmantes del despacho, asumimos cofirmante.
        return "cofirmante"
    nombres_norm = [n.upper().strip() for n in firmantes_despacho]
    autor = expediente.autor_principal
    if autor and autor.nombre.upper().strip() in nombres_norm:
        return "autor"
    return "cofirmante"


def _alertas_para(
    expediente: Expediente,
    antecedente: AntecedenteParecido | None,
) -> list[AlertaBriefing]:
    out: list[AlertaBriefing] = []

    # Alta: a punto de votarse
    if expediente.estado in (
        EstadoExpediente.CON_DICTAMEN,
        EstadoExpediente.MEDIA_SANCION_HCDN,
        EstadoExpediente.MEDIA_SANCION_HSN,
    ):
        out.append(
            AlertaBriefing(
                prioridad="alta",
                titulo=f"{expediente.numero} en condiciones de votarse",
                detalle=(
                    f"Estado actual: {expediente.estado.value}. "
                    "Preparar argumentos y posición de bloque."
                ),
                expediente_id=expediente.id,
            )
        )

    # Alta: caduca pronto
    if expediente.fecha_caducidad is not None:
        dias = (expediente.fecha_caducidad - date.today()).days
        if 0 <= dias <= _DIAS_PARA_CADUCAR_ALERTA:
            out.append(
                AlertaBriefing(
                    prioridad="alta",
                    titulo=f"{expediente.numero} caduca en {dias} días",
                    detalle=(
                        "Pedir prórroga o impulsar tratamiento antes "
                        f"del {expediente.fecha_caducidad.isoformat()} "
                        "(Ley 13.640)."
                    ),
                    expediente_id=expediente.id,
                )
            )

    # Media: hay antecedente parecido sancionado / con media sanción
    if antecedente is not None and antecedente.estado_terminal in (
        EstadoExpediente.SANCIONADO,
        EstadoExpediente.MEDIA_SANCION_HCDN,
        EstadoExpediente.MEDIA_SANCION_HSN,
    ):
        out.append(
            AlertaBriefing(
                prioridad="media",
                titulo=(
                    f"Antecedente afín para {expediente.numero}: "
                    f"{antecedente.numero}"
                ),
                detalle=(
                    f"'{antecedente.titulo[:70]}' alcanzó "
                    f"{antecedente.estado_terminal.value}. "
                    "Citarlo como precedente en la fundamentación."
                ),
                expediente_id=expediente.id,
            )
        )

    return out


_PRIORIDAD_ORDEN = {"alta": 0, "media": 1, "baja": 2}


def _priorizar(alertas: list[AlertaBriefing]) -> list[AlertaBriefing]:
    return sorted(alertas, key=lambda a: _PRIORIDAD_ORDEN.get(a.prioridad, 99))


async def _recomendacion_voto(
    expediente: Expediente,
    antecedente_uc: BuscarAntecedenteParecido,
) -> tuple[RecomendacionVoto, str]:
    """Recomendación simplificada: si hay antecedente positivo, a favor.

    v2 va a usar votaciones nominales reales por bloque. v1 es heurística
    sobre antecedentes — el asesor humano siempre puede sobreescribir.
    """
    if expediente.id is None:
        return ("sin_recomendacion", "Expediente sin id persistido.")
    antec = await antecedente_uc.execute(expediente.id)
    if antec is None:
        return (
            "sin_recomendacion",
            "Sin antecedente histórico claro. Validar con jefe de bloque.",
        )
    if antec.estado_terminal in (
        EstadoExpediente.SANCIONADO,
        EstadoExpediente.MEDIA_SANCION_HCDN,
        EstadoExpediente.MEDIA_SANCION_HSN,
    ):
        return (
            "a_favor",
            f"Antecedente {antec.numero} terminó como {antec.estado_terminal.value}.",
        )
    return (
        "abstencion",
        f"Antecedente {antec.numero} terminó como {antec.estado_terminal.value}.",
    )
