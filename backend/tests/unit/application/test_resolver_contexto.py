"""Tests unit de ResolverContextoRequest.

Usamos fakes en memoria de los 4 puertos (AuthProvider + 3 repos) para
recorrer las 5 ramas de error + caso happy del caso de uso.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from praxis.application.ports import (
    AuthProvider,
    DespachoRepository,
    MembresiaDespachoRepository,
    UsuarioRepository,
)
from praxis.application.use_cases import ResolverContextoRequest
from praxis.domain import (
    AuthClaims,
    AuthError,
    AuthErrorCode,
    Despacho,
    MembresiaDespacho,
    Rol,
    Usuario,
)

pytestmark = pytest.mark.unit


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeAuth(AuthProvider):
    def __init__(self, claims: AuthClaims | None = None, error: AuthError | None = None) -> None:
        self._claims = claims
        self._error = error

    async def verificar_token(self, token: str) -> AuthClaims:
        del token  # no usado en el fake.
        if self._error is not None:
            raise self._error
        assert self._claims is not None
        return self._claims


class FakeUsuarios(UsuarioRepository):
    def __init__(self, usuarios: list[Usuario]) -> None:
        self._usuarios = usuarios

    async def buscar_por_auth_provider_id(self, auth_provider_id: str) -> Usuario | None:
        for u in self._usuarios:
            if u.auth_provider_id == auth_provider_id:
                return u
        return None

    # Métodos no usados por el caso de uso pero requeridos por la ABC.
    async def crear(self, usuario: Usuario) -> Usuario:
        raise NotImplementedError

    async def buscar_por_id(self, usuario_id: UUID) -> Usuario | None:
        raise NotImplementedError

    async def buscar_por_email(self, email: str) -> Usuario | None:
        raise NotImplementedError

    async def listar(self) -> list[Usuario]:
        raise NotImplementedError


class FakeDespachos(DespachoRepository):
    def __init__(self, despachos: list[Despacho]) -> None:
        self._despachos = despachos

    async def buscar_por_id(self, despacho_id: UUID) -> Despacho | None:
        for d in self._despachos:
            if d.id == despacho_id:
                return d
        return None

    async def crear(self, despacho: Despacho) -> Despacho:
        raise NotImplementedError

    async def listar(self) -> list[Despacho]:
        raise NotImplementedError


class FakeMembresias(MembresiaDespachoRepository):
    def __init__(self, membresias: list[MembresiaDespacho]) -> None:
        self._membresias = membresias

    async def buscar(self, *, usuario_id: UUID, despacho_id: UUID) -> MembresiaDespacho | None:
        for m in self._membresias:
            if m.usuario_id == usuario_id and m.despacho_id == despacho_id:
                return m
        return None

    async def agregar(self, membresia: MembresiaDespacho) -> MembresiaDespacho:
        raise NotImplementedError

    async def listar_por_despacho(self, despacho_id: UUID) -> list[MembresiaDespacho]:
        raise NotImplementedError

    async def listar_por_usuario(self, usuario_id: UUID) -> list[MembresiaDespacho]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_usuario(*, auth_provider_id: str = "clerk_user_1", activo: bool = True) -> Usuario:
    return Usuario(
        id=uuid4(),
        email="a@b.com",
        nombre="Ana",
        auth_provider_id=auth_provider_id,
        activo=activo,
    )


def _make_despacho() -> Despacho:
    return Despacho(id=uuid4(), nombre="Despacho X")


def _make_membresia(
    *, usuario: Usuario, despacho: Despacho, activo: bool = True
) -> MembresiaDespacho:
    return MembresiaDespacho(
        usuario_id=usuario.id,
        despacho_id=despacho.id,
        rol=Rol.ASESOR,
        activo=activo,
    )


def _make_resolver(
    *,
    auth: AuthProvider,
    usuarios: list[Usuario],
    despachos: list[Despacho],
    membresias: list[MembresiaDespacho],
) -> ResolverContextoRequest:
    return ResolverContextoRequest(
        auth=auth,
        usuarios=FakeUsuarios(usuarios),
        despachos=FakeDespachos(despachos),
        membresias=FakeMembresias(membresias),
    )


# ---------------------------------------------------------------------------
# Caso happy
# ---------------------------------------------------------------------------


async def test_resuelve_contexto_completo_si_todo_existe() -> None:
    usuario = _make_usuario()
    despacho = _make_despacho()
    membresia = _make_membresia(usuario=usuario, despacho=despacho)

    resolver = _make_resolver(
        auth=FakeAuth(AuthClaims(sub="clerk_user_1", email="a@b.com")),
        usuarios=[usuario],
        despachos=[despacho],
        membresias=[membresia],
    )
    ctx = await resolver.execute(token="t", despacho_id=despacho.id)
    assert ctx.usuario.id == usuario.id
    assert ctx.despacho.id == despacho.id
    assert ctx.rol == Rol.ASESOR


# ---------------------------------------------------------------------------
# Ramas de error
# ---------------------------------------------------------------------------


async def test_propaga_invalid_token_del_auth_provider() -> None:
    resolver = _make_resolver(
        auth=FakeAuth(error=AuthError(AuthErrorCode.INVALID_TOKEN, "bad sig")),
        usuarios=[],
        despachos=[],
        membresias=[],
    )
    with pytest.raises(AuthError) as exc_info:
        await resolver.execute(token="x", despacho_id=uuid4())
    assert exc_info.value.code == AuthErrorCode.INVALID_TOKEN


async def test_propaga_token_expired_del_auth_provider() -> None:
    resolver = _make_resolver(
        auth=FakeAuth(error=AuthError(AuthErrorCode.TOKEN_EXPIRED)),
        usuarios=[],
        despachos=[],
        membresias=[],
    )
    with pytest.raises(AuthError) as exc_info:
        await resolver.execute(token="x", despacho_id=uuid4())
    assert exc_info.value.code == AuthErrorCode.TOKEN_EXPIRED


async def test_user_not_provisioned_si_no_existe_en_db() -> None:
    despacho = _make_despacho()
    resolver = _make_resolver(
        auth=FakeAuth(AuthClaims(sub="clerk_user_FANTASMA")),
        usuarios=[],  # no hay nadie con ese auth_provider_id
        despachos=[despacho],
        membresias=[],
    )
    with pytest.raises(AuthError) as exc_info:
        await resolver.execute(token="t", despacho_id=despacho.id)
    assert exc_info.value.code == AuthErrorCode.USER_NOT_PROVISIONED


async def test_user_not_provisioned_si_usuario_inactivo() -> None:
    """Un usuario marcado activo=False no puede entrar, aunque exista."""
    usuario = _make_usuario(activo=False)
    despacho = _make_despacho()
    membresia = _make_membresia(usuario=usuario, despacho=despacho)
    resolver = _make_resolver(
        auth=FakeAuth(AuthClaims(sub="clerk_user_1")),
        usuarios=[usuario],
        despachos=[despacho],
        membresias=[membresia],
    )
    with pytest.raises(AuthError) as exc_info:
        await resolver.execute(token="t", despacho_id=despacho.id)
    assert exc_info.value.code == AuthErrorCode.USER_NOT_PROVISIONED


async def test_not_a_member_si_despacho_no_existe() -> None:
    """Si el despacho_id no existe, devolvemos NOT_A_MEMBER (no DESPACHO_NOT_FOUND)
    para no leakear info."""
    usuario = _make_usuario()
    resolver = _make_resolver(
        auth=FakeAuth(AuthClaims(sub="clerk_user_1")),
        usuarios=[usuario],
        despachos=[],
        membresias=[],
    )
    with pytest.raises(AuthError) as exc_info:
        await resolver.execute(token="t", despacho_id=uuid4())
    assert exc_info.value.code == AuthErrorCode.NOT_A_MEMBER


async def test_not_a_member_si_no_hay_membresia() -> None:
    """Usuario válido, despacho válido, pero sin membresía entre ambos."""
    usuario = _make_usuario()
    despacho = _make_despacho()
    resolver = _make_resolver(
        auth=FakeAuth(AuthClaims(sub="clerk_user_1")),
        usuarios=[usuario],
        despachos=[despacho],
        membresias=[],
    )
    with pytest.raises(AuthError) as exc_info:
        await resolver.execute(token="t", despacho_id=despacho.id)
    assert exc_info.value.code == AuthErrorCode.NOT_A_MEMBER


async def test_not_a_member_si_membresia_inactiva() -> None:
    """Membresía existe pero está marcada activo=False (ej. el asesor fue baja)."""
    usuario = _make_usuario()
    despacho = _make_despacho()
    membresia = _make_membresia(usuario=usuario, despacho=despacho, activo=False)
    resolver = _make_resolver(
        auth=FakeAuth(AuthClaims(sub="clerk_user_1")),
        usuarios=[usuario],
        despachos=[despacho],
        membresias=[membresia],
    )
    with pytest.raises(AuthError) as exc_info:
        await resolver.execute(token="t", despacho_id=despacho.id)
    assert exc_info.value.code == AuthErrorCode.NOT_A_MEMBER
