# [ABB-22] Visualización avanzada de timeline, anomalías y fuentes NASA

<!-- AGRO-ISSUE-ID: ABB-22 -->
## Objetivo
Visualización avanzada de timeline, anomalías y fuentes NASA. Contribución a **Best Use of Data**. Trabajo de fase **F3**, prioridad **P0**.

**Responsable recomendado:** Persona C (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-08, ABB-10, ABB-20.
**Votación humana:** 2/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Añadir gráfico de series y anomalías con selección temporal y capas disponibles.
- [ ] Mostrar unidad, periodo base, QA, procedencia y resolución por variable.
- [ ] Diferenciar NASA real, datos locales y escenarios simulados en leyenda permanente.
- [ ] Diseñar estados de carga, sin datos, error externo y datos parciales.

## Criterios de aceptación
- [ ] El usuario puede inspeccionar cada hallazgo hasta su origen.
- [ ] Los gráficos no interpolan silenciosamente huecos de datos.
- [ ] La UI representa errores NASA sin inventar valores.

## Archivos o dominios afectados
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

