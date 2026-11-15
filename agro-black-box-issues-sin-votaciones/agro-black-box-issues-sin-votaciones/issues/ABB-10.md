# [ABB-10] Construir línea temporal forense e hipótesis rivales

<!-- AGRO-ISSUE-ID: ABB-10 -->
## Objetivo
Construir línea temporal forense e hipótesis rivales. Contribución a **Best Use of Data; Local Impact**. Fase **F1**, prioridad **P0**.

**Responsable sugerido:** A (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-06, ABB-08. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Generar eventos observacionales con fecha, fuente, variable, severidad definida y confianza en el dato.
- [ ] Separar hechos observados de inferencias, hipótesis y ausencia de evidencia.
- [ ] Definir hipótesis alternativas y preguntas de verificación local; no calcular falsos porcentajes de causalidad.
- [ ] Publicar API de timeline e hipótesis para frontend.

## Criterios de aceptación
- [ ] Timeline contiene observaciones reales, procedencia y límites.
- [ ] Se puede marcar una hipótesis como compatible, contradicha o no evaluable.
- [ ] Ninguna inferencia se etiqueta automáticamente como causa demostrada.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `docs/science/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
