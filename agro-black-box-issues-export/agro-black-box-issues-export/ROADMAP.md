# ROADMAP — AGRO BLACK BOX 1.0

> **Documento de planificación, no certificación de funcionalidades.** La fuente de verdad de lo implementado es `docs/operations/CURRENT_STATE.md`. Las Issues son propuestas hasta que se aprueban según `docs/governance/FEATURE_POLICY.md`.

## Objetivo

Terminar una herramienta de **investigación forense de incidentes agrícolas** que combine observaciones NASA, contexto local, evidencias científicas, al menos **tres rotaciones**, colaboración con permisos y un informe trazable. Es el **alcance completo 1.0**: no se declara terminada hasta superar todos los gates de `docs/product/RELEASE_1_0.md`.

## Lo que ya puede reutilizarse

| Componente | Situación verificada en el código entregado | Qué falta |
|---|---|---|
| FastAPI + OpenAPI | Rutas de desarrollo presentes | Contratos 1.0, errores, persistencia, auth |
| POWER (`services/power.py`) | Adaptador inicial escrito | Validar datos reales, cobertura, QA, reintentos y manifiestos |
| Métricas (`services/metrics.py`) | Funciones y algunos tests | Validación metodológica, gaps, incertidumbre, endpoints |
| OpenAlex (`services/literature.py`) | Búsqueda de metadatos | Crossref, DOI, claims revisados, contexto de estudios |
| Rotaciones (`services/rotations.py`) | Ejemplos ilustrativos | Restricciones, 3 alternativas en contexto, comparación transparente |
| Informe (`services/report.py`) | Markdown preliminar | Versionado, fuentes, trazabilidad, permisos y exportación UI |
| React/Vite (`frontend/src/main.tsx`) | Interfaz inicial con una pantalla | Rutas, casos, mapas, evidencias, colaboración y EN/ES |
| PostgreSQL/Redis | Servicios declarados en `compose.yaml` | Persistencia y workers sin integrar |
| CI | Tests/compilación configurados | Lockfiles, E2E, integración y permisos |

**No hay verificación actual de una ejecución de NASA/OpenAlex en vivo, del despliegue, ni del funcionamiento multiusuario.** No afirmar lo contrario.

## Invariantes de ingeniería y ciencia

1. Hechos observados, hipótesis, simulaciones y notas de agricultores siempre identificados por separado.
2. Nada de atribuir causas o porcentajes de mejora agrícola sin evidencia adecuada.
3. Todas las transformaciones tienen fuente, unidad, resolución, periodo y tratamiento de datos faltantes.
4. Los casos y coordenadas exactas son privados por defecto y se comparten solo con consentimiento.
5. Las IA no aprueban funcionalidades; las decisiones viven en Issues, PRs y ADRs.
6. Cada módulo entra en `main` integrado y probado; jamás se etiqueta como completado por existir solo una interfaz.

## Fases y dependencias

| Fase | Objetivo verificable | Dependencia dominante |
|---|---|---|
| **F0 — Gobierno, contratos e infraestructura** | Monorepo reproducible, contratos estables, esquema de persistencia, permisos base y tablero gobernado por humanos. | Ninguna |
| **F1 — Investigación y observación terrestre** | Incidentes privados y reconstrucción satelital real con calidad, procedencia y explicaciones alternativas. | Contratos, almacenamiento, permisos |
| **F2 — Evidencia, rotaciones y explicabilidad** | Bibliografía verificada, grafo de evidencias, tres rotaciones factibles, análisis de incertidumbre. | Contratos, datos reales y suelos/cultivos |
| **F3 — Producto interactivo y colaboración** | Una web navegable EN/ES para investigar, comparar, compartir con permisos y exportar informes. | Contratos y endpoints validados; pueden usarse mocks etiquetados |
| **F4 — Seguridad, calidad, piloto y entrega** | Sistema seguro, desplegable, probado E2E y validado con un caso local y colaboración auténtica. | Integración y pruebas de las fases anteriores |

## Issues de la versión 1.0

Los IDs `ABB-nn` son claves **estables de planificación**, no números reales de GitHub. Al importar, se publican en el repositorio con una Issue por entrada.

