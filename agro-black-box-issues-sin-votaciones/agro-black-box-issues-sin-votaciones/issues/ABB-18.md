# [ABB-18] Análisis de escenarios, prioridades y sensibilidad

<!-- AGRO-ISSUE-ID: ABB-18 -->
## Objetivo
Análisis de escenarios, prioridades y sensibilidad. Contribución a **Galactic Impact; Local Impact**. Fase **F2**, prioridad **P1**.

**Responsable sugerido:** B (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-17. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Permitir modificar prioridades del agricultor, agua disponible y escenarios climáticos etiquetados.
- [ ] Comparar alternativas bajo episodios históricos comunes y escenarios hipotéticos diferenciados.
- [ ] Aplicar reglas de multicriterio transparentes y mostrar tradeoffs, sin prometer ahorros específicos.
- [ ] Probar estabilidad, ordenación y explicación de cambios.

## Criterios de aceptación
- [ ] La misma entrada obtiene la misma comparación reproducible.
- [ ] Al cambiar una prioridad se muestra qué criterio cambia y por qué.
- [ ] No se confunden simulación, observación y resultado validado de campo.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `backend/tests/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
