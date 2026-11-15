# [ABB-17] Motor de rotaciones con restricciones y tres estrategias

<!-- AGRO-ISSUE-ID: ABB-17 -->
## Objetivo
Motor de rotaciones con restricciones y tres estrategias. Contribución a **Local Impact; Galactic Impact**. Fase **F2**, prioridad **P0**.

**Responsable sugerido:** B (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-08, ABB-11, ABB-14. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Implementar secuencias multianuales y calendarios por cultivo, con rotación actual obligatoria.
- [ ] Construir dos alternativas viables bajo suelo, clima, agua, equipo, cultivos y prioridades declaradas.
- [ ] Excluir combinaciones imposibles y documentar reglas y referencias agrícolas.
- [ ] Ejecutar comparación basada en exposición, cobertura potencial y restricciones; evitar predicción no validada de rendimiento.

## Criterios de aceptación
- [ ] Siempre se comparan >=3 estrategias, incluida la actual, o se explica por qué no son factibles.
- [ ] Cada recomendación indica beneficios posibles, riesgos y condiciones que requieren revisión.
- [ ] Los casos de calendario incompatible se rechazan en tests.

## Archivos o dominios afectados
- `backend/agroblackbox/services/rotations.py`
- `backend/tests/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
