# Guía rápida de la demo web

La colección de demo usa PostgreSQL y datos ficticios. Los nombres parecen naturales
para que el recorrido sea legible, pero las cuentas usan `example.invalid` y cada caso
termina en `— Synthetic`. No son personas ni explotaciones reales.

## Arranque

```bash
cd frontend
npm run dev -- --host 0.0.0.0
```

Abre `http://localhost:5173`. La API debe estar en `http://127.0.0.1:8000`; Vite la
conecta mediante el proxy de desarrollo.

## Propietaria: Lucía Martín

1. Inicia sesión con `lucia.martin.abb-demo@example.invalid`.
2. En **Cases**, abre cualquiera de los tres casos `— Synthetic`.
3. En **Timeline**, enseña las capas observadas, reportadas y las hipótesis, siempre con
   sus limitaciones.
4. En **Evidence**, revisa los estudios importados. `Metadata only` significa que la
   ficha bibliográfica existe, pero todavía no se ha comprobado el texto completo.
5. En **Uncertainty**, responde o descarta preguntas pendientes; las respuestas se
   etiquetan como `FARMER_REPORTED` y no inventan mediciones.
6. En **Collaboration**, comprueba la invitación, el comentario y la actividad.
7. En **Report**, crea una versión del informe y enseña sus descargas y verificabilidad.
8. En la pantalla de cuenta puedes exportar tus datos o eliminar esta cuenta sintética.

Contraseña de demo: `synthetic-demo-correct-horse-42`.

## Revisor: Marek Nowak

1. Abre una ventana privada o un perfil de navegador separado.
2. Inicia sesión con `marek.nowak.abb-demo@example.invalid`.
3. Acepta la invitación desde **Collaboration**.
4. Abre el caso: debe ser de solo lectura y mostrar una celda aproximada o solo región,
   nunca la coordenada exacta.
5. En **Evidence**, revisa la ficha y deja una observación; no puede revisar su propia
   aportación ni editar los datos de la propietaria.
6. En **Collaboration**, añade un comentario y comprueba que la propietaria lo ve.

## Visitante sin cuenta

Un visitante no ve los casos privados ni puede entrar por el identificador del caso. Solo
puede acceder a un enlace compartido que la propietaria haya creado expresamente con
consentimiento. El enlace no contiene coordenadas exactas, e-mails ni historial privado.

## Qué no afirmar durante la demo

- No presentar `— Synthetic` como un piloto agrícola real.
- No llamar “resultado observado” a una tarjeta bibliográfica `Metadata only`.
- No afirmar rendimiento, ahorro o causalidad: los casos solo enseñan el flujo, la
  trazabilidad y la protección de datos.
