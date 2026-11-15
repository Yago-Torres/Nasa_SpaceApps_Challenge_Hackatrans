# [ABB-33] Validación de release 1.0 y cierre técnico

<!-- AGRO-ISSUE-ID: ABB-33 -->
## Objetivo
Validación de release 1.0 y cierre técnico. Contribución a **Transversal**. Fase **F4**, prioridad **P0**.

**Responsable sugerido:** A (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-09, ABB-12, ABB-15, ABB-19, ABB-23, ABB-25, ABB-26, ABB-28, ABB-29, ABB-30, ABB-31, ABB-32. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Pasar la checklist completa de `RELEASE_1_0.md`, módulos F-01 a F-12.
- [ ] Revisar resultados de CI, pruebas de permisos, pruebas en Linux/WSL/Omarchy y smoke externo.
- [ ] Actualizar CURRENT_STATE, changelog, contratos, limitaciones y manual de operación.
- [ ] Obtener validación humana de los tres y etiquetar release v1.0.0 solo si todos los gates pasan.

## Criterios de aceptación
- [ ] Cada criterio F-01...F-12 tiene prueba/PR o incidencia sin resolver; si falta, no llamar release final.
- [ ] La demo puede completarse sin operaciones manuales sobre la API.
- [ ] El tag está asociado a versión desplegada y reproducible.

## Archivos o dominios afectados
- `docs/product/RELEASE_1_0.md`
- `docs/operations/`
- `.github/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
