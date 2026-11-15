# [ABB-13] OpenAlex + Crossref: búsqueda y verificación bibliográfica

<!-- AGRO-ISSUE-ID: ABB-13 -->
## Objetivo
OpenAlex + Crossref: búsqueda y verificación bibliográfica. Contribución a **Best Use of Data; Galactic Impact**. Fase **F2**, prioridad **P0**.

**Responsable sugerido:** B (A = Codex/ChatGPT; B = Claude ciencia/agronomía; C = Claude interfaz/producto). La asignación es flexible: cualquier integrante o agente puede avanzar esta tarea.

**Dependencias técnicas orientativas:** ABB-02. No son bloqueos de aprobación: se puede trabajar en componentes independientes, tests, prototipos o contratos provisionales mientras se integran dependencias.

## Pasos de implementación
- [ ] Extender búsqueda existente y combinar metadatos mediante DOI con Crossref.
- [ ] Normalizar autores, título, año, DOI, licencia, fecha de consulta y URL.
- [ ] Separar coincidencia bibliográfica de evidencia confirmada en el texto.
- [ ] Probar errores de API, DOI faltante, duplicados y límites de uso.

## Criterios de aceptación
- [ ] Cada artículo tiene referencia verificable y procedencia.
- [ ] Un artículo sin DOI no se inventa.
- [ ] Búsqueda fallida no devuelve contenido científico fabricado.

## Archivos o dominios afectados
- `backend/agroblackbox/services/literature.py`
- `backend/tests/`

## Comprobaciones y entrega
- [ ] Ejecutar las pruebas que correspondan y registrar resultados reales; indicar claramente las no ejecutadas.
- [ ] Mantener contratos y documentación sincronizados con los cambios implementados.
- [ ] Dejar una nota breve de integración o handoff si otro agente utiliza este módulo.

**Flujo de trabajo:** la Issue está lista para implementarse. Coordinad únicamente las interfaces y los archivos compartidos cuando sea necesario. El equipo decidirá cuándo crear ramas, commits o PRs.
