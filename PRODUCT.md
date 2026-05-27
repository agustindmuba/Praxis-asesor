# PRODUCT.md — Praxis Asesor

## Visión

Praxis Asesor es el sistema operativo del despacho parlamentario moderno: convierte el caos informativo y la dispersión de tareas de un despacho legislativo en un flujo de trabajo claro, trazable y proactivo, liberando al asesor para hacer lo que solo un humano puede hacer — pensar política.

## Propuesta de valor

Para **jefes de asesores y despachos legislativos del Congreso Nacional Argentino**, que hoy navegan portales oficiales lentos, planillas dispersas y chats inconexos, **Praxis Asesor es una plataforma integral de seguimiento parlamentario** que centraliza expedientes, automatiza alertas, coordina al equipo y, en versiones sucesivas, asiste activamente en el análisis y la redacción.

A diferencia de los sistemas oficiales (que son consultivos pero no operativos) y de las planillas internas (que no escalan ni se actualizan solas), Praxis ofrece **datos siempre frescos + colaboración del equipo + inteligencia aplicada al ciclo legislativo**.

## Usuarios y casos de uso

### Usuario primario: Jefe/a de Asesores

**Contexto**: coordina entre 2 y 6 asesores junior. Reporta al/la legislador/a. Necesita visión transversal: qué está siguiendo cada miembro del equipo, qué expedientes son críticos esta semana, qué viene en el OD, qué requiere intervención del/la legislador/a.

**Casos de uso del MVP**:
- "¿Qué expedientes tocan a mi despacho esta semana?"
- "¿Quién de mi equipo está siguiendo el proyecto X?"
- "Avísenme cuando el expediente Y obtenga dictamen."
- "Mostrame todos los expedientes sobre [tema] presentados este año en ambas cámaras."
- "¿Qué proyectos firmados por mi legislador/a están próximos a perder estado parlamentario?"

### Usuario secundario: Asesor/a Junior

**Contexto**: responsable de un área temática (ej. educación, ambiente, seguridad). Sigue los expedientes asignados, prepara informes, redacta borradores.

**Casos de uso del MVP**:
- "Ver mis expedientes asignados."
- "Tomar notas internas sobre un expediente."
- "Recibir alertas cuando 'mis' expedientes cambian de estado."
- "Consultar el historial completo de trámite de un expediente."

### Usuario terciario: Legislador/a (rol lector)

**Contexto**: consulta puntual antes de una sesión o reunión. No usa el sistema operativamente.

**Casos de uso del MVP**:
- "Dame el estado de los proyectos que firmé."
- "¿Qué hay en el OD de hoy que me toque?"

## Alcance del MVP

### Features en orden de implementación

**Bloque 1 — Fundamentos de datos** (ciclos 1-2)

1. Ingesta automatizada de expedientes de HCDN.
2. Ingesta automatizada de expedientes de HSN.
3. Normalización de modelo común (camara-agnóstico).
4. Histórico de trámites por expediente.
5. Catálogo de legisladores y bloques actuales.
6. Catálogo de comisiones por cámara.

**Bloque 2 — Aplicación core** (ciclos 3-4)

7. Autenticación y multi-tenancy por despacho.
8. Roles: jefe de asesores, asesor, lector.
9. Búsqueda y filtrado de expedientes (full-text + filtros estructurados).
10. Ficha de expediente (vista detalle).
11. Seguimiento personalizado: "marcar" expedientes del despacho.
12. Asignación de expedientes a miembros del equipo.

**Bloque 3 — Alertas y coordinación** (ciclos 5-6)

13. Sistema de alertas configurable (por expediente, por tema, por autor).
14. Notificaciones por email (in-app inicialmente).
15. Notas internas por expediente (privadas del despacho).
16. Tablero del despacho: vista consolidada.
17. Calendario de plazos críticos (caducidad, sesiones próximas).

**Bloque 4 — Pulido y onboarding** (ciclo 7)

