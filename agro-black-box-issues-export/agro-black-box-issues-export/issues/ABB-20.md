# [ABB-20] Sistema de diseño, navegación, accesibilidad e idioma EN/ES

<!-- AGRO-ISSUE-ID: ABB-20 -->
## Objetivo
Sistema de diseño, navegación, accesibilidad e idioma EN/ES. Contribución a **Global Connection; Local Impact**. Trabajo de fase **F3**, prioridad **P0**.

**Responsable recomendado:** Persona C (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-02.
**Votación humana:** 2/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Definir layout, estados vacíos, skeleton, error, componente de fuentes y avisos de simulación.
- [ ] Crear rutas principales: Dashboard, Cases, Investigation, Evidence, Rotations, Collaboration, Report.
- [ ] Incorporar internacionalización EN/ES, responsive y navegación teclado.
- [ ] Probar build TS y accesibilidad de interacciones críticas.

## Criterios de aceptación
- [ ] Frontend navega entre pantallas con estados definidos.
- [ ] Los textos principales están disponibles en español e inglés.
- [ ] No hay errores TS y los flujos críticos son utilizables con teclado.

## Archivos o dominios afectados
- `frontend/src/`
- `frontend/package.json`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

