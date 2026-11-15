# [ABB-02] Congelar contrato API y esquemas de datos v1

<!-- AGRO-ISSUE-ID: ABB-02 -->
## Objetivo
Congelar contrato API y esquemas de datos v1. Contribución a **Best Use of Data; transversal**. Fase **F0**, prioridad **P0**.

**Responsable sugerido:** A (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-01. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Inventariar rutas actuales y tipos de respuesta en FastAPI y React.
- [ ] Diseñar Pydantic: Case, Field, SourceManifest, Observation, Anomaly, Hypothesis, Paper, EvidenceClaim, Rotation, Review y Report.
- [ ] Definir errores, nulos, unidades, metadatos de resolución, privacidad y versionado API.
- [ ] Revisar con responsables B y C y registrar ADR y contrato actualizado.

## Criterios de aceptación
- [ ] OpenAPI refleja esquemas completos con ejemplos reales o claramente marcados como fixtures.
- [ ] Contrato pasa una prueba de validación JSON y otra de error 422/4xx.
- [ ] El contrato compartido se comunica a A, B y C y se documentan los cambios para permitir integración paralela.

## Archivos o dominios afectados
- `backend/agroblackbox/app.py`
- `docs/architecture/API_CONTRACTS.md`
- `docs/architecture/ADRs/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
