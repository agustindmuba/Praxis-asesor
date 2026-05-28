"""Seed inicial para smoke testing y desarrollo local.

Crea (de forma idempotente):
- 1 Despacho de prueba.
- 1 Usuario con `auth_provider_id` configurable.
- 1 MembresiaDespacho (JEFE_ASESORES) entre ambos.

Uso:
    uv run python -m scripts.seed_inicial \
        --email "ana@example.com" \
        --nombre "Ana Perez" \
        --clerk-id "user_test_001" \
        --despacho-nombre "Despacho Demo"

Idempotente: si el usuario o despacho ya existen (por email/clerk_id/nombre),
los reusa en lugar de duplicar. La membresía solo se crea si no existe.

Imprime los UUIDs al terminar para usarlos en headers de prueba:

    Despacho ID:  abc-...
    Usuario ID:   def-...

Estos UUIDs van en el header `X-Despacho-Id` cuando hagas curl.
"""

from __future__ import annotations

import argparse
import asyncio
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from praxis.config import get_settings
from praxis.domain import Despacho, MembresiaDespacho, Rol, Usuario
from praxis.infrastructure.persistence.repositories import (
    SqlAlchemyDespachoRepository,
    SqlAlchemyMembresiaDespachoRepository,
    SqlAlchemyUsuarioRepository,
)


async def _seed(
    session: AsyncSession,
    *,
    email: str,
    nombre: str,
    clerk_id: str | None,
    despacho_nombre: str,
    rol: Rol,
) -> tuple[Despacho, Usuario]:
    despachos = SqlAlchemyDespachoRepository(session)
    usuarios = SqlAlchemyUsuarioRepository(session)
    membresias = SqlAlchemyMembresiaDespachoRepository(session)

    # --- Despacho ---
    # No tenemos buscar_por_nombre en el repo (es seed, lo aceptamos como
    # idempotente solo si el nombre es exacto y único — bueno para dev).
    existentes = await despachos.listar()
    despacho = next((d for d in existentes if d.nombre == despacho_nombre), None)
    if despacho is None:
        despacho = await despachos.crear(Despacho(id=uuid4(), nombre=despacho_nombre))
        print(f"  + Despacho creado: {despacho.id}  '{despacho.nombre}'")
    else:
        print(f"  ✓ Despacho existente: {despacho.id}  '{despacho.nombre}'")

    # --- Usuario ---
    usuario = await usuarios.buscar_por_email(email)
    if usuario is None and clerk_id:
        usuario = await usuarios.buscar_por_auth_provider_id(clerk_id)
    if usuario is None:
        usuario = await usuarios.crear(
            Usuario(
                id=uuid4(),
                email=email,
                nombre=nombre,
                auth_provider_id=clerk_id,
                activo=True,
            )
        )
        print(f"  + Usuario creado: {usuario.id}  '{usuario.email}'")
    else:
        # Si el usuario existe pero el clerk_id viene distinto, actualizamos.
        if clerk_id and usuario.auth_provider_id != clerk_id:
            await usuarios.actualizar(
                Usuario(
                    id=usuario.id,
                    email=usuario.email,
                    nombre=usuario.nombre,
                    auth_provider_id=clerk_id,
                    activo=usuario.activo,
                )
            )
            print(f"  ~ Usuario {usuario.id}: clerk_id actualizado a {clerk_id!r}")
        else:
            print(f"  ✓ Usuario existente: {usuario.id}  '{usuario.email}'")

    # --- Membresia ---
    membresia = await membresias.buscar(usuario_id=usuario.id, despacho_id=despacho.id)
    if membresia is None:
        await membresias.agregar(
            MembresiaDespacho(
                usuario_id=usuario.id,
                despacho_id=despacho.id,
                rol=rol,
                activo=True,
            )
        )
        print(f"  + Membresía creada: {usuario.email} → {despacho.nombre}  ({rol.value})")
    else:
        print(
            f"  ✓ Membresía existente: {usuario.email} → {despacho.nombre}  ({membresia.rol.value})"
        )

    return despacho, usuario


async def main(args: argparse.Namespace) -> None:
    settings = get_settings()
    engine = create_async_engine(str(settings.database_url), echo=False)
    sm = async_sessionmaker(engine, expire_on_commit=False)

    print(f"[seed] Conectando a {settings.database_url}")
    print(f"[seed] Despacho: {args.despacho_nombre!r}")
    print(f"[seed] Usuario:  {args.email!r}  ({args.nombre!r})")
    print(f"[seed] Clerk ID: {args.clerk_id!r}")
    print(f"[seed] Rol:      {args.rol}")
    print()

    try:
        async with sm() as session:
            despacho, usuario = await _seed(
                session,
                email=args.email,
                nombre=args.nombre,
                clerk_id=args.clerk_id,
                despacho_nombre=args.despacho_nombre,
                rol=Rol(args.rol),
            )
            await session.commit()
    finally:
        await engine.dispose()

    print()
    print("=" * 60)
    print(f"  Despacho ID:  {despacho.id}")
    print(f"  Usuario ID:   {usuario.id}")
    print(f"  Email:        {usuario.email}")
    print(f"  Clerk ID:     {usuario.auth_provider_id}")
    print("=" * 60)
    print()
    print("Para probar la API, agregá estos headers a tu curl/httpie:")
    print(f"  Authorization: Bearer <jwt-real-de-clerk-con-sub={usuario.auth_provider_id}>")
    print(f"  X-Despacho-Id: {despacho.id}")
    print()
    print("Para tests sin JWT real, podés overridear el AuthProvider con un fake.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Seed inicial de Praxis Asesor")
    parser.add_argument("--email", required=True, help="Email del usuario seed")
    parser.add_argument("--nombre", required=True, help="Nombre del usuario seed")
    parser.add_argument(
        "--clerk-id",
        default=None,
        help="auth_provider_id (Clerk user_id). Opcional si todavía no usás Clerk.",
    )
    parser.add_argument(
        "--despacho-nombre", default="Despacho Demo", help="Nombre del despacho seed"
    )
    parser.add_argument(
        "--rol",
        default=Rol.JEFE_ASESORES.value,
        choices=[r.value for r in Rol],
        help="Rol de la membresía (default: jefe_asesores)",
    )
    return parser


if __name__ == "__main__":
    asyncio.run(main(_build_parser().parse_args()))
