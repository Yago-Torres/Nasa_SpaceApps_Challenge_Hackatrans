# AGRO BLACK BOX — The Planetary Agricultural Forensics Lab

**NASA Space Apps Challenge 2026 · Herramienta agrícola · Monorepo para tres desarrolladores con Claude Code y OpenAI Codex.**

AGRO BLACK BOX investiga incidentes agrícolas mediante datos de observación de la Tierra, contrasta hipótesis con bibliografía científica verificable, compara **tres o más estrategias de rotación (incluida la actual)** y facilita la revisión entre comunidades y la exportación de **informes de caso**.

> **Estado del código:** el repositorio contiene una base de desarrollo funcional y las especificaciones completas de la versión 1.0. **No es todavía una versión 1.0 finalizada.** Consultad `docs/operations/CURRENT_STATE.md` para distinguir las funcionalidades implementadas de las pendientes. No presentéis simulaciones como observaciones NASA reales.

## 1. Contexto obligatorio para personas y agentes IA

El repositorio y las Issues del roadmap en GitHub constituyen la fuente de verdad. **No dependáis de la memoria de una conversación de Claude o ChatGPT.**

Leed, en este orden:

1. `AGENTS.md` (Claude Code también carga `CLAUDE.md`) y el `AGENTS.md` de la carpeta que vais a editar.
2. `docs/ai/CONTEXT_MAP.md`.
3. `docs/product/PRODUCT.md` y `docs/product/RELEASE_1_0.md`.
4. `docs/operations/CURRENT_STATE.md`.
5. `docs/architecture/ARCHITECTURE.md` y `docs/architecture/API_CONTRACTS.md`.
6. `docs/governance/FEATURE_POLICY.md` y `docs/science/SCIENTIFIC_POLICY.md`.
7. La GitHub Issue activa y el código/tests actuales de los módulos afectados.

**Inicio de una sesión IA:**

```text
Actúa como desarrollador de AGRO BLACK BOX. Lee AGENTS.md, CLAUDE.md (si estás en Claude), docs/ai/CONTEXT_MAP.md, el alcance 1.0, CURRENT_STATE, el flujo de trabajo y los contratos pertinentes. Identifica la Issue activa, qué está implementado y qué falta. No inventes datos ni funcionalidades. Antes de editar, presenta archivos afectados, dependencias y tests previstos. Implementa solo el alcance de la Issue y al final documenta la verificación y el traspaso a otro agente.
```

## 2. Stack y gestor de dependencias

| Componente | Tecnología | Herramienta |
|---|---|---|
| Backend y análisis científico | Python 3.12 + FastAPI | **uv** (único gestor de Python del proyecto) |
| Frontend | React + TypeScript + Vite | Node.js 24 + npm |
| Persistencia (objetivo 1.0) | PostgreSQL | Docker Compose para desarrollo |
| Colas (previstas) | Redis | Docker Compose para desarrollo |
| Automatización | GitHub Actions | `uv` para el backend, npm para el frontend |

**No crear ni activar entornos virtuales manualmente ni instalar dependencias con pip.** `uv` se encarga internamente de su entorno aislado; trabajad siempre con `uv sync`, `uv add`, `uv run` y `uv lock`. El archivo `backend/.python-version` indica Python 3.12.

## 3. Instalación y ejecución — Linux / WSL2

Requisitos: `git`, `uv`, Node.js 24 y npm. En WSL2 guardad el repositorio bajo `~/projects/` (sistema de archivos Linux) y no en `/mnt/c/`.

```bash
# Desde la raíz del repositorio: preparar dependencias Python con uv
cd backend
uv python install 3.12        # Solo hace falta la primera vez
uv sync --locked --extra dev  # Instala exactamente backend/uv.lock
uv run --locked uvicorn agroblackbox.app:app --reload --port 8000
```

En **otra terminal**, desde la raíz del repositorio:

```bash
cd frontend
npm ci
npm run dev
```

- Interfaz: http://localhost:5173
- API y documentación OpenAPI: http://localhost:8000/docs
- Los datos NASA y OpenAlex en vivo requieren conexión a Internet; **nunca** sustituyáis una respuesta fallida por datos inventados.

Comprobaciones locales:

```bash
# Desde la raíz
uv run --no-project python scripts/check_context.py
cd backend && uv lock --check && uv run --locked --extra dev pytest -q
cd ../frontend && npm run build
```

**Bloqueo de dependencias:** `backend/uv.lock` y `frontend/package-lock.json` están versionados y son obligatorios. Comprobad Python con `cd backend && uv lock --check` e instalad mediante `uv sync --locked --extra dev`. En frontend usad `npm ci`; no sustituyáis los locks por resoluciones flotantes durante CI.

ABB-03 utiliza PostgreSQL para la capa interna de persistencia; Redis sigue sin estar conectado. Para una base local vacía, ejecutad `docker compose up -d db`, copiad `DATABASE_URL` desde `.env.example` al entorno y aplicad `make db-upgrade`. Las pruebas de integración requieren una base desechable explícita mediante `TEST_DATABASE_URL`; nunca apuntéis esa variable a una base con datos que deban conservarse, porque la suite prueba migraciones y limpia tablas. Las rutas autenticadas que consumen esta capa se añaden en Issues posteriores.

## 4. Guía específica para agentes IA en Omarchy (Arch Linux)

Omarchy está basado en Arch y utiliza **mise** para gestionar herramientas de desarrollo. Su manual indica que `uv`, `gh` y distintos agentes de programación pueden estar disponibles mediante instalación diferida; no asumáis que el primer comando funcionará sin descargar nada.

