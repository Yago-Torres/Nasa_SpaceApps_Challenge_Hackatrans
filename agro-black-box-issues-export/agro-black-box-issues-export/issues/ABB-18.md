# [ABB-18] Análisis de escenarios, prioridades y sensibilidad

<!-- AGRO-ISSUE-ID: ABB-18 -->
## Objetivo
Análisis de escenarios, prioridades y sensibilidad. Contribución a **Galactic Impact; Local Impact**. Trabajo de fase **F2**, prioridad **P1**.

**Responsable recomendado:** Persona B (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-17.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Permitir modificar prioridades del agricultor, agua disponible y escenarios climáticos etiquetados.
- [ ] Comparar alternativas bajo episodios históricos comunes y escenarios hipotéticos diferenciados.
- [ ] Aplicar reglas de multicriterio transparentes y mostrar tradeoffs, sin prometer ahorros específicos.
- [ ] Probar estabilidad, ordenación y explicación de cambios.

## Criterios de aceptación
- [ ] La misma entrada obtiene la misma comparación reproducible.
- [ ] Al cambiar una prioridad se muestra qué criterio cambia y por qué.
- [ ] No se confunden simulación, observación y resultado validado de campo.

## Archivos o dominios afectados
- `backend/agroblackbox/`
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

