# AGRO BLACK BOX — Exportación de 34 Issues

Repositorio: `Yago-Torres/Nasa_SpaceApps_Challenge_Hackatrans`.

Contiene 34 ficheros Markdown individuales, `issues.json`, `issues.csv`, `ROADMAP.md` y un importador. Todas son propuestas, no aprobaciones. **No se crean ramas ni se hace push de código.**

## Publicar en GitHub

Con GitHub CLI autenticado y permiso Issues: Read and write, desde esta carpeta:

```bash
gh auth login
uv run --no-project python publish_issues.py --repo Yago-Torres/Nasa_SpaceApps_Challenge_Hackatrans
uv run --no-project python publish_issues.py --repo Yago-Torres/Nasa_SpaceApps_Challenge_Hackatrans --apply
```

La primera ejecución es simulación. La segunda crea etiquetas e Issues ausentes. No cambia Issues existentes y evita duplicados por código ABB-XX. No requiere `pip` ni crear un entorno manual.

Para conservar el roadmap en el repositorio, añadid `ROADMAP.md` a `docs/ROADMAP.md` cuando queráis; esto es independiente de publicar Issues.

## Responsables recomendados

A = usuario con ChatGPT/Codex (backend, NASA, CI); B = Claude (evidencia y rotaciones); C = Claude (producto, interfaz y colaboración). El equipo puede reasignar cualquier Issue.
