# [ABB-10] Construir línea temporal forense e hipótesis rivales

<!-- AGRO-ISSUE-ID: ABB-10 -->
## Objetivo
Construir línea temporal forense e hipótesis rivales. Contribución a **Best Use of Data; Local Impact**. Trabajo de fase **F1**, prioridad **P0**.

**Responsable recomendado:** Persona A (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-06, ABB-08.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Generar eventos observacionales con fecha, fuente, variable, severidad definida y confianza en el dato.
- [ ] Separar hechos observados de inferencias, hipótesis y ausencia de evidencia.
- [ ] Definir hipótesis alternativas y preguntas de verificación local; no calcular falsos porcentajes de causalidad.
- [ ] Publicar API de timeline e hipótesis para frontend.

## Criterios de aceptación
- [ ] Timeline contiene observaciones reales, procedencia y límites.
- [ ] Se puede marcar una hipótesis como compatible, contradicha o no evaluable.
- [ ] Ninguna inferencia se etiqueta automáticamente como causa demostrada.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `docs/science/`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

