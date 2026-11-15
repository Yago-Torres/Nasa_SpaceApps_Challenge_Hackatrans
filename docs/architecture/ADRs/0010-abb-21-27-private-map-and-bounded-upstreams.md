# ADR-0010 — Mapa local privado y resiliencia acotada para ABB-21/ABB-27

- Status: accepted
- Date: 2026-11-15
- Related GitHub Issues: ABB-21, ABB-27
- Reviewers / coordination notes: pendiente de revisión humana de producto, seguridad y operaciones

## Context

ABB-21 necesita una interfaz geoespacial para el wizard, pero una tesela externa puede
inferir una parcela mediante la URL de tesela, la ventana solicitada y la dirección IP.
El caso permite coordenadas exactas al propietario, pero los colaboradores reciben una
celda aproximada, una región o nada según el nivel de privacidad.

ABB-27 necesita evitar descargas repetidas y responder honestamente ante fallos de NASA
POWER. El servidor actual tiene reintentos acotados y caché TTL, pero la respuesta GeoJSON
de POWER contiene la geometría exacta consultada y no debe quedar persistida en disco.
Redis y un worker aún no están desplegados en el entorno objetivo del proyecto.

## Options considered

### ABB-21 map

1. Basemap externo con MapLibre: buena orientación cartográfica, pero añade proveedor,
   coste/condiciones de uso, dependencia de red y una superficie de filtración de ubicación.
2. Tiles autoalojadas: reduce la filtración a terceros, pero añade almacenamiento,
   actualización y operación fuera del alcance de esta entrega.
3. **Mapa local de privacidad en SVG**: muestra a escala el punto del propietario, la
   celda compartida y la celda espacial de NASA POWER sin realizar peticiones de red.

### ABB-27 execution and cache

1. Redis + worker ahora: proporciona progreso y reanudación, pero exige despliegue,
   recuperación y una política de durabilidad que el demo host todavía no tiene.
2. **Peticiones directas con timeout/reintentos acotados y caché TTL** para las operaciones
   actuales; registrar explícitamente el fallo y dejar Redis/worker para tareas que superen
   los límites medidos.
3. Persistir la respuesta POWER completa: conserva una copia sencilla, pero deja la
   geometría exacta en el sistema de archivos y contradice la política de minimización.

## Decision

1. ABB-21 usa el mapa local SVG de privacidad como mapa geoespacial de 1.0. No se añade
   MapLibre ni un proveedor de teselas en esta entrega. El mapa debe permanecer útil sin
   red y mostrar siempre el nivel de precisión que realmente verá cada rol.
2. ABB-27 mantiene el camino directo para las operaciones actuales. Los límites vigentes
   son timeout de cliente, tres intentos como máximo, backoff acotado y TTL de 24 horas.
   Un worker Redis solo se incorpora con una medición que demuestre que una operación
   supera esos límites o necesita progreso/reanudación, acompañado de un ADR de despliegue.
3. La caché de NASA POWER se guarda en formato 2: antes de escribir se elimina `geometry`
   y `coordinates`; el sidecar conserva `source_sha256` de la respuesta validada y un
   `cache_sha256` de los bytes minimizados. Las respuestas servidas desde caché mantienen
   el checksum de origen y su fecha de recuperación.
4. Las entradas de caché de formato anterior se consideran inválidas y se vuelven a
   descargar. En despliegue se debe eliminar el directorio antiguo de caché, que puede
   contener geometrías exactas.

## Tradeoffs and consequences

- Se renuncia a calles, satélite y geocodificación en el wizard para no convertir una
  decisión de privacidad en una dependencia externa silenciosa.
- El usuario sigue viendo límites espaciales honestos (celda POWER y precisión compartida),
  no una imagen cartográfica que sugiera una precisión inexistente.
- El camino directo no ofrece progreso para trabajos largos. Esa capacidad queda como
  trabajo explícito de ABB-27, no como una falsa promesa de interfaz.
- Al cambiar el formato de caché, el primer acceso tras actualizarse hace una descarga
  nueva; la trazabilidad científica conserva el checksum de la fuente original.

## Rollout / rollback

- ABB-21: desplegar el frontend; no requiere claves, tiles ni migración. Revertir elimina
  únicamente el texto/diagrama nuevo y no afecta a casos guardados.
- ABB-27: desplegar backend y ejecutar los tests de caché. Antes de arrancar una versión
  actualizada, borrar `backend/.cache/power/` en cada host existente. Revertir al código
  anterior es seguro, pero no debe restaurar una caché antigua en un entorno compartido.
