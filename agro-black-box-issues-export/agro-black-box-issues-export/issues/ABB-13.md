# [ABB-13] OpenAlex + Crossref: búsqueda y verificación bibliográfica

<!-- AGRO-ISSUE-ID: ABB-13 -->
## Objetivo
OpenAlex + Crossref: búsqueda y verificación bibliográfica. Contribución a **Best Use of Data; Galactic Impact**. Trabajo de fase **F2**, prioridad **P0**.

**Responsable recomendado:** Persona B (A = usuario/ChatGPT, B = Claude científico, C = Claude producto). Cualquier integrante puede implementarla si el equipo aprueba la asignación.

**Dependencias previas:** ABB-02.
**Votación humana:** 2/3; revisar `docs/governance/FEATURE_POLICY.md`. La creación de esta Issue **no implica aprobación**.

## Pasos de implementación
- [ ] Extender búsqueda existente y combinar metadatos mediante DOI con Crossref.
- [ ] Normalizar autores, título, año, DOI, licencia, fecha de consulta y URL.
- [ ] Separar coincidencia bibliográfica de evidencia confirmada en el texto.
- [ ] Probar errores de API, DOI faltante, duplicados y límites de uso.

## Criterios de aceptación
- [ ] Cada artículo tiene referencia verificable y procedencia.
- [ ] Un artículo sin DOI no se inventa.
- [ ] Búsqueda fallida no devuelve contenido científico fabricado.

## Archivos o dominios afectados
- `backend/agroblackbox/services/literature.py`
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

