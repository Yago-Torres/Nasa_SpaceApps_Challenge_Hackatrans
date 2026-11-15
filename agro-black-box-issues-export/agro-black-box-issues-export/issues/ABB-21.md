# [ABB-21] Wizard de incidente y mapa geoespacial con privacidad

<!-- AGRO-ISSUE-ID: ABB-21 -->
## Objetivo
Wizard de incidente y mapa geoespacial con privacidad. Contribución a **Local Impact; Global Connection**. Trabajo de fase **F3**, prioridad **P0**.

**Responsable recomendado:** Persona C (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-05, ABB-06, ABB-20.
**Votación humana:** 2/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Crear formulario guiado de incidente y selección espacial, con precisión configurable.
- [ ] Mostrar datos introducidos y alertas de variables/campos faltantes.
- [ ] Integrar guardado/autosave y control de autorización.
- [ ] Ocultar coordenadas exactas al compartir externamente, salvo consentimiento explícito.

## Criterios de aceptación
- [ ] Un usuario crea un caso desde cero y vuelve a editarlo.
- [ ] Datos incorrectos reciben mensajes útiles, sin perder información.
- [ ] Un invitado no ve la ubicación exacta de la parcela privada.

## Archivos o dominios afectados
- `frontend/src/`
- `docs/product/UX_FLOWS.md`

## Contrato de entrega
- [ ] Cambios vinculados a esta Issue y revisados por otra persona cuando el equipo habilite su flujo Git.
- [ ] Tests/comprobaciones ejecutados y resultados registrados en la Issue o en la revisión (no inventados).
- [ ] Contratos y ADR actualizados si cambian; `CURRENT_STATE.md` solo tras validación.
- [ ] Handoff entre agentes según `docs/ai/HANDOFF_TEMPLATE.md`.

**Aprobaciones humanas (completar antes de programar):**
- [ ] Voto 1:
- [ ] Voto 2:
- [ ] Voto 3 (si se requieren 3/3):

