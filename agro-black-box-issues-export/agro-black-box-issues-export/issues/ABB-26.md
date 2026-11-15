# [ABB-26] Informe de caso completo y exportación verificable

<!-- AGRO-ISSUE-ID: ABB-26 -->
## Objetivo
Informe de caso completo y exportación verificable. Contribución a **Best Use of Data; Local Impact**. Trabajo de fase **F3**, prioridad **P0**.

**Responsable recomendado:** Persona B (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-10, ABB-14, ABB-16, ABB-17, ABB-25.
**Votación humana:** 3/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Ampliar Markdown existente con contexto, fuentes, periodos, métodos, hipótesis rivales, 3 rotaciones, claims/DOIs y limitaciones.
- [ ] Crear snapshot inmutable o versionado del informe y registrar hash de fuentes.
- [ ] Ofrecer descarga desde UI (Markdown y HTML, o PDF si el equipo aprueba la dependencia).
- [ ] Probar el informe con un caso que combine NASA real, evidencias revisadas y colaboración.

## Criterios de aceptación
- [ ] Descarga contiene resultados auténticos y los IDs/DOIs rastreables.
- [ ] Un informe regenerado identifica fecha, versión y cambios relevantes.
- [ ] Se evita filtrar coordenadas personales en exportaciones compartidas.

## Archivos o dominios afectados
- `backend/agroblackbox/services/report.py`
- `frontend/src/`
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

