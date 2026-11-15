# [ABB-30] Despliegue seguro, monitorización y recuperación

<!-- AGRO-ISSUE-ID: ABB-30 -->
## Objetivo
Despliegue seguro, monitorización y recuperación. Contribución a **Galactic Impact; transversal**. Trabajo de fase **F4**, prioridad **P1**.

**Responsable recomendado:** Persona A (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-01, ABB-03, ABB-05, ABB-27, ABB-29.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Elegir plataforma y registrar costes, variables y controles de acceso.
- [ ] Configurar entornos de demo y release con migraciones, healthcheck, logs y seguimiento de errores.
- [ ] Definir backup/restauración de PostgreSQL y rollback de releases.
- [ ] Probar despliegue desde tag y recuperación ante una migración fallida simulada.

## Criterios de aceptación
- [ ] Hay URL de demo funcional accesible con el mínimo dato privado.
- [ ] El equipo puede repetir deploy, restaurar backup y revertir versión.
- [ ] Errores de fuentes externas son visibles en monitoreo sin exponer datos sensibles.

## Archivos o dominios afectados
- `.github/workflows/`
- `compose.yaml`
- `docs/operations/`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

