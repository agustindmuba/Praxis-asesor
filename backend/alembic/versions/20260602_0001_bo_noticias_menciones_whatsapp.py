"""create BO + Noticias + Menciones + WhatsApp tables

Revision ID: 20260602_0001
Revises: 20260601_0002
Create Date: 2026-06-02

Migración conjunta de feat-39.2.B. Crea las 16 tablas del ADR 0006 +
sus índices. Tablas agrupadas por dominio:

- Compartido: perfil_interes_despacho.
- Boletín Oficial (spec 15): norma_bo, norma_bo_texto,
  clasificacion_norma_bo, norma_bo_accionable.
- Noticias + Menciones (spec 16): fuente_noticia, fuente_noticia_despacho,
  articulo, articulo_hash, clasificacion_articulo, articulo_relevante,
  mencion.
- WhatsApp (spec 17): destinatario, plantilla_whatsapp, envio_whatsapp,
  alerta_mencion_enviada.

Aditiva pura: no toca tablas existentes. Reversible.

Ver ADR 0006 §"Esquema SQL".
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20260602_0001"
down_revision: str | None = "20260601_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # ---------------------------------------------------------------
    # Compartido — PerfilInteresDespacho
    # ---------------------------------------------------------------
    op.create_table(
        "perfil_interes_despacho",
        sa.Column("despacho_id", sa.Uuid(), primary_key=True),
        sa.Column("areas_tematicas", sa.JSON(), nullable=False),
        sa.Column("comisiones_legislador", sa.JSON(), nullable=False),
        sa.Column("distritos_observados", sa.JSON(), nullable=False),
        sa.Column("aliases_legislador", sa.JSON(), nullable=False),
        sa.Column(
            "sembrado_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "editado_at", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["despacho_id"], ["despacho.id"], ondelete="CASCADE",
        ),
    )

    # ---------------------------------------------------------------
    # Boletín Oficial
    # ---------------------------------------------------------------
    op.create_table(
        "norma_bo",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fecha_publicacion", sa.Date(), nullable=False),
        sa.Column("seccion", sa.String(length=30), nullable=False),
        sa.Column("tipo_norma", sa.String(length=80), nullable=False),
        sa.Column("numero_norma", sa.String(length=80), nullable=False),
        sa.Column("organismo_emisor", sa.String(length=400), nullable=False),
        sa.Column("sumario", sa.Text(), nullable=False),
        sa.Column("url_oficial", sa.String(length=1000), nullable=False),
        sa.Column("hash_sumario", sa.String(length=64), nullable=False),
        sa.Column(
            "capturado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "uq_norma_bo_identidad_natural",
        "norma_bo",
        ["fecha_publicacion", "seccion", "tipo_norma", "numero_norma"],
        unique=True,
    )
    op.create_index(
        "ix_norma_bo_fecha_seccion",
        "norma_bo",
        ["fecha_publicacion", "seccion"],
    )
    op.create_index(
        "ix_norma_bo_hash_sumario",
        "norma_bo",
        ["hash_sumario"],
        unique=True,
    )

    op.create_table(
        "norma_bo_texto",
        sa.Column("norma_id", sa.Uuid(), primary_key=True),
        sa.Column("texto", sa.Text(), nullable=False),
        sa.Column(
            "capturado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["norma_id"], ["norma_bo.id"], ondelete="CASCADE",
        ),
    )

    op.create_table(
        "clasificacion_norma_bo",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("norma_id", sa.Uuid(), nullable=False),
        sa.Column("area_tematica", sa.String(length=40), nullable=False),
        sa.Column("palabras_clave", sa.JSON(), nullable=False),
        sa.Column(
            "afecta_expedientes_hcdn",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("referencias_legales", sa.JSON(), nullable=False),
        sa.Column("modelo", sa.String(length=80), nullable=False),
        sa.Column(
            "prompt_version",
            sa.String(length=20),
            nullable=False,
            server_default="v1",
        ),
        sa.Column(
            "generado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["norma_id"], ["norma_bo.id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint("norma_id", name="uq_clasif_norma_bo_norma_id"),
    )
    op.create_index(
        "ix_clasif_norma_bo_norma_id",
        "clasificacion_norma_bo",
        ["norma_id"],
    )
    op.create_index(
        "ix_clasif_norma_bo_area",
        "clasificacion_norma_bo",
        ["area_tematica"],
    )

    op.create_table(
        "norma_bo_accionable",
        sa.Column("norma_id", sa.Uuid(), primary_key=True),
        sa.Column("despacho_id", sa.Uuid(), primary_key=True),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("prioridad", sa.String(length=10), nullable=False),
        sa.Column("razon", sa.String(length=200), nullable=False),
        sa.Column("expedientes_tocados", sa.JSON(), nullable=False),
        sa.Column(
            "generado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["norma_id"], ["norma_bo.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["despacho_id"], ["despacho.id"], ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_accionable_despacho_fecha",
        "norma_bo_accionable",
        ["despacho_id"],
    )

    # ---------------------------------------------------------------
    # Noticias + Menciones
    # ---------------------------------------------------------------
    op.create_table(
        "fuente_noticia",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("dominio", sa.String(length=255), nullable=False, unique=True),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("alcance", sa.String(length=20), nullable=False),
        sa.Column("modo_acceso", sa.String(length=20), nullable=False),
        sa.Column("feed_url", sa.String(length=1000), nullable=True),
        sa.Column("distrito", sa.String(length=100), nullable=True),
        sa.Column(
            "robots_ok", sa.Boolean(), nullable=False, server_default=sa.true(),
        ),
        sa.Column(
            "ultima_revision", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "activa", sa.Boolean(), nullable=False, server_default=sa.true(),
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_fuente_noticia_dominio", "fuente_noticia", ["dominio"])

    op.create_table(
        "fuente_noticia_despacho",
        sa.Column("fuente_id", sa.Uuid(), primary_key=True),
        sa.Column("despacho_id", sa.Uuid(), primary_key=True),
        sa.Column(
            "agregada_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["fuente_id"], ["fuente_noticia.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["despacho_id"], ["despacho.id"], ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_fuente_noticia_despacho_despacho_id",
        "fuente_noticia_despacho",
        ["despacho_id"],
    )

    op.create_table(
        "articulo",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("fuente_id", sa.Uuid(), nullable=False),
        sa.Column("url", sa.String(length=2000), nullable=False),
        sa.Column("titulo", sa.String(length=1000), nullable=False),
        sa.Column("bajada_propia", sa.String(length=400), nullable=True),
        sa.Column(
            "publicado_en", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "capturado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("hash_dedup", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(
            ["fuente_id"], ["fuente_noticia.id"], ondelete="CASCADE",
        ),
    )
    op.create_index("uq_articulo_hash", "articulo", ["hash_dedup"], unique=True)
    op.create_index(
        "ix_articulo_fuente_capturado",
        "articulo",
        ["fuente_id", "capturado_en"],
    )

    op.create_table(
        "articulo_hash",
        sa.Column("hash_dedup", sa.String(length=64), primary_key=True),
        sa.Column(
            "visto_por_primera_vez",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "clasificacion_articulo",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("articulo_id", sa.Uuid(), nullable=False),
        sa.Column("area_tematica", sa.String(length=40), nullable=False),
        sa.Column("palabras_clave", sa.JSON(), nullable=False),
        sa.Column("modelo", sa.String(length=80), nullable=False),
        sa.Column(
            "prompt_version",
            sa.String(length=20),
            nullable=False,
            server_default="v1",
        ),
        sa.Column(
            "generado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["articulo_id"], ["articulo.id"], ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "articulo_id", name="uq_clasif_articulo_articulo_id",
        ),
    )
    op.create_index(
        "ix_clasif_articulo_articulo_id",
        "clasificacion_articulo",
        ["articulo_id"],
    )
    op.create_index(
        "ix_clasif_articulo_area",
        "clasificacion_articulo",
        ["area_tematica"],
    )

    op.create_table(
        "articulo_relevante",
        sa.Column("articulo_id", sa.Uuid(), primary_key=True),
        sa.Column("despacho_id", sa.Uuid(), primary_key=True),
        sa.Column("score", sa.SmallInteger(), nullable=False),
        sa.Column("razon", sa.String(length=200), nullable=False),
        sa.Column("expedientes_tocados", sa.JSON(), nullable=False),
        sa.Column(
            "generado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["articulo_id"], ["articulo.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["despacho_id"], ["despacho.id"], ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_articulo_relevante_despacho",
        "articulo_relevante",
        ["despacho_id"],
    )

    op.create_table(
        "mencion",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("articulo_id", sa.Uuid(), nullable=False),
        # legislador_id sin FK estricta v1 (catálogo en CSV vendored).
        sa.Column("legislador_id", sa.Uuid(), nullable=False),
        sa.Column("despacho_id", sa.Uuid(), nullable=False),
        sa.Column("snippet_contexto", sa.String(length=400), nullable=False),
        sa.Column("tono", sa.String(length=15), nullable=False),
        sa.Column("confianza_tono", sa.Float(), nullable=False),
        sa.Column("alcance_medio", sa.String(length=20), nullable=False),
        sa.Column(
            "detectado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "notificada", sa.Boolean(), nullable=False, server_default=sa.false(),
        ),
        sa.ForeignKeyConstraint(
            ["articulo_id"], ["articulo.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["despacho_id"], ["despacho.id"], ondelete="CASCADE",
        ),
    )
    op.create_index("ix_mencion_articulo_id", "mencion", ["articulo_id"])
    op.create_index(
        "ix_mencion_despacho_detectado",
        "mencion",
        ["despacho_id", "detectado_en"],
    )
    op.create_index(
        "ix_mencion_legislador_detectado",
        "mencion",
        ["legislador_id", "detectado_en"],
    )

    # ---------------------------------------------------------------
    # WhatsApp
    # ---------------------------------------------------------------
    op.create_table(
        "destinatario",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("despacho_id", sa.Uuid(), nullable=False),
        sa.Column("usuario_id", sa.Uuid(), nullable=True),
        sa.Column("nombre", sa.String(length=200), nullable=False),
        sa.Column("rol_interno", sa.String(length=40), nullable=False),
        sa.Column("telefono_e164", sa.String(length=20), nullable=False),
        sa.Column(
            "recibe_briefing_diario",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "recibe_alertas_menciones",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "recibe_alertas_otras",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "opt_in_en", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "opt_out_en", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "activo", sa.Boolean(), nullable=False, server_default=sa.false(),
        ),
        sa.Column(
            "creado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "actualizado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.ForeignKeyConstraint(
            ["despacho_id"], ["despacho.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["usuario_id"], ["usuario.id"], ondelete="SET NULL",
        ),
        sa.UniqueConstraint(
            "despacho_id", "telefono_e164",
            name="uq_destinatario_despacho_telefono",
        ),
    )
    op.create_index(
        "ix_destinatario_despacho_id", "destinatario", ["despacho_id"],
    )

    op.create_table(
        "plantilla_whatsapp",
        sa.Column("name", sa.String(length=100), primary_key=True),
        sa.Column(
            "idioma", sa.String(length=10), nullable=False, server_default="es_AR",
        ),
        sa.Column("categoria", sa.String(length=20), nullable=False),
        sa.Column("body_params", sa.JSON(), nullable=False),
        sa.Column(
            "estado_meta",
            sa.String(length=30),
            nullable=False,
            server_default="pendiente_aprobacion",
        ),
        sa.Column(
            "aprobada_en", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column("contenido_referencia", sa.Text(), nullable=False),
    )

    op.create_table(
        "envio_whatsapp",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("destinatario_id", sa.Uuid(), nullable=False),
        # Desnormalizado por ADR 0006 para queries auditables por despacho.
        sa.Column("despacho_id", sa.Uuid(), nullable=False),
        sa.Column("plantilla_name", sa.String(length=100), nullable=False),
        sa.Column("tipo", sa.String(length=40), nullable=False),
        sa.Column("payload_params", sa.JSON(), nullable=False),
        sa.Column("correlativo_id", sa.Uuid(), nullable=True),
        sa.Column(
            "enviado_en", sa.DateTime(timezone=True), nullable=True,
        ),
        sa.Column(
            "estado",
            sa.String(length=30),
            nullable=False,
            server_default="pendiente",
        ),
        sa.Column("message_id_meta", sa.String(length=120), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["destinatario_id"], ["destinatario.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["despacho_id"], ["despacho.id"], ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["plantilla_name"], ["plantilla_whatsapp.name"], ondelete="RESTRICT",
        ),
    )
    op.create_index(
        "ix_envio_whatsapp_message_id_meta",
        "envio_whatsapp",
        ["message_id_meta"],
        unique=True,
    )
    op.create_index(
        "ix_envio_whatsapp_despacho_enviado",
        "envio_whatsapp",
        ["despacho_id", "enviado_en"],
    )

    op.create_table(
        "alerta_mencion_enviada",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("destinatario_id", sa.Uuid(), nullable=False),
        sa.Column("tipo", sa.String(length=20), nullable=False),
        sa.Column("menciones_ids", sa.JSON(), nullable=False),
        sa.Column("plantilla_meta", sa.String(length=100), nullable=False),
        sa.Column(
            "enviado_en",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("estado", sa.String(length=20), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(
            ["destinatario_id"], ["destinatario.id"], ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_alerta_mencion_enviada_destinatario_id",
        "alerta_mencion_enviada",
        ["destinatario_id"],
    )


def downgrade() -> None:
    # Orden inverso al upgrade. Las tablas con FK se borran antes que
    # sus padres.
    for tabla in (
        "alerta_mencion_enviada",
        "envio_whatsapp",
        "plantilla_whatsapp",
        "destinatario",
        "mencion",
        "articulo_relevante",
        "clasificacion_articulo",
        "articulo_hash",
        "articulo",
        "fuente_noticia_despacho",
        "fuente_noticia",
        "norma_bo_accionable",
        "clasificacion_norma_bo",
        "norma_bo_texto",
        "norma_bo",
        "perfil_interes_despacho",
    ):
        op.drop_table(tabla)