18. Onboarding guiado para nuevos despachos.
19. Documentación de usuario.
20. Pilotos con 2-3 despachos amigos.

### Métricas de éxito del MVP

- **Adopción**: 3 despachos piloto en uso activo durante 4 semanas.
- **Engagement**: >5 sesiones/semana por usuario activo; >10 expedientes seguidos por despacho.
- **Confiabilidad**: <1% de discrepancia entre datos del sistema y portales oficiales (muestreo semanal); uptime >99%.
- **Valor percibido**: NPS >40 en encuesta de cierre de piloto; al menos 2 despachos dispuestos a pagar.

## Roadmap post-MVP (referencia, no compromiso)

**v2 — Inteligencia de legisladores**
- Fichas analíticas: historial de votación, coautorías, comisiones, estadísticas de productividad.
- Mapa de alianzas: con qué bloques/legisladores se cofirma más.
- Análisis de comportamiento parlamentario (alimentado por el Observatorio).

**v3 — Asistencia activa con IA**
- Asistente de redacción de proyectos, fundamentos, dictámenes.
- Briefings automáticos pre-sesión y pre-comisión.
- Resúmenes de versiones taquigráficas.
- Sugerencias de aliados para cofirmar (basado en patrones históricos).

**v4 — Ecosistema**
- Integración con calendario externo (Google/Outlook).
- App móvil.
- API pública para integraciones (CRM del distrito, prensa, etc.).
- Módulo de pedidos del distrito.

## Riesgos y supuestos

### Riesgos de producto

- **Resistencia al cambio cultural**: los despachos tienen rutinas establecidas (Excel, WhatsApp). Mitigación: onboarding muy guiado + valor inmediato en primera sesión.
- **Sensibilidad política sobre datos**: aunque los datos son públicos, la información de seguimiento del despacho es estratégica. Mitigación: cifrado, multi-tenancy estricto, auditoría.
- **Estacionalidad**: el Congreso tiene receso (verano, parte del invierno). Los pilotos deben coincidir con período de sesiones ordinarias (marzo-noviembre).

### Riesgos técnicos

- **Cambios en portales oficiales**: scrapers se rompen. Mitigación: tests de contrato, monitoreo, arquitectura modular.
- **Volumen de datos**: HCDN procesa ~6000 expedientes/año; HSN ~2000. No es masivo pero el historial es largo. Mitigación: ingesta incremental, archivado.

### Supuestos críticos

- Hay disposición a pagar por una herramienta así. **A validar en ciclo 0/1** con entrevistas a 5 jefes de asesores.
- Los portales oficiales seguirán siendo scrapeables. Si publicaran API oficial, mejor; si bloquearan scraping, problema serio.
- Agustín consigue al menos 2-3 despachos amigos dispuestos a pilotear sin pagar.

## Pricing (hipótesis preliminar, a validar)

- **Por despacho/mes**, escalando con tamaño de equipo.
- Despacho chico (hasta 3 usuarios): USD 80-120/mes equivalente en ARS.
- Despacho mediano (4-8 usuarios): USD 200-300/mes.
- Bloque (>8 usuarios, multi-despacho): cotización.
- Período de prueba: 60 días gratuitos para pilotos.

## Decisiones tomadas (ciclo 0)

- ✅ Dolor #1 del MVP: seguimiento de expedientes + alertas de trámite.
- ✅ Cámara objetivo: ambas (HCDN + HSN) desde el inicio.
- ✅ Usuario objetivo: jefe de asesores / despacho completo.
- ✅ Despliegue: agnóstico (arquitectura hexagonal).

## Decisiones pendientes (próximos ciclos)

- ⏳ Stack técnico definitivo (confirmar en ciclo 1).
- ⏳ Modelo legal/comercial (SaaS argentino, SRL, monotributo escalable, etc.).
- ⏳ Marca: nombre comercial definitivo, dominio, identidad visual.
- ⏳ Política de retención de datos.
- ⏳ Plan de incorporación de dev senior (¿cuándo? ¿part-time? ¿equity?).