| ID | Prioridad | Módulo | Liderazgo | Predecesoras |
|---|---|---|---|---|
| ABB-01 | P0 | Estabilizar herramientas, locks y CI reproducible | A | — |
| ABB-02 | P0 | Congelar contrato API y esquemas de datos v1 | A | ABB-01 |
| ABB-03 | P0 | Modelo PostgreSQL, migraciones y repositorio de datos | A | ABB-02 |
| ABB-04 | P0 | Configurar gobierno del equipo, GitHub Project y protección de main | C | ABB-01 |
| ABB-05 | P0 | Diseñar y aplicar permisos y autenticación segura | C | ABB-02, ABB-03 |
| ABB-06 | P0 | Gestión completa de investigaciones y parcelas | C | ABB-03, ABB-05 |
| ABB-07 | P0 | Robustecer NASA POWER y registrar procedencia | A | ABB-02 |
| ABB-08 | P0 | Motor de anomalías y control de calidad científico | A | ABB-07 |
| ABB-09 | P1 | Integrar GPM IMERG con armonización espacial y temporal | A | ABB-07, ABB-08 |
| ABB-10 | P0 | Construir línea temporal forense e hipótesis rivales | A | ABB-06, ABB-08 |
| ABB-11 | P0 | Registrar suelos, cultivos y calendario local del agricultor | B | ABB-02, ABB-06 |
| ABB-12 | P1 | Integrar HLS como observación de cobertura vegetal | A | ABB-07, ABB-09 |
| ABB-13 | P0 | OpenAlex + Crossref: búsqueda y verificación bibliográfica | B | ABB-02 |
| ABB-14 | P0 | Registro estructurado de claims científicos con revisión humana | B | ABB-03, ABB-13 |
| ABB-15 | P1 | Detector de contradicciones y aplicabilidad de estudios | B | ABB-11, ABB-14 |
| ABB-16 | P1 | Modelo de grafo de evidencia y trazabilidad | B | ABB-10, ABB-14 |
| ABB-17 | P0 | Motor de rotaciones con restricciones y tres estrategias | B | ABB-08, ABB-11, ABB-14 |
| ABB-18 | P1 | Análisis de escenarios, prioridades y sensibilidad | B | ABB-17 |
| ABB-19 | P1 | Uncertainty Hunter: carencias y comprobaciones útiles | B | ABB-10, ABB-15, ABB-18 |
| ABB-20 | P0 | Sistema de diseño, navegación, accesibilidad e idioma EN/ES | C | ABB-02 |
| ABB-21 | P0 | Wizard de incidente y mapa geoespacial con privacidad | C | ABB-05, ABB-06, ABB-20 |
| ABB-22 | P0 | Visualización avanzada de timeline, anomalías y fuentes NASA | C | ABB-08, ABB-10, ABB-20 |
| ABB-23 | P1 | Explorador visual de papers y Evidence Graph | C | ABB-14, ABB-16, ABB-20 |
| ABB-24 | P0 | Constructor y comparador interactivo de rotaciones | C | ABB-17, ABB-18, ABB-20 |
| ABB-25 | P0 | Invitaciones, revisión y colaboración entre comunidades | C | ABB-05, ABB-06, ABB-14, ABB-20 |
| ABB-26 | P0 | Informe de caso completo y exportación verificable | B | ABB-10, ABB-14, ABB-16, ABB-17, ABB-25 |
| ABB-27 | P1 | Caché, tareas asíncronas y resiliencia ante APIs externas | A | ABB-03, ABB-07, ABB-13 |
| ABB-28 | P0 | Seguridad, privacidad y operaciones de datos | C | ABB-05, ABB-25, ABB-26 |
| ABB-29 | P0 | Suite E2E y contratos entre backend y frontend | C | ABB-06, ABB-10, ABB-14, ABB-17, ABB-21, ABB-22, ABB-24, ABB-26 |
| ABB-30 | P1 | Despliegue seguro, monitorización y recuperación | A | ABB-01, ABB-03, ABB-05, ABB-27, ABB-29 |
| ABB-31 | P0 | Piloto agrícola local con revisión externa documentada | B | ABB-10, ABB-17, ABB-21, ABB-24, ABB-26 |
| ABB-32 | P1 | Colaboración internacional real y prueba de intercambio | B | ABB-25, ABB-31 |
| ABB-33 | P0 | Validación de release 1.0 y cierre técnico | A | ABB-09, ABB-12, ABB-15, ABB-19, ABB-23, ABB-25, ABB-26, ABB-28, ABB-29, ABB-30, ABB-31, ABB-32 |
| ABB-34 | P0 | Narrativa NASA Space Apps, vídeo y envío oficial | C | ABB-22, ABB-24, ABB-26, ABB-31 |

### Secuencia de trabajo propuesta

**Arranque (en paralelo):** A toma ABB-01, B revisa catálogos y bibliografía para ABB-13/ABB-17 (sin cambios de contratos no aprobados), C toma ABB-04 y la base visual ABB-20. Todos revisan ABB-02 antes de comprometer endpoints.

**Primera integración:** A ABB-07/08/10 (NASA), B ABB-11/13/14/17 (ciencia y rotaciones), C ABB-05/06/20/21 (casos, auth y experiencia). Es válido crear UI con datos simulados etiquetados *solo en desarrollo*; la release no puede ocultar mocks.

**Segunda integración:** cruzar APIs y pantallas ABB-22/23/24, pruebas contrafactuales ABB-18, revisión ABB-25 y evidencias ABB-16.

**Cierre de producto:** ABB-26/28/29/30; caso y feedback ABB-31/32; gate ABB-33. ABB-34 es material de concurso, no sustituye validación de ingeniería.

