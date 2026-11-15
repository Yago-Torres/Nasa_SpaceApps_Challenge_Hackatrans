# [ABB-27] Caché, tareas asíncronas y resiliencia ante APIs externas

<!-- AGRO-ISSUE-ID: ABB-27 -->
## Objetivo
Caché, tareas asíncronas y resiliencia ante APIs externas. Contribución a **Best Use of Data**. Trabajo de fase **F4**, prioridad **P1**.

**Responsable recomendado:** Persona A (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-03, ABB-07, ABB-13.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Definir tareas con identificador, estado, timeout, reintento, cancelación y deduplicación.
- [ ] Integrar Redis/worker si se justifica mediante ADR y límites claros; evitar bloquear peticiones largas.
- [ ] Registrar cuota de upstream y política de caché por recurso y fecha.
- [ ] Probar caída de POWER/OpenAlex, reintentos limitados y recuperación.

## Criterios de aceptación
- [ ] Solicitudes repetidas no disparan descargas innecesarias.
- [ ] Un upstream caído produce error recuperable y nunca dato ficticio.
- [ ] Tareas largas reportan progreso/estado y pueden retomarse.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `compose.yaml`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

