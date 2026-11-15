# [ABB-25] Invitaciones, revisión y colaboración entre comunidades

<!-- AGRO-ISSUE-ID: ABB-25 -->
## Objetivo
Invitaciones, revisión y colaboración entre comunidades. Contribución a **Global Connection**. Trabajo de fase **F3**, prioridad **P0**.

**Responsable recomendado:** Persona C (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-05, ABB-06, ABB-14, ABB-20.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Permitir invitación revocable a personas identificadas, con permisos definidos.
- [ ] Registrar comentarios, revisión de hipótesis/claims, decisiones y marca de autoría.
- [ ] Ofrecer vista pública anonimizada/compartida solo con consentimiento.
- [ ] Prevenir XSS, acceso no autorizado y cambios de revisión sin auditoría.

## Criterios de aceptación
- [ ] Dos usuarios distintos colaboran en un caso sin exposición de información privada.
- [ ] Un invitado puede comentar y otro revisar o revocar permisos.
- [ ] El registro de revisiones conserva autor, instante y evidencia.

## Archivos o dominios afectados
- `backend/agroblackbox/`
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