**Dependencia crítica:** contratos (ABB-02) → persistencia/permisos (ABB-03/05) → casos (ABB-06) → experiencia/collab (ABB-21/25) → informe/pruebas (ABB-26/29) → release (ABB-33). En paralelo: NASA (ABB-07/08/09/12) y literatura/rotaciones (ABB-13/14/17).

## Criterios de terminación de la versión 1.0

- [ ] Cobertura F-01...F-12 de `docs/product/RELEASE_1_0.md`, probada y documentada.
- [ ] Recorrido E2E sin comandos manuales: caso → NASA → hipótesis → papers → tres rotaciones → colaboración → informe.
- [ ] Fuentes NASA reales con trazabilidad y manejo explícito de errores/lagunas.
- [ ] Estudios/DOIs revisados, sin transformar automáticamente metadatos en afirmaciones científicas.
- [ ] Acceso privado, invitaciones revocables, tests de permisos y política de retención.
- [ ] Interfaz EN/ES, responsive, accesible, y sin resultados presentados como ciertos si son simulados.
- [ ] Deploy reproducible, logs, backups, documentación de Omarchy/WSL y recuperación.
- [ ] Al menos una revisión humana local y una contribución externa internacional auténtica si se afirma ese impacto.
- [ ] Dos revisiones independientes de PR para áreas de alto riesgo y consenso humano de 3/3 para release.

## Backlog de ideas posteriores a la 1.0 (NO aprobadas; no se importan como trabajos activos)

| Idea | Valor | Riesgo/validación previa |
|---|---|---|
| Motor de experimentos distribuidos | Diseñar ensayos cooperativos entre granjas | Consentimiento y revisión agronómica; plazos de cultivos |
| Crop Climate Twin de segunda generación | Transferir aprendizajes entre condiciones ambientales comparables | Peligro de extrapolación entre suelos/mercados |
| Paper Contradiction Radar cuantitativo | Agregación de efectos entre trabajos | Heterogeneidad, tamaños muestrales, sesgo de publicación |
| Value-of-Information formal | Priorizar mediciones locales que cambian la decisión | Requiere probabilidades calibradas |
| Datos ECOSTRESS/SMAP/GRACE | Variables de estrés e hidrología ampliadas | Resolución y compatibilidad a escala de parcela |
| Algoritmos robustos de estrés climático | Peores escenarios y minimax regret | Validación científica de modelo de vulnerabilidad |
| Aprendizaje federado privado | Intercambio de patrones sin datos sensibles | Seguridad, representatividad y coste |
| Auditoría comunitaria y moderación | Correcciones entre expertos/agricultores | Gobernanza de comunidades y abuso |
| Panel de impacto longitudinal | Evaluación de resultados reales durante campañas | Datos de campo, horizonte de varios años |
| App móvil offline | Investigación en zonas de baja conectividad | Sincronización, privacidad y conflictos |

Cualquiera de estas ideas necesita nueva Feature Issue, consenso humano y actualización de `RELEASE_1_0.md` si modifica el compromiso de la release.

## Guía GitHub e importación

Fuente única de issues: `planning/issues.json`. Importador idempotente: `scripts/publish_roadmap_issues.py`. Antes de publicar, los humanos deben revisar requisitos y votaciones; crear una Issue no equivale a aprobarla.

```bash
gh auth login
gh repo view --json nameWithOwner -q .nameWithOwner
uv run --no-project python scripts/publish_roadmap_issues.py --repo OWNER/REPO         # Simulación
uv run --no-project python scripts/publish_roadmap_issues.py --repo OWNER/REPO --apply # Crea las Issues
```

El script compara los títulos `[ABB-nn]`, crea solo las que faltan, añade etiquetas `phase:*`, `lead:*`, `priority:*`, `needs-vote` y **no asigna la etiqueta `team-approved`**. Si ya tenéis cambios manuales en GitHub, conservadlos: el importador no actualiza cuerpos de Issues existentes.

## Equipo y agentes

| Persona | IA | Responsabilidad dominante | Primera secuencia | Revisión cruzada |
|---|---|---|---|---|
| **A (tú)** | **ChatGPT / Codex** | Backend, NASA, métricas, contratos, integración/release | ABB-01 → ABB-02 → ABB-07 → ABB-08 → ABB-10 | B revisa método, C contrato/API |
| **B** | **Claude** | Papers, evidencia, suelos/cultivos, rotaciones, explicación | ABB-11 → ABB-13 → ABB-14 → ABB-17 → ABB-18 | A revisa datos/método |
| **C** | **Claude** | Frontend, UX/ES-EN, casos, autenticación/collab, deploy UX | ABB-04 → ABB-20 → ABB-05 → ABB-06 → ABB-21 | A revisa API/permisos |

Los roles son **stewards**, no monopolios: cualquier integrante puede implementar una Issue aprobada. El dueño de cada Issue es un humano; su IA no toma decisiones de producto autónomamente.

## Solo después, a futuro

Cuando la herramienta 1.0 esté estabilizada y exista evidencia validada, el equipo podrá estudiar redactar un artículo científico sobre la metodología y los resultados verificables. No es un frente de trabajo activo.
