# [ABB-14] Registro estructurado de claims científicos con revisión humana

<!-- AGRO-ISSUE-ID: ABB-14 -->
## Objetivo
Registro estructurado de claims científicos con revisión humana. Contribución a **Best Use of Data**. Fase **F2**, prioridad **P0**.

**Responsable sugerido:** B (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-03, ABB-13. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Crear entidad EvidenceClaim: afirmación, población/cultivos/suelos, diseño, resultado, incertidumbre, DOI, página/fragmento y estatus.
- [ ] Implementar flujo unverified → reviewed/rejected y mantener historial.
- [ ] Exigir licencia y acceso legítimo para procesar contenido completo.
- [ ] Añadir fichas verificadas para el caso piloto y avisos cuando solo haya metadatos.

## Criterios de aceptación
- [ ] Ningún abstract se presenta automáticamente como resultado de un ensayo.
- [ ] La UI distingue claims revisados y no revisados.
- [ ] Se conserva qué persona revisó y qué fuente se consultó.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `docs/science/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
