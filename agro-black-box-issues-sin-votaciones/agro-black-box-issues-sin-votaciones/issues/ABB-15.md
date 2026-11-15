# [ABB-15] Detector de contradicciones y aplicabilidad de estudios

<!-- AGRO-ISSUE-ID: ABB-15 -->
## Objetivo
Detector de contradicciones y aplicabilidad de estudios. Contribución a **Best Use of Data; Galactic Impact**. Fase **F2**, prioridad **P1**.

**Responsable sugerido:** B (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-11, ABB-14. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Definir reglas comparables por intervención, resultado y condiciones del estudio.
- [ ] Detectar desacuerdos entre claims sin afirmar que siempre se contradigan metodológicamente.
- [ ] Comparar clima, suelo, cultivos y prácticas del paper con las del caso; producir notas de transferibilidad.
- [ ] Integrar revisión humana y estado no concluyente.

## Criterios de aceptación
- [ ] Una contradicción real/revisada se muestra con sus dos referencias.
- [ ] Ausencia de datos impide un score de aplicabilidad falsamente preciso.
- [ ] Al menos un ejemplo de transferencia limitada documenta las diferencias.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `docs/science/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
