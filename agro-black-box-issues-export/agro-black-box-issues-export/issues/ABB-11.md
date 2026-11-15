# [ABB-11] Registrar suelos, cultivos y calendario local del agricultor

<!-- AGRO-ISSUE-ID: ABB-11 -->
## Objetivo
Registrar suelos, cultivos y calendario local del agricultor. Contribución a **Local Impact**. Trabajo de fase **F1**, prioridad **P0**.

**Responsable recomendado:** Persona B (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-02, ABB-06.
**Votación humana:** 2/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Permitir propiedades de suelo locales, unidades, profundidad y fuente de medida.
- [ ] Modelar cultivos, sistema de secano/regadío, fechas, restricciones de equipos y mercados.
- [ ] Usar catálogo inicial revisado con origen científico, no inventar parámetros.
- [ ] Definir advertencias por dato ausente y validaciones agronómicas.

## Criterios de aceptación
- [ ] Se puede distinguir medición local de estimación regional.
- [ ] El usuario puede registrar historial de cultivos, suelo y restricciones.
- [ ] Datos no disponibles provocan resultados limitados, no certezas simuladas.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `docs/science/`
- `frontend/src/`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

