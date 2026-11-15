# [ABB-01] Estabilizar herramientas, locks y CI reproducible

<!-- AGRO-ISSUE-ID: ABB-01 -->
## Objetivo
Estabilizar herramientas, locks y CI reproducible. Contribución a **Best Use of Data; transversal**. Fase **F0**, prioridad **P0**.

**Responsable sugerido:** A (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ninguna. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Generar y commitear `backend/uv.lock` con `uv lock`; instalar mediante `uv sync --locked --extra dev`.
- [ ] Generar y commitear `frontend/package-lock.json`; en CI ejecutar `npm ci`, no instalar versiones flotantes.
- [ ] Verificar el arranque en Ubuntu/WSL y Omarchy; documentar errores reales y sus soluciones.
- [ ] Confirmar `api-tests`, `web-build` y `context-policy` en una instalación limpia.

## Criterios de aceptación
- [ ] CI pasa con lockfiles en un checkout limpio.
- [ ] `uv run pytest -q`, `npm run build` y `scripts/check_context.py` reproducibles.
- [ ] README documenta el flujo de trabajo sin pip ni activación manual.

## Archivos o dominios afectados
- `backend/pyproject.toml`
- `backend/uv.lock`
- `frontend/package-lock.json`
- `.github/workflows/ci.yml`
- `README.md`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
