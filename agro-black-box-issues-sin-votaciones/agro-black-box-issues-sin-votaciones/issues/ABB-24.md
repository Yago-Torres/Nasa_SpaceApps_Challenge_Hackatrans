# [ABB-24] Constructor y comparador interactivo de rotaciones

<!-- AGRO-ISSUE-ID: ABB-24 -->
## Objetivo
Constructor y comparador interactivo de rotaciones. Contribución a **Galactic Impact; Local Impact**. Fase **F3**, prioridad **P0**.

**Responsable sugerido:** C (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-17, ABB-18, ABB-20. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Crear editor de secuencia actual y dos alternativas, con años y estaciones.
- [ ] Añadir preferencias del agricultor y restricciones con formularios validados.
- [ ] Mostrar calendario, criterios, riesgos, explicaciones y por qué cada estrategia entra o se descarta.
- [ ] Incluir accesibilidad, estados de cálculo/error y guardado de selección.

## Criterios de aceptación
- [ ] Se pueden evaluar tres estrategias desde la UI.
- [ ] Cambiar las prioridades recalcula el resultado autorizado desde backend.
- [ ] No se presentan ahorros numéricos sin un modelo y fuente verificados.

## Archivos o dominios afectados
- `frontend/src/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
