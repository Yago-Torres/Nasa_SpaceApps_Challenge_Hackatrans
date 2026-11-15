# [ABB-26] Informe de caso completo y exportación verificable

<!-- AGRO-ISSUE-ID: ABB-26 -->
## Objetivo
Informe de caso completo y exportación verificable. Contribución a **Best Use of Data; Local Impact**. Fase **F3**, prioridad **P0**.

**Responsable sugerido:** B (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-10, ABB-14, ABB-16, ABB-17, ABB-25. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Ampliar Markdown existente con contexto, fuentes, periodos, métodos, hipótesis rivales, 3 rotaciones, claims/DOIs y limitaciones.
- [ ] Crear snapshot inmutable o versionado del informe y registrar hash de fuentes.
- [ ] Ofrecer descarga desde UI en Markdown y HTML, y PDF si es viable técnicamente.
- [ ] Probar el informe con un caso que combine NASA real, evidencias revisadas y colaboración.

## Criterios de aceptación
- [ ] Descarga contiene resultados auténticos y los IDs/DOIs rastreables.
- [ ] Un informe regenerado identifica fecha, versión y cambios relevantes.
- [ ] Se evita filtrar coordenadas personales en exportaciones compartidas.

## Archivos o dominios afectados
- `backend/agroblackbox/services/report.py`
- `frontend/src/`
- `docs/science/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
