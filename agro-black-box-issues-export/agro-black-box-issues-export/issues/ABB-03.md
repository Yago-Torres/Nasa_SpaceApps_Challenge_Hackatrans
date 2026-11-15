# [ABB-03] Modelo PostgreSQL, migraciones y repositorio de datos

<!-- AGRO-ISSUE-ID: ABB-03 -->
## Objetivo
Modelo PostgreSQL, migraciones y repositorio de datos. Contribución a **Local Impact; transversal**. Trabajo de fase **F0**, prioridad **P0**.

**Responsable recomendado:** Persona A (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-02.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Definir relaciones para usuarios, permisos, casos, parcelas, fuentes, observaciones, hipótesis, evidencias, rotaciones, revisiones e informes.
- [ ] Implementar SQLAlchemy + Alembic y migración inicial; no guardar coordenadas privadas en logs.
- [ ] Separar entidades, repositorios y lógica de negocio; añadir seeds explícitamente sintéticos.
- [ ] Probar creación, actualización, lectura, cambios concurrentes y rollback de migraciones.

## Criterios de aceptación
- [ ] Una base vacía se inicializa con migraciones reproducibles.
- [ ] Persisten casos y artefactos y se pueden leer tras reiniciar.
- [ ] Tests de integridad referencial y recuperación funcionan con PostgreSQL.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `compose.yaml`
- `backend/tests/`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