### Preparación del equipo (la realiza la persona, no un agente sin permiso)

1. Abrir una terminal. Si faltan runtimes, usar `Super + Space → Install → Development` para instalar **Python** y **Node.js**, o gestionarlos con `mise`.
2. Comprobar herramientas y versiones:

   ```bash
   mise --version
   mise ls --current
   uv --version
   node --version        # objetivo: v24.x
   npm --version
   git --version
   gh --version
   ```

3. Si falta Node 24, utilizar `mise use -g node@24` tras confirmarlo con la persona. Para Python, es `uv python install 3.12`, no `pip`, `virtualenv` ni activación manual.
4. Clonar el repositorio con `gh repo clone <ORG>/agro-black-box` (después de `gh auth login`) o `git clone <URL>`. Nunca guardar credenciales en los archivos del proyecto.
5. Ejecutar el backend con `cd backend && uv sync --locked --extra dev && uv run --locked uvicorn agroblackbox.app:app --reload --port 8000` y el frontend con `cd frontend && npm ci && npm run dev`.
6. Si la Issue necesita PostgreSQL/Redis, Omarchy suele incluir Docker y Compose. Utilizar `sudo docker compose up -d` desde la raíz **solo tras consentimiento**. La pertenencia al grupo `docker` implica privilegios equivalentes a root; no cambiarla automáticamente.

Documentación del sistema: [Omarchy — Development Tools](https://omarchy.org/manual/development-tools/). Gestor Python: [uv — Working on projects](https://docs.astral.sh/uv/guides/projects/).

### Reglas operativas para Claude Code y ChatGPT/Codex en Omarchy

- **Primero leer el contexto**, luego la Issue y el código; nunca asumir que una instrucción de chat anterior sigue vigente si contradice el repositorio.
- Trabajar en el árbol actual sin crear ramas, commits, pushes o PRs automáticamente; los humanos deciden cuándo publicar cambios.
- No ejecutar `sudo`, `pacman`, `yay`, `mise use -g`, `omarchy update`, cambios de grupo, scripts remotos, `gh auth login` ni instalaciones globales sin autorización humana explícita.
- Para dependencias Python usar `uv add`/`uv remove` **dentro de `backend/`** solo cuando la Issue activa las requiera. Actualizar y revisar `pyproject.toml` **y** `uv.lock` juntos.
- Preferir `uv run` para comandos y tests; no usar `source .venv/bin/activate`, `python -m venv`, `pip install` o herramientas Python globales.
- Mantener los datos locales o privados fuera de Git; no exponer claves, coordenadas privadas ni registros personales a servicios externos sin autorización.
- Al terminar: ejecutar tests, actualizar `CURRENT_STATE.md` únicamente con funcionalidades probadas y dejar un handoff siguiendo `docs/ai/HANDOFF_TEMPLATE.md`.
- Si falta contexto, permisos o conectividad para verificar una integración, **detener el paso afectado y declarar el bloqueo**; no fabricar resultados ni indicar que se ha verificado algo que no se probó.

### Prompt corto de arranque en Omarchy

```text
Estamos en Omarchy (Arch Linux). Usa mise para runtimes del sistema cuando esté autorizado y uv para todas las dependencias y ejecuciones Python en backend/. No uses pip ni gestiones entornos Python manualmente. Lee AGENTS.md, docs/ai/CONTEXT_MAP.md, CURRENT_STATE y la Issue activa; inspecciona los tests. No ejecutes comandos privilegiados ni cambies herramientas globales sin mi autorización. Tras implementar la Issue, ejecuta los checks y prepara un resumen verificable para el handoff o PR.
```

## 5. Equipo, gobierno de features y GitHub

| Steward técnico | Revisión preferente de | ¿Puede implementar funcionalidades de otro dominio? |
|---|---|---|
| Persona A | NASA / observaciones / métricas | **Sí**, desde una Issue del roadmap |
| Persona B | Evidencias científicas / rotaciones | **Sí**, desde una Issue del roadmap |
| Persona C | Frontend / integración / autenticación | **Sí**, desde una Issue del roadmap |

- Toda feature se vincula a una **GitHub Roadmap Issue** con alcance y criterios verificables; no requiere votos ni etiquetas de aprobación para comenzar.
- El dominio indica quién revisa, no quién tiene permiso exclusivo para programar.
- Una tarea tiene un implementador principal y coordinación explícita cuando toca contratos o archivos compartidos. Los humanos deciden cuándo crear rama y PR; CI debe pasar antes de integrar.
- Las IA implementan y verifican el alcance de la Issue, pero no sustituyen la revisión técnica, científica o de seguridad.
- Las decisiones duraderas se guardan en Issues/ADRs, no en memorias de chat.

Consultar `docs/governance/GITHUB_SETUP.md`, `FEATURE_POLICY.md`, `TEAM_WORKFLOW.md` y `docs/ai/HANDOFF_TEMPLATE.md`.

## 6. Integridad científica y privacidad

Las observaciones espaciales no identifican por sí solas la causa de un fracaso agrícola. Los datos de NASA POWER tienen una resolución distinta a una medición local; metadatos de un artículo no prueban su resultado. Las rotaciones ilustrativas no son predicciones validadas de cosechas o ahorro hídrico. Toda conclusión importante requiere fuente, supuestos y limitaciones visibles. Los casos privados lo son por defecto.

## 7. Próximo trabajo — el artículo científico (futuro)

Cuando la **herramienta 1.0 esté estabilizada** y el equipo lo apruebe, se podrá redactar y publicar un artículo científico propio con metodología, resultados validados y limitaciones. **No forma parte de las tareas actuales de desarrollo.**
