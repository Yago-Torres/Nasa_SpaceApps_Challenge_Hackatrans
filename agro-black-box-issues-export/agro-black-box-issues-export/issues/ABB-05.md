# [ABB-05] Diseñar y aplicar permisos y autenticación segura

<!-- AGRO-ISSUE-ID: ABB-05 -->
## Objetivo
Diseñar y aplicar permisos y autenticación segura. Contribución a **Global Connection; Local Impact**. Trabajo de fase **F0**, prioridad **P0**.

**Responsable recomendado:** Persona C (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-02, ABB-03.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Seleccionar implementación de sesiones/autenticación y registrar ADR aprobado.
- [ ] Crear roles owner, editor, reviewer; casos privados por defecto y acceso por invitación.
- [ ] Incluir consentimiento para compartir y posibilidad de revocarlo.
- [ ] Escribir pruebas de autorización negativas, expiración y acceso entre usuarios.

## Criterios de aceptación
- [ ] Usuarios sin permiso no acceden a casos, fuentes ni coordenadas.
- [ ] Rol reviewer solo modifica contenido autorizado.
- [ ] Revocar invitación bloquea inmediatamente el acceso.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `frontend/src/`
- `docs/architecture/ADRs/`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

