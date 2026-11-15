# [ABB-04] Configurar gobierno del equipo, GitHub Project y protección de main

<!-- AGRO-ISSUE-ID: ABB-04 -->
## Objetivo
Configurar gobierno del equipo, GitHub Project y protección de main. Contribución a **Global Connection; transversal**. Trabajo de fase **F0**, prioridad **P0**.

**Responsable recomendado:** Persona C (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-01.
**Votación humana:** 2/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Activar Issues, configurar etiquetas, Project y columnas del flujo de aprobación.
- [ ] Invitar a los tres humanos y asociar sus logins a tareas; exigir PR y revisión de otra persona.
- [ ] Configurar CODEOWNERS para ciencia, backend, frontend y documentación.
- [ ] Añadir a las plantillas PR enlaces a Issue, pruebas, cambios en contratos y evidencia de votos.

## Criterios de aceptación
- [ ] Las Issues tienen propietario, estado y criterios verificables.
- [ ] Una PR sin revisión o con checks rojos no se fusiona en main.
- [ ] Las IA no pueden otorgar aprobación de funcionalidades en nombre de humanos.

## Archivos o dominios afectados
- `.github/`
- `docs/governance/`
- `docs/ai/`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

