# [ABB-16] Modelo de grafo de evidencia y trazabilidad

<!-- AGRO-ISSUE-ID: ABB-16 -->
## Objetivo
Modelo de grafo de evidencia y trazabilidad. Contribución a **Best Use of Data; Global Connection**. Fase **F2**, prioridad **P1**.

**Responsable sugerido:** B (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-10, ABB-14. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Diseñar nodos observación, hipótesis, estudio, claim, limitación y conclusión.
- [ ] Registrar aristas con tipo y estado de revisión; prohibir referencias huérfanas.
- [ ] Exponer endpoint navegable por caso con fuente verificable y control de permisos.
- [ ] Probar que toda conclusión científica remite a datos y/o revisión humana.

## Criterios de aceptación
- [ ] Cada conclusión importante se rastrea hasta su evidencia original.
- [ ] Grafo no crea enlaces inexistentes y soporta hipótesis contradictorias.
- [ ] El endpoint respeta permisos privados de caso.

## Archivos o dominios afectados
- `backend/agroblackbox/`
- `docs/architecture/API_CONTRACTS.md`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
