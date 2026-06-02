"""Puertos (interfaces) de la capa Application.

Cada puerto declara un contrato que la capa Infrastructure debe implementar.
Las implementaciones concretas (adaptadores) viven en `praxis.infrastructure`
y se inyectan en los casos de uso.

Regla hexagonal (ver `docs/adr/0001-stack-inicial.md`):
- `praxis.application` define los puertos pero NO conoce las implementaciones.
- `praxis.infrastructure` implementa los puertos.
- Los casos de uso reciben puertos por DI, nunca importan adaptadores
  directamente.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from uuid import UUID

from praxis.domain import (
    AreaTematica,
    AuthClaims,
    Briefing,
    Camara,
    Comision,
    Expediente,
    ExpedienteAreaTematica,
    ExpedienteQuery,
    MembresiaDespacho,
    NumeroExpediente,
    OrdenDelDia,
    PerfilInteresDespacho,
    ResultadoBusqueda,
    ResumenEjecutivo,
    SeguimientoExpediente,
    TipoExpediente,
    Usuario,
)
from praxis.domain.despacho import Despacho
from praxis.domain.legislador import Legislador


class FuenteExpedientes(ABC):
    """Puerto: una fuente desde la que se pueden obtener expedientes.

    Implementaciones esperadas:
    - `praxis.infrastructure.scrapers.hcdn.HcdnScraper`
    - `praxis.infrastructure.scrapers.hsn.HsnScraper`
    - Eventualmente: cache, persistencia local, otras fuentes públicas.

    Convención de errores:
    - `ExpedienteNoEncontrado` si el número no existe en la fuente.
    - `FuenteNoDisponible` si la fuente está caída o devuelve errores
      no-recuperables. Errores transitorios deben manejarse internamente
      con retries antes de propagar.
    """

    @abstractmethod
    async def buscar_por_numero(
        self,
        numero: NumeroExpediente,
        tipo: TipoExpediente | None = None,
    ) -> Expediente:
        """Devuelve el expediente identificado por `numero`.

        Args:
            numero: Identificador del expediente.
            tipo: Tipo del expediente. **Requerido para HSN** (la URL canónica
                lo incluye, ver spec `docs/specs/02-ingesta-hsn.md`). HCDN lo
                ignora (su búsqueda lo infiere del sumario). `None` para
                fuentes que no lo necesitan.

        Returns:
            Snapshot completo del expediente con todos los campos que la
            fuente pueda proveer.

        Raises:
            ExpedienteNoEncontrado: si la fuente no encuentra el expediente.
            FuenteNoDisponible: si la fuente falla por motivos externos.
            ValueError: si `numero.camara` no es compatible con la fuente,
                o si la fuente exige `tipo` y no se proveyó.
        """
        raise NotImplementedError


class CatalogoLegisladores(ABC):
    """Puerto: catálogo del padrón vigente de legisladores.

    Implementación esperada inicial: `praxis.infrastructure.padron.CsvPadronRepository`
    (lee de CSVs vendored del Observatorio). Futuras: DB, API oficial si existe.

    El padrón cambia con poca frecuencia (recambio bicameral, asunciones).
    Las implementaciones pueden cachear todo en memoria al inicio sin
    preocupación de staleness inmediata.
    """

    @abstractmethod
    def listar(self, camara: Camara) -> list[Legislador]:
        """Devuelve todos los legisladores vigentes de la cámara dada."""
        raise NotImplementedError

    @abstractmethod
    def buscar_por_slug(self, slug: str, camara: Camara) -> Legislador:
        """Devuelve el legislador identificado por su slug.

        Raises:
            KeyError: si no se encuentra el slug en esa cámara.
        """
        raise NotImplementedError

    @abstractmethod
    def buscar_por_nombre(self, query: str) -> list[Legislador]:
        """Devuelve legisladores cuyo apellido o nombre matche `query`
        (case-insensitive, substring). Busca en ambas cámaras.
        """
        raise NotImplementedError


class CatalogoComisiones(ABC):
    """Puerto: catálogo de comisiones legislativas.

    Implementación esperada inicial:
    `praxis.infrastructure.comisiones.LocalCatalogoComisiones` (lee CSV HCDN
    del Observatorio + JSON HSN oficial, ambos vendored).
    """

    @abstractmethod
    def listar(self, camara: Camara) -> list[Comision]:
        """Devuelve todas las comisiones registradas en la cámara dada."""
        raise NotImplementedError

    @abstractmethod
    def buscar_por_nombre(
        self,
        query: str,
        camara: Camara | None = None,
    ) -> list[Comision]:
        """Devuelve comisiones cuyo nombre contiene `query` (case-insensitive).

        Si `camara=None`, busca en ambas cámaras.
        """
        raise NotImplementedError


class DespachoRepository(ABC):
    """Puerto: persistencia de `Despacho` (el tenant).

    Implementación esperada inicial:
    `praxis.infrastructure.persistence.repositories.SqlAlchemyDespachoRepository`.
    """

    @abstractmethod
    async def crear(self, despacho: Despacho) -> Despacho:
        """Persiste un Despacho nuevo. Devuelve la entidad con id y timestamps poblados."""
        raise NotImplementedError

    @abstractmethod
    async def buscar_por_id(self, despacho_id: UUID) -> Despacho | None:
        """Devuelve el Despacho o None si no existe."""
        raise NotImplementedError

    @abstractmethod
    async def listar(self) -> list[Despacho]:
        """Devuelve todos los despachos. Sin paginación por ahora (volúmenes bajos)."""
        raise NotImplementedError


class ExpedienteRepository(ABC):
    """Puerto: persistencia de `Expediente` (+ firmantes, giros, trámite).

    No es tenant-scoped: el catálogo de expedientes es global (todos los
    despachos ven los mismos datos públicos). Lo tenant-scoped es el
    *seguimiento* del expediente por un despacho (otra entidad).
    """

    @abstractmethod
    async def crear(self, expediente: Expediente) -> Expediente:
        """Inserta un expediente nuevo con todos sus hijos. Devuelve la
        entidad hidratada (timestamps, etc.).
        """
        raise NotImplementedError

    @abstractmethod
    async def buscar_por_id(self, expediente_id: UUID) -> Expediente | None:
        """Devuelve el Expediente con relaciones cargadas, o None."""
        raise NotImplementedError

    @abstractmethod
    async def buscar_por_numero(self, numero: NumeroExpediente) -> Expediente | None:
        """Lookup por identidad natural `(numero, origen, anio, camara)`."""
        raise NotImplementedError

    @abstractmethod
    async def listar(self, *, limit: int = 50, offset: int = 0) -> list[Expediente]:
        """Lista paginada por orden de UUID (≈ orden temporal de inserción)."""
        raise NotImplementedError

    @abstractmethod
    async def buscar(self, query: ExpedienteQuery) -> ResultadoBusqueda:
        """Busca expedientes que matcheen el criterio.

        Devuelve `ResultadoBusqueda` con la página solicitada (`items`) y el
        `total` de matches del filtro (independiente de limit/offset). Ver
        `docs/specs/08-busqueda-expedientes.md`.
        """
        raise NotImplementedError

    @abstractmethod
    async def contar(self, query: ExpedienteQuery) -> int:
        """Cuenta matches del filtro, ignorando `limit/offset`.

        Útil si el caller solo necesita el total (ej. estadísticas, badge en UI).
        """
        raise NotImplementedError


class UsuarioRepository(ABC):
    """Puerto: persistencia de Usuario.

    No es tenant-scoped: un usuario puede pertenecer a múltiples despachos.
    Las membresías (con rol) se modelan en `MembresiaDespacho` aparte.
    """

    @abstractmethod
    async def crear(self, usuario: Usuario) -> Usuario:
        raise NotImplementedError

    @abstractmethod
    async def buscar_por_id(self, usuario_id: UUID) -> Usuario | None:
        raise NotImplementedError

    @abstractmethod
    async def buscar_por_email(self, email: str) -> Usuario | None:
        """Lookup case-insensitive sobre el email."""
        raise NotImplementedError

    @abstractmethod
    async def buscar_por_auth_provider_id(self, auth_provider_id: str) -> Usuario | None:
        """Lookup por el id del provider externo (Clerk u otro)."""
        raise NotImplementedError

    @abstractmethod
    async def listar(self) -> list[Usuario]:
        raise NotImplementedError

    @abstractmethod
    async def actualizar(self, usuario: Usuario) -> Usuario:
        """Actualiza los campos editables (email, nombre, activo) por id.

        El `id` es el discriminador — `auth_provider_id` también se respeta
        si viene seteado, para conexión inicial entre nuestra row pre-existente
        y un Clerk user_id que recién apareció.

        Raises:
            ValueError: si el usuario no existe en la DB.
        """
        raise NotImplementedError


class MembresiaDespachoRepository(ABC):
    """Puerto: persistencia de MembresiaDespacho (tenant-scoped por design).

    Filter explícito de `despacho_id` en `listar_por_despacho` (ADR 0003 §4).
    """

    @abstractmethod
    async def agregar(self, membresia: MembresiaDespacho) -> MembresiaDespacho:
        raise NotImplementedError

    @abstractmethod
    async def buscar(
        self,
        *,
        usuario_id: UUID,
        despacho_id: UUID,
    ) -> MembresiaDespacho | None:
        raise NotImplementedError

    @abstractmethod
    async def listar_por_despacho(self, despacho_id: UUID) -> list[MembresiaDespacho]:
        """Tenant-scoped: filtra por despacho_id."""
        raise NotImplementedError

    @abstractmethod
    async def listar_por_usuario(self, usuario_id: UUID) -> list[MembresiaDespacho]:
        """Cross-tenant desde la perspectiva del usuario."""
        raise NotImplementedError


class SeguimientoExpedienteRepository(ABC):
    """Puerto: persistencia de SeguimientoExpediente.

    Tenant-scoped por design. TODA query filtra explícito por `despacho_id`
    (ADR 0003 §4). Operaciones de write reciben `despacho_id` aunque también
    haya un `seguimiento_id` — esto previene leak cross-tenant si el id
    viene de un input no validado.
    """

    @abstractmethod
    async def crear(self, seguimiento: SeguimientoExpediente) -> SeguimientoExpediente:
        raise NotImplementedError

    @abstractmethod
    async def buscar(
        self,
        *,
        despacho_id: UUID,
        expediente_id: UUID,
    ) -> SeguimientoExpediente | None:
        """Devuelve el seguimiento del despacho sobre ese expediente, o None."""
        raise NotImplementedError

    @abstractmethod
    async def buscar_por_id(
        self,
        *,
        despacho_id: UUID,
        seguimiento_id: UUID,
    ) -> SeguimientoExpediente | None:
        """Lookup por UUID con filter explícito de despacho_id (defensivo)."""
        raise NotImplementedError

    @abstractmethod
    async def listar_por_despacho(
        self,
        despacho_id: UUID,
        *,
        incluir_archivados: bool = False,
    ) -> list[SeguimientoExpediente]:
        raise NotImplementedError

    @abstractmethod
    async def archivar(
        self,
        *,
        despacho_id: UUID,
        seguimiento_id: UUID,
    ) -> bool:
        """Marca archivado=True. Devuelve True si la fila existía y pertenecía
        al despacho; False si no afectó nada (no existe o es de otro tenant).
        """
        raise NotImplementedError

    @abstractmethod
    async def asignar_responsable(
        self,
        *,
        despacho_id: UUID,
        seguimiento_id: UUID,
        responsable_id: UUID | None,
    ) -> bool:
        """Asigna (o desasigna con None) un responsable. Returns True si afectó."""
        raise NotImplementedError


class LlmProvider(ABC):
    """Puerto: generación de contenido por LLM.

    Implementaciones esperadas:
    - `praxis.infrastructure.llm.fake.FakeLlmProvider` (default en dev, costo cero).
    - `praxis.infrastructure.llm.anthropic.AnthropicLlmProvider` (cuando hay key).

    Ver `docs/specs/13-resumen-ejecutivo-ia.md`.
    """

    @property
    @abstractmethod
    def nombre_modelo(self) -> str:
        """Identificador del modelo, ej. 'fake' o 'claude-sonnet-4-5-...'."""
        raise NotImplementedError

    @abstractmethod
    async def generar_resumen_ejecutivo(self, expediente: Expediente) -> str:
        """Devuelve markdown con 3 bullets:

            **Qué propone:** ...
            **Quién lo impulsa:** ...
            **Probabilidad de avance:** ...

        El provider decide cómo arma el prompt + cómo parsea la respuesta.
        El caller chequea cache antes de llamar — esto NO cachea solo.
        """
        raise NotImplementedError

    @abstractmethod
    async def clasificar_area_tematica(self, expediente: Expediente) -> AreaTematica:
        """Devuelve el área temática que mejor representa al expediente.

        Las 12 áreas son fijas (`AreaTematica`). Los proyectos transversales
        van a `AreaTematica.OTROS`.

        El caller chequea cache (ExpedienteAreaTematicaRepository) antes de
        llamar — esto NO cachea solo.
        """
        raise NotImplementedError

    @abstractmethod
    async def generar_argumentos(
        self,
        expediente: Expediente,
        *,
        contraargumentos: bool = False,
    ) -> list[str]:
        """Devuelve 2-3 bullets de texto plano (sin markdown).

        Si `contraargumentos=True`, los bullets son los que el bloque
        rival va a decir, no los del que defiende el proyecto.

        Pensado para alimentar las secciones de página 2 del briefing
        (un proyecto del despacho). El caller decide cuándo invocar — no
        cachea solo.
        """
        raise NotImplementedError


class ResumenEjecutivoRepository(ABC):
    """Puerto: persistencia de resúmenes ejecutivos (caché por expediente).

    UNIQUE en `expediente_id`: a lo sumo un resumen por expediente. Para
    regenerar, hay que borrar el viejo primero.
    """

    @abstractmethod
    async def buscar_por_expediente(self, expediente_id: UUID) -> ResumenEjecutivo | None:
        raise NotImplementedError

    @abstractmethod
    async def crear(self, resumen: ResumenEjecutivo) -> ResumenEjecutivo:
        raise NotImplementedError

    @abstractmethod
    async def eliminar(self, expediente_id: UUID) -> bool:
        """Borra el resumen del expediente. Devuelve True si había alguno."""
        raise NotImplementedError


class ExpedienteAreaTematicaRepository(ABC):
    """Puerto: persistencia del cache de clasificación temática.

    UNIQUE en `expediente_id`: a lo sumo una clasificación por expediente.
    Para reclasificar (cambio de prompt_version), borrar y recrear.
    """

    @abstractmethod
    async def buscar_por_expediente(
        self, expediente_id: UUID
    ) -> ExpedienteAreaTematica | None:
        raise NotImplementedError

    @abstractmethod
    async def crear(self, cache: ExpedienteAreaTematica) -> ExpedienteAreaTematica:
        raise NotImplementedError

    @abstractmethod
    async def eliminar(self, expediente_id: UUID) -> bool:
        """Borra la clasificación del expediente. True si había alguna."""
        raise NotImplementedError

    @abstractmethod
    async def listar_por_area(
        self, area: AreaTematica, *, limit: int = 100,
    ) -> list[ExpedienteAreaTematica]:
        """Útil para la página 3 del briefing (agrupar OD por área)."""
        raise NotImplementedError


class OrdenDelDiaRepository(ABC):
    """Puerto: persistencia del OrdenDelDia (lista de expedientes a tratar)."""

    @abstractmethod
    async def crear(self, od: OrdenDelDia) -> OrdenDelDia:
        raise NotImplementedError

    @abstractmethod
    async def buscar_por_id(self, od_id: UUID) -> OrdenDelDia | None:
        raise NotImplementedError

    @abstractmethod
    async def listar_por_despacho(
        self, despacho_id: UUID, *, limit: int = 20,
    ) -> list[OrdenDelDia]:
        raise NotImplementedError


class BriefingRepository(ABC):
    """Puerto: persistencia del Briefing (caché por despacho+OD).

    UNIQUE en (despacho_id, orden_del_dia_id): un briefing por par.
    Regenerar = delete + insert.
    """

    @abstractmethod
    async def buscar_por_despacho_y_od(
        self, *, despacho_id: UUID, orden_del_dia_id: UUID,
    ) -> Briefing | None:
        raise NotImplementedError

    @abstractmethod
    async def crear(self, briefing: Briefing) -> Briefing:
        raise NotImplementedError

    @abstractmethod
    async def eliminar(
        self, *, despacho_id: UUID, orden_del_dia_id: UUID,
    ) -> bool:
        raise NotImplementedError


class PerfilInteresDespachoRepository(ABC):
    """Puerto: persistencia del `PerfilInteresDespacho`.

    Una fila por despacho (PK = `despacho_id`). El upsert reemplaza la
    fila entera — no hay diff incremental. La distinción entre
    "sembrado automático" y "edición manual" se mantiene en los timestamps
    `sembrado_at` y `editado_at` que viajan en la entidad.

    Tenant-scoped por design: cualquier operación filtra por `despacho_id`.
    """

    @abstractmethod
    async def buscar_por_despacho(
        self, despacho_id: UUID,
    ) -> PerfilInteresDespacho | None:
        """Devuelve el perfil del despacho o None si no se sembró nunca."""
        raise NotImplementedError

    @abstractmethod
    async def upsert(
        self, perfil: PerfilInteresDespacho,
    ) -> PerfilInteresDespacho:
        """UPSERT por `despacho_id`.

        Reemplaza la fila entera. El caller setea `sembrado_at` cuando
        viene de re-sembrado automático, y `editado_at` cuando viene de
        edición manual desde la UI.

        Devuelve la entidad con `actualizado_en` poblado por el server.
        """
        raise NotImplementedError


class AuthProvider(ABC):
    """Puerto: verificación de tokens de un proveedor de identidad externo.

    Implementación esperada inicial:
    `praxis.infrastructure.auth.clerk.ClerkAuthProvider`.

    El método verifica firma + claims (iss, exp, aud opcional) y devuelve
    `AuthClaims` con los campos útiles. Si algo falla, lanza `AuthError`
    con un `AuthErrorCode` discreto para que el caller (FastAPI dep o caso
    de uso) lo mapee a un HTTP status code.

    Ver `docs/specs/09-auth-multitenancy.md`.
    """

    @abstractmethod
    async def verificar_token(self, token: str) -> AuthClaims:
        """Verifica el token y devuelve los claims.

        Raises:
            AuthError: con `code` ∈ {INVALID_TOKEN, TOKEN_EXPIRED, WRONG_ISSUER}.
        """
        raise NotImplementedError
