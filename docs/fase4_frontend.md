# Fase 4: Frontend (Streamlit)

## Qué hace
Formulario de turno → vista de aprobación (aprobar / editar / descartar) → dashboard (pase de guardia,
tareas pendientes, alertas y, según el rol, auditoría). Habla con la API solo por HTTP.

## Decisiones
1. El frontend no importa `backend.app`; los rangos del formulario son una ayuda y la API es la autoridad
   (sus 422 se muestran por campo).
2. Navegación con `st.navigation`; enfermería y supervisión operan, auditoría solo lee. El rol se lee del
   JWT sin verificar la firma, solo para el menú: cada acción la autoriza la API.
3. `Idempotency-Key` en `/procesar` y en `/decision`: una por envío, atada a la huella del contenido. Se
   conserva tras timeout/5xx y se libera con una respuesta definitiva.
4. El token vive solo en `st.session_state`; un 401 cierra la sesión y vuelve al login.
5. Timeout de 120 s, spinner y botones deshabilitados mientras se procesa.
6. El formulario no precarga signos vitales ni ítems de Morse: todo dato clínico se ingresa a propósito.
7. «Cargar caso de prueba» solo con `AURA_ENTORNO=dev`; cada caso carga su paciente del seed (ids 1, 2, 3).
8. Severidad con color y texto. Descartar exige confirmación.
9. Si el Agente Seguridad no estuvo disponible, la vista de aprobación lo advierte: «sin alertas» no es «sin riesgo».
10. Si el guardado queda pendiente, «Reintentar guardado» repite la MISMA decisión (la API rechaza otra distinta).
11. Tras recargar el navegador, un 409 en `/procesar` ofrece «Recuperar el turno pendiente» (`GET /turnos/{thread_id}`).
12. `httpx` es dependencia principal.

## Configuración
`API_URL` (default `http://localhost:8000`), `AURA_ENTORNO` (`dev` habilita el caso de prueba),
`API_TIMEOUT_S` (default 120).

## Contrato HTTP
Concentrado en `RUTAS` y `DECISIONES` de `frontend/api_client.py`, tomado de `backend/app/routers`.

## Limitaciones
- Sin alta de pacientes (la API no tiene `POST /pacientes`).
- Los rangos del formulario duplican los de `SignosVitales`: si cambian en la API, actualizar `payload.RANGOS`.
- `payload.thread_id_para` replica `make_thread_id`: si el backend cambia el formato, actualizar ambos.
- La API limita el login a 5 intentos por minuto (429).
