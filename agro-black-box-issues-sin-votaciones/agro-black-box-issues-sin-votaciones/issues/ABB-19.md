# [ABB-19] Uncertainty Hunter: carencias y comprobaciones útiles

<!-- AGRO-ISSUE-ID: ABB-19 -->
## Objetivo
Uncertainty Hunter: carencias y comprobaciones útiles. Contribución a **Best Use of Data; Local Impact**. Fase **F2**, prioridad **P1**.

**Responsable sugerido:** B (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-10, ABB-15, ABB-18. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Localizar datos que faltan o son poco fiables para decidir entre rotaciones.
- [ ] Definir preguntas locales concretas (suelo, riego, etapa fenológica, manejo) con justificación.
- [ ] Mostrar qué conclusión podría cambiar al introducir esa observación, sin prometer cálculo de valor de información sin modelo.
- [ ] Añadir estado de resolución por agricultor o experto.

## Criterios de aceptación
- [ ] Cada pregunta propuesta explica qué incertidumbre abordaría.
- [ ] La interfaz permite registrar una respuesta local revisable.
- [ ] Si no hay base para priorizar una medición, se dice explícitamente.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `frontend/src/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
